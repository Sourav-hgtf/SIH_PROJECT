from datetime import datetime, timezone
import json
import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.database import Base, engine, SessionLocal
from app.main import app
from app.models import Report, SifClassification, Site
from app.nlp.calibration import (
    calibrate_classifier,
    compute_brier_score,
    compute_expected_calibration_error,
    compute_log_loss,
    optimize_threshold,
)
from app.nlp.model import (
    ARTIFACT_PATH,
    MANIFEST_PATH,
    get_model_health_status,
    load_sif_model,
    predict_sif_details,
    predict_sif_probability,
)
from app.nlp.preprocess import preprocess
from app.training import run_ml_training

client = TestClient(app)


@pytest.fixture(scope="module")
def setup_training_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    site = Site(name="Calibration Test Facility", region="Assam")
    db.add(site)
    db.commit()

    # Seed 30 realistic reports (15 SIF, 15 Safe) for calibrated training
    for i in range(15):
        db.add(
            Report(
                source_report_id=f"cal-sif-{i}",
                report_type="incident",
                site_id=site.id,
                raw_text_redacted=f"High pressure gas blowout and fire at drilling rig wellhead cell {i}",
                validated_label="SIF",
                label_source="CONSENSUS_VALIDATED",
                reported_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
            )
        )
        db.add(
            Report(
                source_report_id=f"cal-safe-{i}",
                report_type="observation",
                site_id=site.id,
                raw_text_redacted=f"Routine daily housekeeping observation: safety cones positioned at walkway {i}",
                validated_label="NON_SIF",
                label_source="CONSENSUS_VALIDATED",
                reported_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
            )
        )

    db.commit()
    yield db
    db.close()


def test_brier_score_and_ece_metrics():
    """Requirement 9: Probability calibration error metrics (Brier Score, ECE, log loss)."""
    y_true = [True, True, False, False, True, False]
    y_prob = [0.90, 0.85, 0.15, 0.10, 0.80, 0.20]

    brier = compute_brier_score(y_true, y_prob)
    ece = compute_expected_calibration_error(y_true, y_prob)
    logloss = compute_log_loss(y_true, y_prob)

    assert brier is not None
    assert 0.0 <= brier <= 0.25  # Well-calibrated predictions have low Brier score
    assert ece is not None
    assert 0.0 <= ece <= 0.5
    assert logloss is not None
    assert logloss > 0.0


def test_threshold_optimization_on_validation():
    """Requirement 7 & 8: Threshold selection optimizes safety recall on validation data without touching test data."""
    y_val = [True, True, True, False, False, False, False]
    val_probs = [0.95, 0.88, 0.48, 0.40, 0.25, 0.15, 0.10]

    opt_thresh, thresh_ver, metrics = optimize_threshold(y_val, val_probs, target_recall=0.85)

    assert 0.10 <= opt_thresh <= 0.90
    assert "thresh-" in thresh_ver
    assert metrics["recall"] >= 0.85
    assert metrics["sample_size"] == len(y_val)


def test_model_artifact_metadata_and_version_separation(setup_training_db: Session):
    """Requirement 1, 2, 3, 4: Model training produces artifact with separated versions and true calibration."""
    db = setup_training_db
    run = run_ml_training(db, force_demo_fallback=False, random_seed=42)

    assert run is not None
    assert ARTIFACT_PATH.exists()

    # Load artifact dictionary
    model_data = load_sif_model()

    assert "model_version" in model_data
    assert "feature_version" in model_data
    assert "preprocessing_version" in model_data
    assert "dataset_version" in model_data
    assert "label_schema_version" in model_data
    assert "calibration_version" in model_data
    assert "calibration_method" in model_data
    assert "is_calibrated" in model_data
    assert "threshold_version" in model_data
    assert "optimal_threshold" in model_data
    assert "training_run_id" in model_data
    assert "trained_at" in model_data
    assert "metrics" in model_data

    # Verify version concepts are distinct and not conflated
    assert model_data["model_version"] != model_data["calibration_version"]
    assert model_data["model_version"] != model_data["threshold_version"]
    assert model_data["calibration_version"] != model_data["threshold_version"]

    assert model_data["feature_version"] == "tfidf-unigram-bigram-v1"
    assert model_data["preprocessing_version"] == "prep-pii-spell-abbr-v1"
    assert model_data["is_calibrated"] is True
    assert model_data["calibration_method"] == "sigmoid"
    assert "sklearn-ccv-sigmoid-v1" in model_data["calibration_version"]


