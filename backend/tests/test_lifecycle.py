import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_token
from app.database import Base, get_db
from app.main import app
from app.models import (
    LsrTag,
    PrecursorTriple,
    Recommendation,
    Report,
    ReportReview,
    SifClassification,
    Site,
    User,
    new_id,
    utcnow,
)

TEST_DB_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    site = Site(id="site-test-1", name="Alpha Offshore", region="Assam")
    db.add(site)

    analyst = User(
        id="user-analyst-1",
        username="hse_analyst",
        password_hash="hash",
        role="analyst",
        site_scope=["site-test-1"],
    )
    db.add(analyst)

    report = Report(
        id="rep-lc-01",
        source_report_id="INC-LC-001",
        report_type="near_miss",
        site_id="site-test-1",
        department="Drilling",
        raw_text_redacted="High pressure gas kick observed on drill floor. BOP closed immediately.",
        reported_at=utcnow(),
        lifecycle_status="AI_ANALYZED",
    )
    report.classification = SifClassification(
        sif_probability=0.88,
        sif_label=True,
        model_version="tfidf-logreg-v1-test",
        contributing_phrases=[{"phrase": "high pressure", "weight": 2.5}],
    )
    report.lsr_tags = [
        LsrTag(
            id=new_id(),
            report_id="rep-lc-01",
            lsr_category="Energy Isolation",
            rule_id="LSR-04",
            rule_name="Energy Isolation",
            confidence=0.9,
            source="rule",
        )
    ]
    report.triples = [
        PrecursorTriple(
            id=new_id(),
            report_id="rep-lc-01",
            activity="Drilling operations",
            location_asset="Drill Floor",
            barrier_failure="Wellbore barrier degradation",
        )
    ]
    db.add(report)
    db.commit()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="module")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def analyst_headers(db_session):
    token = create_token("user-analyst-1", "access", 60)
    return {"Authorization": f"Bearer {token}"}


def test_confirm_sif_workflow(client, analyst_headers, db_session):
    # Confirm SIF
    resp = client.post(
        "/v1/reports/rep-lc-01/confirm",
        json={"notes": "Confirmed high pressure gas kick meets SIF criteria"},
        headers=analyst_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["lifecycle_status"] == "CONFIRMED"
    assert data["final_sif_label"] is True
    # Verify AI prediction is immutable
    assert data["sif_probability"] == 0.88
    assert data["sif_label"] is True
    assert data["review"] is not None
    assert data["review"]["decision"] == "CONFIRMED"


def test_override_sif_workflow(client, analyst_headers, db_session):
    # Create second report for override
    rep2 = Report(
        id="rep-lc-02",
        source_report_id="INC-LC-002",
        report_type="near_miss",
        site_id="site-test-1",
        raw_text_redacted="Water puddle on walkway outside office. Wet floor sign deployed.",
        reported_at=utcnow(),
        lifecycle_status="AI_ANALYZED",
    )
    rep2.classification = SifClassification(
        sif_probability=0.55,
        sif_label=True,
        model_version="tfidf-logreg-v1-test",
    )
    db_session.add(rep2)
    db_session.commit()

    # Try override without reason -> should fail with 400
    bad_resp = client.post(
        "/v1/reports/rep-lc-02/override",
        json={"final_sif_label": False, "reason": ""},
        headers=analyst_headers,
    )
    assert bad_resp.status_code == 400

    # Override with proper reason
    resp = client.post(
        "/v1/reports/rep-lc-02/override",
        json={
            "final_sif_label": False,
            "reason": "False positive - surface water with no credible high energy hazard",
            "notes": "Slip hazard only",
        },
        headers=analyst_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["lifecycle_status"] == "OVERRIDDEN"
    assert data["final_sif_label"] is False
    # AI prediction is preserved
    assert data["sif_label"] is True
    assert data["sif_probability"] == 0.55
    assert data["review"]["decision"] == "OVERRIDDEN"
    assert "False positive" in data["review"]["reason"]


def test_lsr_review_preserves_ai_tags(client, analyst_headers, db_session):
    resp = client.post(
        "/v1/reports/rep-lc-01/lsr-review",
        json={"selected_rule_ids": ["LSR-04", "LSR-01"], "reason": "BOP barrier requires energy isolation and bypass controls"},
        headers=analyst_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    # Should have both rule tags and analyst tags
    sources = [t["source"] for t in data["lsr_tags"]]
    assert "analyst" in sources


def test_precursor_review_feedback(client, analyst_headers, db_session):
    resp = client.post(
        "/v1/reports/rep-lc-01/precursor-review",
        json={
            "activity": "Well kill operation",
            "location_asset": "Drill Floor Substructure",
            "barrier_failure": "Primary hydrostatic head underbalance",
            "comment": "Refined barrier failure analysis",
        },
        headers=analyst_headers,
    )
    assert resp.status_code == 200


def test_priority_adjustment(client, analyst_headers, db_session):
    resp = client.post(
        "/v1/reports/rep-lc-01/priority-review",
        json={"priority_tier": "CRITICAL", "reason": "Active well control risk demands immediate intervention"},
        headers=analyst_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["final_priority"] == "CRITICAL"


def test_resolve_and_reopen_workflow(client, analyst_headers, db_session):
    # Resolve without notes -> fails
    bad_res = client.post("/v1/reports/rep-lc-01/resolve", json={"resolution_notes": ""}, headers=analyst_headers)
    assert bad_res.status_code == 400

    # Resolve with notes
    res = client.post(
        "/v1/reports/rep-lc-01/resolve",
        json={"resolution_notes": "Wellbore stabilized and kill fluid weighted up. Dual barriers verified."},
        headers=analyst_headers,
    )
    assert res.status_code == 200
    assert res.json()["lifecycle_status"] == "RESOLVED"

    # Reopen
    reopen_res = client.post(
        "/v1/reports/rep-lc-01/reopen",
        json={"reason": "Secondary pressure spike detected in annulus during post-kill monitoring"},
        headers=analyst_headers,
    )
    assert reopen_res.status_code == 200
    assert reopen_res.json()["lifecycle_status"] == "REOPENED"


def test_case_timeline(client, analyst_headers):
    resp = client.get("/v1/reports/rep-lc-01/timeline", headers=analyst_headers)
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) >= 3
    event_types = [e["event_type"] for e in events]
    assert "INGESTION" in event_types
    assert "AI_ANALYSIS" in event_types
    assert "ANALYST_REVIEW" in event_types


def test_lifecycle_kpis_and_agreement_analytics(client, analyst_headers):
    kpis_resp = client.get("/v1/dashboard/lifecycle-kpis", headers=analyst_headers)
    assert kpis_resp.status_code == 200
    kpis = kpis_resp.json()
    assert "pending_review" in kpis
    assert "confirmed_sif" in kpis
    assert "ai_overrides" in kpis
    assert "agreement_rate" in kpis

    agree_resp = client.get("/v1/dashboard/agreement-analytics", headers=analyst_headers)
    assert agree_resp.status_code == 200
    analytics = agree_resp.json()
    assert analytics["total_reviewed"] >= 2
    assert analytics["confirm_count"] >= 1
    assert analytics["override_count"] >= 1
    assert "False positive" in str(analytics["reason_breakdown"])
