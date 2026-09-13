"""Tests for Semantic SIF Representation Model (Phase 4).

Verifies:
1. Embedding extraction: dimensionality (384), normalization, Apple Silicon/CPU execution.
2. Semantic classifier training on valid records.
3. Probability calibration using FrozenEstimator and CalibratedClassifierCV.
4. Validation-only threshold optimization.
5. Save/load integrity with SHA-256 manifest.
6. Hard guard: zero synthetic records in training split.
7. Prediction schema completeness.
"""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pytest

from app.nlp.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
    extract_embedding,
    extract_embeddings,
    get_preferred_device,
)
from app.nlp.semantic_model import (
    SemanticSifClassifier,
    SemanticModelPrediction,
    SEMANTIC_ARTIFACT_PATH,
    SEMANTIC_MANIFEST_PATH,
)
from app.training import (
    IncidentDataRecord,
    create_leak_free_split,
)


def test_preferred_device_detection():
    """Verify local device detection returns a valid string (mps, cuda, or cpu)."""
    device = get_preferred_device()
    assert device in ("mps", "cuda", "cpu")


def test_extract_embedding_shape_and_norm():
    """Verify single embedding is 384-dimensional and unit-normalized."""
    emb = extract_embedding("High pressure hydrogen sulfide leak on separation vessel")
    assert isinstance(emb, np.ndarray)
    assert emb.shape == (EMBEDDING_DIMENSION,)
    assert emb.dtype == np.float32
    norm = np.linalg.norm(emb)
    assert pytest.approx(norm, abs=1e-3) == 1.0


def test_extract_embeddings_batch():
    """Verify batch embedding extraction handles multiple texts."""
    texts = [
        "Hydrocarbon release at offshore platform wellhead",
        "Routine housekeeping completed on deck 3",
        "Scaffolding collapsed during turnaround maintenance",
    ]
    embs = extract_embeddings(texts)
    assert isinstance(embs, np.ndarray)
    assert embs.shape == (3, EMBEDDING_DIMENSION)
    for i in range(3):
        norm = np.linalg.norm(embs[i])
        assert pytest.approx(norm, abs=1e-3) == 1.0


def test_extract_embedding_empty_text():
    """Verify empty or whitespace-only text returns a zero vector without crashing."""
    emb = extract_embedding("   ")
    assert isinstance(emb, np.ndarray)
    assert emb.shape == (EMBEDDING_DIMENSION,)
    assert np.all(emb == 0.0)


def test_semantic_model_fit_calibrate_and_predict(tmp_path):
    """Verify full fit, calibration, threshold optimization, and prediction lifecycle."""
    train_texts = [
        "Explosion in crude distillation furnace with worker hospitalized",
        "H2S gas cloud detected over 100 ppm, emergency evacuation",
        "High pressure gas blow out at drilling rig floor",
        "Major oil spill into water body from fractured pipeline",
        "Worker fell from 20 foot ladder with severe head trauma",
        "Minor paper cut in office area",
        "Routine vibration monitoring on water pump showed normal",
        "Replaced air filter in control room HVAC unit",
        "Safety glasses cleaned at wash station",
        "Weekly safety meeting conducted with 12 attendees",
    ]
    train_labels = [True, True, True, True, True, False, False, False, False, False]

    val_texts = [
        "Uncontrolled gas release from flare knockout drum",
        "Scheduled visual inspection of storage tank foundation",
    ]
    val_labels = [True, False]

    classifier = SemanticSifClassifier(c=1.0, random_state=42)
    classifier.fit_train(train_texts, train_labels)

    # Base classifier predicts valid probabilities
    raw_probs = classifier.predict_probabilities(val_texts, use_calibrator=False)
    assert len(raw_probs) == 2
    assert all(0.0 <= p <= 1.0 for p in raw_probs)
    assert raw_probs[0] > raw_probs[1]  # SIF higher than Non-SIF

    # Calibrate on validation split
    classifier.calibrate_val(val_texts, val_labels)
    assert classifier.is_calibrated is True
    assert classifier.calibrator is not None

    # Calibrated probabilities
    cal_probs = classifier.predict_probabilities(val_texts, use_calibrator=True)
    assert len(cal_probs) == 2
    assert all(0.0 <= p <= 1.0 for p in cal_probs)

    # Threshold optimization
    opt_thresh = classifier.optimize_decision_threshold(val_texts, val_labels, target_sif_recall=0.85)
    assert 0.0 < opt_thresh < 1.0

    # Test single prediction interface
    pred = classifier.predict_one("High pressure gas release ignited injuring worker")
    assert isinstance(pred, SemanticModelPrediction)
    assert 0.0 <= pred.raw_probability <= 1.0
    assert 0.0 <= pred.calibrated_probability <= 1.0
    assert isinstance(pred.sif_potential, bool)
    assert pred.is_calibrated is True

    # Test artifact save and reload
    art_file = tmp_path / "test_semantic_model.joblib"
    classifier.save(art_file)
    assert art_file.exists()

    loaded = SemanticSifClassifier.load(art_file)
    assert loaded.is_calibrated is True
    assert loaded.optimal_threshold == classifier.optimal_threshold
    assert loaded.model_version == classifier.model_version


def test_no_synthetic_in_semantic_training():
    """Hard guard: verify that the training script strictly filters out synthetic records."""
    from scripts.train_semantic_model import load_imported_records

    records = load_imported_records()
    for r in records:
        assert r.data_type != "synthetic", f"Synthetic record {r.id} found in imported dataset"
        assert r.label_source == "IMPORTED", f"Record {r.id} has non-imported source: {r.label_source}"
        assert r.label is not None, f"Record {r.id} has None label"


def test_semantic_artifact_and_manifest_exist():
    """Verify production-ready presence of semantic artifact and manifest files."""
    assert SEMANTIC_ARTIFACT_PATH.exists(), f"Artifact not found: {SEMANTIC_ARTIFACT_PATH}"
    assert SEMANTIC_MANIFEST_PATH.exists(), f"Manifest not found: {SEMANTIC_MANIFEST_PATH}"

    manifest = json.loads(SEMANTIC_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert "sha256" in manifest
    assert "model_version" in manifest
    assert manifest["embedding_dimension"] == 384
    assert manifest["is_calibrated"] is True


def test_semantic_model_evaluation_report_exists():
    """Verify SEMANTIC_MODEL.md and SEMANTIC_MODEL.json were generated and contain complete metrics."""
    project_root = Path(__file__).resolve().parents[2]
    md_path = project_root / "SEMANTIC_MODEL.md"
    json_path = project_root / "SEMANTIC_MODEL.json"

    assert md_path.exists(), "SEMANTIC_MODEL.md does not exist"
    assert json_path.exists(), "SEMANTIC_MODEL.json does not exist"

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert "test" in data
    assert "rule_baseline" in data["test"]
    assert "tfidf_baseline" in data["test"]
    assert "semantic_model" in data["test"]

    # Verify all 8 core metrics are present in JSON for the semantic model
    sem_metrics = data["test"]["semantic_model"]
    for m in ("precision", "recall", "f1", "brier_score", "sif_recall", "false_negative_count", "false_positive_count"):
        assert m in sem_metrics, f"Missing metric {m} in semantic model evaluation"
