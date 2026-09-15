"""Phase 8 dashboard filters and report-denominator contracts."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import User
from app.database import Base
from app.models import LsrTag, PrecursorTriple, Report, SifClassification, Site
from app.routers import dashboard
from app.routers.dashboard import FilterParams


@pytest.fixture()
def filtered_db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setattr(dashboard, "score_report", lambda _report, _db: type("Priority", (), {"tier": "HIGH"})())

    alpha = Site(id="site-alpha", name="Alpha", region="North")
    beta = Site(id="site-beta", name="Beta", region="South")
    session.add_all([alpha, beta])
    reports = [
        Report(id="r1", source_report_id="R1", report_type="near_miss", site_id=alpha.id, department="Maintenance", raw_text_redacted="r1", reported_at=datetime(2026, 1, 10, tzinfo=timezone.utc)),
        Report(id="r2", source_report_id="R2", report_type="near_miss", site_id=alpha.id, department="Operations", raw_text_redacted="r2", reported_at=datetime(2026, 2, 10, tzinfo=timezone.utc)),
        Report(id="r3", source_report_id="R3", report_type="near_miss", site_id=beta.id, department="Maintenance", raw_text_redacted="r3", reported_at=datetime(2026, 1, 20, tzinfo=timezone.utc)),
    ]
    session.add_all(reports)
    session.add_all([
        SifClassification(report_id="r1", sif_probability=0.95, sif_label=True),
        SifClassification(report_id="r2", sif_probability=0.40, sif_label=False),
        SifClassification(report_id="r3", sif_probability=0.80, sif_label=True),
        LsrTag(report_id="r1", lsr_category="Energy Isolation", confidence=0.9, source="rule"),
        LsrTag(report_id="r2", lsr_category="Line of Fire", confidence=0.9, source="rule"),
        LsrTag(report_id="r3", lsr_category="Energy Isolation", confidence=0.9, source="rule"),
        # Two triples on r1 intentionally exercise the unique-report rule.
        PrecursorTriple(report_id="r1", activity="Mechanical lifting", location_asset="deck", barrier_failure="Lifting barrier failed"),
        PrecursorTriple(report_id="r1", activity="Mechanical lifting", location_asset="yard", barrier_failure="Lifting barrier failed"),
        PrecursorTriple(report_id="r2", activity="Mechanical lifting", location_asset="deck", barrier_failure="Lifting barrier failed"),
        PrecursorTriple(report_id="r3", activity="Line dismantling", location_asset="wellhead", barrier_failure="Isolation not verified"),
    ])
    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


def _user():
    return User(id="dashboard-admin", username="dashboard-admin", password_hash="x", role="admin", site_scope=[])


@pytest.mark.parametrize(
    ("filters", "expected_total"),
    [
        (FilterParams(start_date=datetime(2026, 1, 1).date(), end_date=datetime(2026, 1, 31).date()), 2),
        (FilterParams(site_id="site-alpha"), 2),
        (FilterParams(department="Maintenance"), 2),
        (FilterParams(min_confidence=0.9), 1),
        (FilterParams(lsr_category="Line of Fire"), 1),
    ],
)
def test_each_dashboard_filter_is_applied_at_report_level(filtered_db, filters, expected_total):
    result = dashboard.kpis(filters=filters, db=filtered_db, user=_user())
    assert result["total_reports"] == expected_total


def test_combined_filters_and_zero_results(filtered_db):
    matching = FilterParams(site_id="site-alpha", department="Maintenance", lsr_category="Energy Isolation", min_confidence=0.9)
    assert dashboard.kpis(filters=matching, db=filtered_db, user=_user())["total_reports"] == 1

    none = FilterParams(site_id="site-alpha", department="Maintenance", lsr_category="Line of Fire", min_confidence=0.9)
    result = dashboard.kpis(filters=none, db=filtered_db, user=_user())
    assert result["total_reports"] == 0
    assert result["sif_rate"] == 0
    assert dashboard.sif_density(filters=none, group_by="activity", db=filtered_db, user=_user()) == []


def test_activity_density_counts_reports_once_and_uses_report_sif_rate(filtered_db):
    rows = dashboard.sif_density(filters=FilterParams(), group_by="activity", db=filtered_db, user=_user())
    lifting = next(row for row in rows if row.group_label == "Mechanical lifting")
    # r1 has two triples, but the activity contains only r1 and r2 reports.
    assert lifting.total_count == 2
    assert lifting.sif_count == 1
    assert lifting.sif_rate == 0.5
