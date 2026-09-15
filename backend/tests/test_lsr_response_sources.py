"""Regression coverage for LSR provenance returned by report APIs."""

from datetime import UTC, datetime

from app.models import LsrTag
from app.routers.reports import _to_lsr_tag_out
from app.services.core_services import _utc_timestamp


def test_lsr_response_accepts_hybrid_and_semantic_provenance():
    for source in ("hybrid", "semantic"):
        tag = LsrTag(
            report_id="report-1",
            lsr_category="Safe Mechanical Lifting",
            confidence=0.8,
            source=source,
            evidence=[],
        )
        assert _to_lsr_tag_out(tag).source == source


def test_cluster_timestamp_normalization_accepts_sqlite_naive_and_utc_values():
    naive = datetime(2026, 1, 1, 12, 0, 0)
    aware = datetime(2026, 1, 1, 13, 0, 0, tzinfo=UTC)
    assert min(_utc_timestamp(naive), _utc_timestamp(aware)) == _utc_timestamp(naive)
