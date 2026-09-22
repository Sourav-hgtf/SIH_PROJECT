"""Contracts for SIF_LIKELY / UNCERTAIN / NON_SIF operational routing."""

from datetime import UTC, datetime

import pytest

from app.models import Report, SifClassification
from app.nlp.classify import classify_sif
from app.nlp.decision import state_for_probability
from app.priority import score_report


@pytest.mark.parametrize(
    ("probability", "expected_state", "review_required"),
    [
        (0.20, "NON_SIF", False),
        (0.35, "UNCERTAIN", True),
        (0.45, "UNCERTAIN", True),
        (0.55, "SIF_LIKELY", False),
        (0.90, "SIF_LIKELY", False),
    ],
)
def test_probability_bands_are_explicit_and_stable(probability, expected_state, review_required):
    assert state_for_probability(probability) == expected_state


@pytest.mark.parametrize(
    ("probability", "expected_state", "review_required", "legacy_sif_label"),
    [
        (0.20, "NON_SIF", False, False),
        (0.45, "UNCERTAIN", True, False),
        (0.80, "SIF_LIKELY", False, True),
    ],
)
def test_classifier_exposes_three_way_state(monkeypatch, probability, expected_state, review_required, legacy_sif_label):
    monkeypatch.setattr(
        "app.nlp.classify.predict_sif_details",
        lambda _text: {
            "sif_probability": probability,
            "calibrated_sif_probability": probability,
            "is_calibrated": True,
            "calibration_status": "CALIBRATED",
            "model_version": "test-model",
            "feature_version": "test-feature",
            "preprocessing_version": "test-preprocess",
            "calibration_version": "test-calibration",
            "threshold_version": "test-threshold",
            "threshold": 0.45,
        },
    )

    result = classify_sif("Live electrical panel with bypassed interlock.")

    assert result["classification_state"] == expected_state
    assert result["requires_analyst_review"] is review_required
    assert result["sif_label"] is legacy_sif_label


def test_uncertain_priority_requires_human_review_before_disposition():
    report = Report(
        id="uncertain-routing-report",
        source_report_id="uncertain-routing-source",
        report_type="near_miss",
        site_id="site-1",
        raw_text_redacted="Potential pressure exposure reported.",
        reported_at=datetime.now(UTC),
    )
    report.classification = SifClassification(
        report_id=report.id,
        sif_probability=0.45,
        sif_label=False,
        classification_state="UNCERTAIN",
        requires_analyst_review=True,
    )

    priority = score_report(report)

    assert priority.classification_state == "UNCERTAIN"
    assert priority.requires_analyst_review is True
    assert "Mandatory analyst review" in priority.action_recommendation
