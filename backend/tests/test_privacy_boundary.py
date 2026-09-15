"""Privacy-by-design tests for the production SIF processing path."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Report, Site, SifClassification
from app.nlp.model import predict_sif_details
from app.nlp.pipeline import process_report_text
from app.nlp.preprocess import contains_detectable_pii, preprocess
from app.training import run_ml_training


@pytest.mark.parametrize(
    "name",
    ["Rahul Kumar", "Amit Das", "Priya Singh", "Sourav Ranjan", "Anil Sharma", "Rakesh Prasad"],
)
def test_south_asian_names_are_removed_from_ai_visible_text(name: str):
    result = preprocess(f"{name} was working at height without a safety harness.")

    assert name not in result["raw_text_redacted"]
    assert name not in result["processed_text"]
    assert "[PERSON]" in result["processed_text"]
    assert result["pii_redacted"] is True
    assert result["pii_replacements"] >= 1


def test_all_required_pii_categories_are_removed_before_processing():
    text = "Rahul Sharma, EMP-44102, 9876543210, rahul@example.com entered a confined space."
    result = preprocess(text)

    for identity in ("Rahul Sharma", "EMP-44102", "9876543210", "rahul@example.com"):
        assert identity not in result["processed_text"]
    assert all(token in result["processed_text"] for token in ("[PERSON]", "[ID]", "[PHONE]", "[EMAIL]"))
    assert not contains_detectable_pii(result["processed_text"])


def test_production_pipeline_sends_only_redacted_text_to_estimator(monkeypatch):
    captured: list[str] = []

    class SafeEstimator:
        classes_ = [False, True]

        def predict_proba(self, values):
            captured.extend(values)
            return [[0.25, 0.75]]

    monkeypatch.setattr(
        "app.nlp.model.load_sif_model",
        lambda: {
            "pipeline": SafeEstimator(),
            "calibrator": None,
            "model_version": "privacy-test-v1",
            "feature_version": "tfidf-unigram-bigram-v1",
            "preprocessing_version": "prep-pii-spell-abbr-v1",
            "calibration_version": "uncalibrated-test-v1",
            "threshold_version": "thresh-test-v1",
            "optimal_threshold": 0.45,
        },
    )

    raw = (
        "Worker: Rahul Sharma\nEmployee ID: OIL12345\nPhone: 9876543210\n"
        "Email: rahul@example.com\n\nWorker entered a confined space without gas testing."
    )
    result = process_report_text(raw)

    assert result["classification"]["sif_probability"] == 0.75
    assert len(captured) == 1
    model_input = captured[0]
    for identity in ("Rahul Sharma", "OIL12345", "9876543210", "rahul@example.com"):
        assert identity not in model_input
    assert "[PERSON]" in model_input
    assert "[ID]" in model_input
    assert "[PHONE]" in model_input
    assert "[EMAIL]" in model_input


def test_prediction_details_never_return_callers_raw_text(monkeypatch):
    class SafeEstimator:
        classes_ = [False, True]

        def predict_proba(self, _values):
            return [[0.25, 0.75]]

    monkeypatch.setattr(
        "app.nlp.model.load_sif_model",
        lambda: {"pipeline": SafeEstimator(), "calibrator": None, "model_version": "privacy-test-v1"},
    )
    details = predict_sif_details("Rahul Sharma entered a confined space.")

    assert "raw_text" not in details
    assert "Rahul Sharma" not in details["processed_text"]


def test_detected_pii_blocks_model_invocation(monkeypatch):
    def should_not_load_model():
        raise AssertionError("model must not be loaded after a privacy-boundary failure")

    monkeypatch.setattr("app.nlp.model.contains_detectable_pii", lambda _text: True)
    monkeypatch.setattr("app.nlp.model.load_sif_model", should_not_load_model)

    details = predict_sif_details("Safe operational narrative.")

    assert details["processing_error"] == "PII_REDACTION_REQUIRED"
    assert details["model_version"] == "not-invoked-privacy-boundary"


def test_training_rejects_record_without_pii_redacted_text(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    db = Session()
    try:
        site = Site(id="privacy-site", name="Privacy Site", region="Test")
        db.add(site)
        report = Report(
            id="privacy-unredacted-record",
            source_report_id="PRIV-001",
            report_type="near_miss",
            site_id=site.id,
            raw_text_redacted="",
            processed_text="Rahul Sharma worked without isolation.",
            reported_at=datetime.now(timezone.utc),
        )
        report.classification = SifClassification(
            sif_probability=0.9, sif_label=True, model_version="privacy-test-v1"
        )
        db.add(report)
        safe_report = Report(
            id="privacy-safe-record",
            source_report_id="PRIV-002",
            report_type="near_miss",
            site_id=site.id,
            raw_text_redacted="Crew verified isolation before maintenance.",
            processed_text="Crew verified isolation before maintenance.",
            reported_at=datetime.now(timezone.utc),
        )
        safe_report.classification = SifClassification(
            sif_probability=0.1, sif_label=False, model_version="privacy-test-v1"
        )
        db.add(safe_report)
        db.commit()

        monkeypatch.setattr("app.training.ARTIFACT_PATH", tmp_path / "sif_model.joblib")
        run = run_ml_training(db, force_demo_fallback=True)

        privacy = run.metrics_after["privacy"]
        assert privacy["training_text_source"] == "raw_text_redacted_only"
        assert privacy["rejected_record_count"] == 1
        assert privacy["rejected_records"] == [
            {"report_id": "privacy-unredacted-record", "reason": "PII_REDACTED_TEXT_REQUIRED"}
        ]
    finally:
        db.close()