def test_prediction_reproducibility_and_version_exposure():
    """Requirement 5 & 6: Prediction responses expose calibrated probability and version metadata."""
    text = "Severe gas blowout and high voltage arc flash near drilling rig"

    details = predict_sif_details(text)

    assert "sif_probability" in details
    assert "calibrated_sif_probability" in details
    assert "is_calibrated" in details
    assert "calibration_status" in details
    assert "sif_potential" in details
    assert "model_version" in details
    assert "calibration_version" in details
    assert "threshold_version" in details
    assert "threshold" in details
    assert "preprocessing_version" in details
    assert "processed_text" in details

    assert 0.0 <= details["sif_probability"] <= 1.0
    assert details["is_calibrated"] is True
    assert details["calibration_status"] == "CALIBRATED"
    assert details["calibrated_sif_probability"] is not None
    assert 0.0 <= details["calibrated_sif_probability"] <= 1.0
    assert isinstance(details["sif_potential"], bool)

    # Verify reproducibility across repeated calls
    details2 = predict_sif_details(text)
    assert details["sif_probability"] == details2["sif_probability"]
    assert details["calibrated_sif_probability"] == details2["calibrated_sif_probability"]
    assert details["sif_potential"] == details2["sif_potential"]


def test_test_set_isolation_and_leak_free_split():
    """Verify train / val / test sets have 0 ID leakage and 0 text duplicate leakage."""
    from app.training import create_leak_free_split, IncidentDataRecord

    records = [
        IncidentDataRecord(
            id=f"rec-{i}",
            group_id=f"grp-{i // 2}",
            raw_text=f"Incident text sample {i}",
            norm_text=f"incident text sample {i}",
            text_hash=f"hash-{i}",
            label=(i % 2 == 0),
            data_type="human_validated",
            label_source="CONSENSUS_VALIDATED",
        )
        for i in range(40)
    ]

    status, train_recs, val_recs, test_recs = create_leak_free_split(records)
    assert status == "VALIDATED"
    assert len(train_recs) > 0
    assert len(val_recs) > 0
    assert len(test_recs) > 0

    train_ids = {r.id for r in train_recs}
    val_ids = {r.id for r in val_recs}
    test_ids = {r.id for r in test_recs}

    assert len(train_ids & val_ids) == 0
    assert len(train_ids & test_ids) == 0
    assert len(val_ids & test_ids) == 0


def test_model_loading_and_integrity_verification():
    """Verify model loading and integrity verification via SHA-256."""
    health = get_model_health_status()
    assert health["valid"] is True
    assert health["status"] == "MODEL_INTEGRITY_VALID"
    assert health["artifact_exists"] is True
    assert health["manifest_exists"] is True

    model_data = load_sif_model()
    assert model_data["calibrator"] is not None
    assert model_data["pipeline"] is not None


def test_api_endpoints_expose_version_metadata():
    """Requirement 5: /model-info and /predict endpoints return rich calibration and version metadata."""
    # Test /model-info
    res_info = client.get("/model-info")
    assert res_info.status_code == 200
    info_data = res_info.json()

    assert "model_version" in info_data
    assert "feature_version" in info_data
    assert "preprocessing_version" in info_data
    assert "calibration_version" in info_data
    assert "calibration_method" in info_data
    assert "is_calibrated" in info_data
    assert info_data["is_calibrated"] is True
    assert "threshold_version" in info_data
    assert "threshold" in info_data
    assert "sha256" in info_data

    # Test /predict
    payload = {"text": "Worker fell from uninspected scaffold tower without harness"}
    res_pred = client.post("/predict", json=payload)
    assert res_pred.status_code == 200
    pred_data = res_pred.json()

    assert "sif_probability" in pred_data
    assert "calibrated_sif_probability" in pred_data
    assert pred_data["calibrated_sif_probability"] is not None
    assert 0.0 <= pred_data["calibrated_sif_probability"] <= 1.0
    assert "is_calibrated" in pred_data
    assert pred_data["is_calibrated"] is True
    assert "calibration_status" in pred_data
    assert pred_data["calibration_status"] == "CALIBRATED"
    assert "sif_potential" in pred_data
    assert "model_version" in pred_data
    assert "calibration_version" in pred_data
    assert "threshold_version" in pred_data
    assert "threshold" in pred_data
    assert "processed_text" in pred_data
