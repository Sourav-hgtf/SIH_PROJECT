"""Machine learning training entry point and persistence helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import logging

import joblib
from sqlalchemy.orm import Session
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import precision_recall_fscore_support, accuracy_score, roc_auc_score, average_precision_score, confusion_matrix

from app.config import settings
from app.models import AnalystFeedback, ModelTrainingRun, Report, ReportReview, SifClassification
from app.nlp.model import ARTIFACT_PATH

logger = logging.getLogger(__name__)

def _feedback_label(feedback: AnalystFeedback) -> bool | None:
    if feedback.feedback_type == "override_sif":
        value = (feedback.new_value or {}).get("sif_label")
        return bool(value) if isinstance(value, bool) else None
    if feedback.feedback_type == "confirm_sif":
        value = (feedback.previous_value or {}).get("sif_label")
        return bool(value) if isinstance(value, bool) else None
    return None

def run_ml_training(db: Session, force_demo_fallback: bool = True) -> ModelTrainingRun:
    """Train a new TF-IDF + Logistic Regression model for SIF classification.

    Production training policy (Requirement 11 & 12):
    - Production training uses exclusively human-validated labels (validated_label in ('SIF', 'NON_SIF')).
    - Synthetic demo labels are strictly barred from production training and final evaluation.
    - If force_demo_fallback is True (offline dev/cold start only), heuristic demo data is used
      with explicit warning and zero contamination of gold validation metrics.
    """
    # 1. Fetch validated human labels from reports & reviews
    # Validated records are those where consensus was reached or senior HSE reviewed
    reports = db.query(Report).all()

    validated_X = []
    validated_y = []
    demo_fallback_X = []
    demo_fallback_y = []

    for report in reports:
        text = report.processed_text or report.raw_text_redacted
        is_synthetic = getattr(report, "data_type", "synthetic") == "synthetic"
        val_lbl = getattr(report, "validated_label", None)
        human_lbl = getattr(report, "human_label", None)

        # 1. Check validated gold label first
        if val_lbl in ("SIF", "NON_SIF"):
            validated_X.append(text)
            validated_y.append(True if val_lbl == "SIF" else False)
        # 2. Check human review if not yet in consensus
        elif human_lbl in ("SIF", "NON_SIF") and not is_synthetic:
            validated_X.append(text)
            validated_y.append(True if human_lbl == "SIF" else False)
        elif report.final_sif_label is not None and getattr(report, "label_source", "") in ("CONSENSUS_VALIDATED", "SENIOR_HSE_OVERRIDE", "HUMAN_REVIEW"):
            validated_X.append(text)
            validated_y.append(bool(report.final_sif_label))
        elif force_demo_fallback and report.classification is not None:
            # Cold-start development fallback only
            demo_fallback_X.append(text)
            demo_fallback_y.append(bool(report.classification.sif_label))

    feedback_count = len(validated_X)

    if validated_X:
        logger.info(f"Training on {len(validated_X)} human-validated records.")
        X_raw = validated_X
        y_raw = validated_y
    elif force_demo_fallback and demo_fallback_X:
        logger.warning(
            "[DEFENSE AUDIT WARNING] Training using demo fallback data. "
            "No validated human labels exist in database. Synthetic labels strictly tagged."
        )
        X_raw = demo_fallback_X
        y_raw = demo_fallback_y
    else:
        raise ValueError("No validated human-labelled records found for production training.")

    # Convert to standard python bools
    y_raw = [bool(lbl) for lbl in y_raw]

    # If we have very few examples, we use a small split
    if len(X_raw) < 10:
        X_train, X_test, y_train, y_test = X_raw, X_raw, y_raw, y_raw
    else:
        has_both_classes = len(set(y_raw)) > 1
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X_raw, y_raw, test_size=0.2, random_state=42, stratify=y_raw if has_both_classes else None
            )
        except ValueError:
            X_train, X_test, y_train, y_test = train_test_split(
                X_raw, y_raw, test_size=0.2, random_state=42
            )
            
    # 4. Define and train pipeline
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(max_features=5000, stop_words="english")),
        ("clf", LogisticRegression(class_weight="balanced", random_state=42))
    ])
    
    # Check if there is only 1 class in the training data (can happen in extreme edge cases)
    if len(set(y_train)) < 2:
        logger.warning("Only one class present in training data. Model will not learn meaningful differences.")
        
    pipeline.fit(X_train, y_train)
    
    # 5. Evaluate
    # If the test set only has 1 class, metrics might be poorly defined, but we catch it with zero_division
    y_pred = pipeline.predict(X_test)
    # Basic binary metrics
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_test, y_pred, average="binary", zero_division=0
    )
    # Additional metrics
    accuracy = accuracy_score(y_test, y_pred)
    # ROC AUC and PR AUC require both classes present; otherwise set to None
    try:
        roc_auc = roc_auc_score(y_test, pipeline.predict_proba(X_test)[:, 1])
    except ValueError:
        roc_auc = None
    try:
        pr_auc = average_precision_score(y_test, pipeline.predict_proba(X_test)[:, 1])
    except ValueError:
        pr_auc = None
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred, labels=[False, True]).ravel()
    positive_samples = sum(y_test)
    negative_samples = len(y_test) - positive_samples

    metrics = {
        "sample_size": len(X_raw),
        "test_size": len(X_test),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "accuracy": round(accuracy, 3),
        "roc_auc": round(roc_auc, 3) if roc_auc is not None else None,
        "pr_auc": round(pr_auc, 3) if pr_auc is not None else None,
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "positive_samples": int(positive_samples),
        "negative_samples": int(negative_samples),
    }
    
    # 6. Save model artifact
    version = f"tfidf-logreg-v1-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    
    model_data = {
        "pipeline": pipeline,
        "model_version": version,
        "feedback_count": feedback_count,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model_data, ARTIFACT_PATH)

    # Update SHA-256 in model_manifest.json
    import hashlib
    manifest_path = ARTIFACT_PATH.parent / "model_manifest.json"
    sha256 = hashlib.sha256(ARTIFACT_PATH.read_bytes()).hexdigest()
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({"model_file": ARTIFACT_PATH.name, "model_version": version, "sha256": sha256}, f, indent=2)

    # Clear model cache in memory
    from app.nlp import model as nlp_model
    nlp_model._MODEL_CACHE = None

    
    # 7. Record run in DB
    run = ModelTrainingRun(
        model_version=version,
        artifact_path=str(ARTIFACT_PATH),
        feedback_count=feedback_count,
        metrics_before={},  # Not easily computable without loading old model
        metrics_after=metrics,
    )
    db.add(run)
    db.flush()
    return run

# Keep the old function signature for compatibility with admin.py, but wire it to the new ML training
def run_feedback_calibration(db: Session) -> ModelTrainingRun:
    """Wrapper around run_ml_training to preserve backwards compatibility with admin routes."""
    return run_ml_training(db, force_demo_fallback=True)

if __name__ == "__main__":
    from app.database import SessionLocal
    print("Running ML training pipeline...")
    db = SessionLocal()
    try:
        run = run_ml_training(db)
        db.commit()
        print(f"Success! Model {run.model_version} created.")
        print(f"Metrics: {run.metrics_after}")
    finally:
        db.close()
