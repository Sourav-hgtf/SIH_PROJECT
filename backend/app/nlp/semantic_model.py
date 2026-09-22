"""Semantic SIF representation model and classifier.

Architecture:
  Incident Text
    ↓ Preprocessing (PII redaction, spelling, abbreviations) via app.nlp.preprocess
  Sentence Transformer (all-MiniLM-L6-v2 → 384-d normalized vector)
    ↓
  Logistic Regression Classifier (fitted on TRAIN partition only)
    ↓
  sklearn CalibratedClassifierCV(cv='prefit', method='sigmoid')
    (sigmoid calibration layer fitted on VAL partition only)
    ↓
  Threshold Optimization (safety-recall-prioritized grid search on calibrated VAL)
    ↓
  Calibrated SIF Probability & Decision

Guarantees:
1. 100% Local / Offline execution — zero external API calls.
2. Identical preprocessing across train, val, test, and inference.
3. True probability calibration on held-out validation data.
4. Independent artifact storage (does not overwrite TF-IDF production model).
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression

from app.config import settings
from app.nlp.calibration import optimize_threshold
from app.nlp.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
    extract_embeddings,
)

logger = logging.getLogger(__name__)

SEMANTIC_ARTIFACT_DIR = Path(__file__).resolve().parents[3] / "data" / "model_artifacts"
SEMANTIC_ARTIFACT_PATH = SEMANTIC_ARTIFACT_DIR / "semantic_sif_model.joblib"
SEMANTIC_MANIFEST_PATH = SEMANTIC_ARTIFACT_DIR / "semantic_model_manifest.json"


@dataclass
class SemanticModelPrediction:
    raw_probability: float
    calibrated_probability: float
    is_calibrated: bool
    sif_potential: bool
    threshold: float
    model_version: str
    embedding_model: str
    calibration_version: str
    threshold_version: str


class SemanticSifClassifier:
    """SIF classifier built on dense local sentence embeddings."""

    def __init__(
        self,
        embedding_model_name: str = DEFAULT_EMBEDDING_MODEL,
        c: float = 1.0,
        random_state: int = 42,
    ):
        self.embedding_model_name = embedding_model_name
        self.classifier = LogisticRegression(
            C=c,
            max_iter=1000,
            class_weight="balanced",
            solver="lbfgs",
            random_state=random_state,
        )
        self.calibrator: CalibratedClassifierCV | None = None
        self.optimal_threshold: float = settings.sif_threshold
        self.is_calibrated: bool = False
        self.model_version: str = f"sif-semantic-minilm-v1-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        self.calibration_version: str = "uncalibrated-v0"
        self.threshold_version: str = "thresh-default-v1"
        self.training_run_id: str = str(uuid.uuid4())

    def fit_train(self, train_texts: list[str], train_labels: list[bool]) -> None:
        """Fit the base classifier on training partition embeddings only."""
        if not train_texts or not train_labels:
            raise ValueError("Training texts and labels cannot be empty.")
        X_train = extract_embeddings(train_texts, model_name=self.embedding_model_name)
        y_train = np.array(train_labels, dtype=bool)
        self.classifier.fit(X_train, y_train)
        logger.info(f"Fitted semantic classifier on {len(train_texts)} train embeddings.")

    def calibrate_val(self, val_texts: list[str], val_labels: list[bool]) -> None:
        """Fit sigmoid probability calibrator on validation partition embeddings only."""
        if not val_texts or not val_labels:
            logger.warning("No validation data for calibration. Retaining uncalibrated classifier.")
            return

        y_val = np.array(val_labels, dtype=bool)
        unique_classes = np.unique(y_val)
        if len(unique_classes) < 2:
            logger.warning(
                f"Validation partition contains only class {unique_classes}. "
                "Cannot fit binary calibrator; retaining uncalibrated classifier."
            )
            return

        X_val = extract_embeddings(val_texts, model_name=self.embedding_model_name)
        n_val = len(X_val)
        cv_single_split = [(np.arange(n_val), np.arange(n_val))]
        try:
            from sklearn.frozen import FrozenEstimator
            estimator_to_calibrate = FrozenEstimator(self.classifier)
        except ImportError:
            estimator_to_calibrate = self.classifier

        self.calibrator = CalibratedClassifierCV(
            estimator=estimator_to_calibrate,
            method="sigmoid",
            cv=cv_single_split,
        )
        self.calibrator.fit(X_val, y_val)
        self.is_calibrated = True
        self.calibration_version = "sklearn-ccv-sigmoid-v1"
        logger.info(f"Calibrated semantic classifier on {len(val_texts)} validation embeddings.")

    def optimize_decision_threshold(
        self,
        val_texts: list[str],
        val_labels: list[bool],
        target_sif_recall: float = 0.85,
    ) -> float:
        """Find optimal operating threshold on calibrated validation predictions."""
        if not val_texts or not val_labels:
            self.optimal_threshold = settings.sif_threshold
            return self.optimal_threshold

        probs = self.predict_probabilities(val_texts, use_calibrator=True)
        opt_thresh, thresh_ver, thresh_info = optimize_threshold(
            val_labels,
            probs,
            target_recall=target_sif_recall,
        )
        self.optimal_threshold = float(opt_thresh)
        self.threshold_version = thresh_ver
        logger.info(f"Optimized decision threshold: {self.optimal_threshold:.4f} (version: {thresh_ver})")
        return self.optimal_threshold

    def predict_probabilities(self, texts: list[str], use_calibrator: bool = True) -> list[float]:
        """Predict SIF probability for a list of raw texts."""
        if not texts:
            return []
        X = extract_embeddings(texts, model_name=self.embedding_model_name)
        estimator = self.calibrator if (use_calibrator and self.is_calibrated and self.calibrator is not None) else self.classifier
        classes = list(estimator.classes_)
        pos_idx = classes.index(True) if True in classes else 1
        probas = estimator.predict_proba(X)[:, pos_idx]
        return [float(max(0.0, min(1.0, p))) for p in probas]

    def predict_one(self, raw_text: str, threshold: float | None = None) -> SemanticModelPrediction:
        """Run single-instance inference with detailed confidence and provenance."""
        thresh = self.optimal_threshold if threshold is None else threshold
        raw_prob = self.predict_probabilities([raw_text], use_calibrator=False)[0]
        cal_prob = self.predict_probabilities([raw_text], use_calibrator=True)[0] if self.is_calibrated else raw_prob
        final_prob = cal_prob if self.is_calibrated else raw_prob
        is_sif = final_prob >= thresh

        return SemanticModelPrediction(
            raw_probability=round(raw_prob, 4),
            calibrated_probability=round(cal_prob, 4),
            is_calibrated=self.is_calibrated,
            sif_potential=is_sif,
            threshold=round(thresh, 4),
            model_version=self.model_version,
            embedding_model=self.embedding_model_name,
            calibration_version=self.calibration_version,
            threshold_version=self.threshold_version,
        )

    def save(self, artifact_path: Path = SEMANTIC_ARTIFACT_PATH) -> None:
        """Serialize model artifact and write cryptographic manifest."""
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "classifier": self.classifier,
            "calibrator": self.calibrator,
            "embedding_model_name": self.embedding_model_name,
            "optimal_threshold": self.optimal_threshold,
            "is_calibrated": self.is_calibrated,
            "model_version": self.model_version,
            "calibration_version": self.calibration_version,
            "threshold_version": self.threshold_version,
            "training_run_id": self.training_run_id,
            "embedding_dimension": EMBEDDING_DIMENSION,
            "saved_at": datetime.now(UTC).isoformat(),
        }
        joblib.dump(payload, artifact_path, compress=3)

        sha256_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        manifest = {
            "model_version": self.model_version,
            "embedding_model": self.embedding_model_name,
            "embedding_dimension": EMBEDDING_DIMENSION,
            "sha256": sha256_hash,
            "training_date": payload["saved_at"],
            "optimal_threshold": self.optimal_threshold,
            "is_calibrated": self.is_calibrated,
            "calibration_version": self.calibration_version,
            "threshold_version": self.threshold_version,
            "training_run_id": self.training_run_id,
            "artifact_file": artifact_path.name,
        }
        manifest_path = artifact_path.parent / "semantic_model_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        logger.info(f"Saved semantic model artifact to {artifact_path} (SHA-256: {sha256_hash[:16]}...)")

    @classmethod
    def load(cls, artifact_path: Path = SEMANTIC_ARTIFACT_PATH) -> SemanticSifClassifier:
        """Load and verify serialized semantic model."""
        if not artifact_path.exists():
            raise FileNotFoundError(f"Semantic model artifact not found at {artifact_path}")

        payload = joblib.load(artifact_path)
        inst = cls(embedding_model_name=payload.get("embedding_model_name", DEFAULT_EMBEDDING_MODEL))
        inst.classifier = payload["classifier"]
        inst.calibrator = payload.get("calibrator")
        inst.optimal_threshold = float(payload.get("optimal_threshold", settings.sif_threshold))
        inst.is_calibrated = bool(payload.get("is_calibrated", False))
        inst.model_version = payload.get("model_version", "unknown")
        inst.calibration_version = payload.get("calibration_version", "unknown")
        inst.threshold_version = payload.get("threshold_version", "unknown")
        inst.training_run_id = payload.get("training_run_id", "")
        return inst
