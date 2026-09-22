"""Contracts for versioned, segment-aware model evaluation reporting."""

import pytest

from app.config import settings
from app.training import (
    IncidentDataRecord,
    assert_segment_quality_gates,
    build_evaluation_metrics,
    build_segment_evaluation,
)


def _record(index: int, label: bool, *, site: str = "site-a") -> IncidentDataRecord:
    return IncidentDataRecord(
        id=f"r-{index}", group_id=f"g-{index}", raw_text="redacted", norm_text="redacted",
        text_hash=str(index), label=label, data_type="human_validated", label_source="HUMAN_VALIDATED",
        site_id=site, department="operations", report_type="near_miss",
    )


def test_evaluation_metrics_include_confusion_rates_and_calibration_curve():
    metrics = build_evaluation_metrics([False, False, True, True], [False, True, False, True], [0.1, 0.8, 0.2, 0.9])

    assert metrics["confusion_matrix"] == {"tn": 1, "fp": 1, "fn": 1, "tp": 1}
    assert metrics["precision"] == metrics["recall"] == metrics["f1"] == 0.5
    assert metrics["specificity"] == metrics["false_negative_rate"] == 0.5
    assert metrics["calibration_curve"]


def test_segment_quality_gate_blocks_eligible_underperforming_segment(monkeypatch):
    monkeypatch.setattr(settings, "evaluation_min_segment_size", 4)
    monkeypatch.setattr(settings, "evaluation_min_segment_precision", 0.75)
    monkeypatch.setattr(settings, "evaluation_min_segment_recall", 0.75)
    records = [_record(0, False), _record(1, False), _record(2, True), _record(3, True)]
    segments = build_segment_evaluation(records, [False, True, False, True], [0.1, 0.8, 0.2, 0.9])

    with pytest.raises(ValueError, match="site_id=site-a"):
        assert_segment_quality_gates(segments)
    assert segments["site_id"]["site-a"]["quality_gate"] == "FAILED"
