"""Tests for Defensible Human-Validated SIF Labelling Workflow (Task 2).

Covers:
1. Reviewer authorization (authorized HSE roles vs unauthorized).
2. Label creation, state validation (SIF, NON_SIF, UNCERTAIN), and mandatory reason.
3. Immutable review versioning (never overwriting previous reviews).
4. Multi-reviewer consensus policy (2 agreeing reviewers = VALIDATED gold label).
5. Reviewer disagreement handling and senior HSE adjudication.
6. Inter-rater agreement calculation (Cohen's Kappa).
7. Audit log generation for every label review.
8. Preventing synthetic / unvalidated records from becoming gold labels or leaking into production ML training.
9. Human-in-the-loop classification: AI prediction preserved, analyst decision separate.
10. Confirmed SIF, overridden SIF, confirmed non-SIF, analyst decision without AI prediction.
"""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import joinedload, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_token
from app.database import Base, get_db
from app.main import app
from app.migrations import run_feedback_migrations, run_labeling_migrations, run_lsr_migrations, run_recommendation_migrations
from app.models import (
    AnalystDecision,
    AuditLog,
    LabelReview,
    Report,
    SifClassification,
    Site,
    User,
    utcnow,
)
from app.services.label_service import (
    calculate_cohens_kappa,
    get_report_label_history,
    get_reviewer_agreement_summary,
    record_label_review,
)
from app.training import run_ml_training

TEST_DB_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module")
def setup_db():
    Base.metadata.create_all(bind=engine)
    run_lsr_migrations(engine)
    run_recommendation_migrations(engine)
    run_labeling_migrations(engine)
    run_feedback_migrations(engine)
    db = TestingSessionLocal()

    site = Site(id="site-test-lab", name="Labelling Test Facility", region="Mumbai")
    db.add(site)

    analyst1 = User(
        id="user-analyst-1",
        username="analyst_1",
        password_hash="hash",
        role="analyst",
        site_scope=["site-test-lab"],
    )
    analyst2 = User(
        id="user-analyst-2",
        username="analyst_2",
        password_hash="hash",
        role="analyst",
        site_scope=["site-test-lab"],
    )
    senior_hse = User(
        id="user-senior-hse",
        username="senior_hse",
        password_hash="hash",
        role="admin",
        site_scope=[],
    )
    technician = User(
        id="user-technician",
        username="tech_worker",
        password_hash="hash",
        role="technician",
        site_scope=["site-test-lab"],
    )
    db.add_all([analyst1, analyst2, senior_hse, technician])

    # Report 1: Initial unreviewed incident with synthetic heuristic prediction
    rep1 = Report(
        id="rep-label-001",
        source_report_id="INC-LAB-001",
        report_type="incident",
        site_id="site-test-lab",
        department="Operations",
        raw_text_redacted="Uncontrolled gas kick during casing operation. Crew evacuated floor.",
        reported_at=utcnow(),
        lifecycle_status="AI_ANALYZED",
        human_label="UNLABELED",
        validated_label=None,
        label_source="UNLABELED",
        validation_status="UNLABELED",
        data_type="synthetic",
    )
    rep1.classification = SifClassification(
        sif_probability=0.82,
        sif_label=True,
        model_version="heuristic-v1",
        classified_at=utcnow(),
    )
    db.add(rep1)
    db.commit()

    yield db
    db.close()


@pytest.fixture(scope="module")
def client(setup_db):
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def make_auth_header(user_id: str) -> dict[str, str]:
    token = create_token(user_id, "access", 60)
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# 1. REVIEWER AUTHORIZATION TESTS
# ==============================================================================

def test_unauthorized_role_cannot_submit_label_review(client):
    headers = make_auth_header("user-technician")
    res = client.post(
        "/v1/reports/rep-label-001/label-review",
        headers=headers,
        json={
            "label": "SIF",
            "reason": "Technician perspective on risk",
        },
    )
    assert res.status_code == 403


def test_authorized_analyst_can_submit_label_review(client):
    headers = make_auth_header("user-analyst-1")
    res = client.post(
        "/v1/reports/rep-label-001/label-review",
        headers=headers,
        json={
            "label": "SIF",
            "reason": "High pressure gas kick without secondary barrier in place",
            "notes": "Verified against well control SIF criteria",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["human_label"] == "SIF"
    assert data["validation_status"] == "PENDING_CONSENSUS"
    assert data["validated_label"] is None  # Single review does not produce gold label without consensus


# ==============================================================================
# 2. MANDATORY REASON & LABEL VALIDATION TESTS
# ==============================================================================

def test_mandatory_reason_enforced(client):
    headers = make_auth_header("user-analyst-1")
    # Empty reason
    res = client.post(
        "/v1/reports/rep-label-001/label-review",
        headers=headers,
        json={
            "label": "SIF",
            "reason": "   ",
        },
    )
    assert res.status_code == 400
    assert "reason is mandatory" in res.json()["detail"].lower()


def test_invalid_label_state_rejected(client):
    headers = make_auth_header("user-analyst-1")
    res = client.post(
        "/v1/reports/rep-label-001/label-review",
        headers=headers,
        json={
            "label": "MAYBE_SIF",
            "reason": "Invalid category test",
        },
    )
    assert res.status_code == 400
    assert "invalid label" in res.json()["detail"].lower()


# ==============================================================================
# 3. IMMUTABLE VERSIONING & PRESERVING HISTORY
# ==============================================================================

def test_immutable_review_versioning(setup_db, client):
    db = setup_db
    # Analyst 1 updates their review with new notes
    token = create_token("user-analyst-1", "access", 60)
    res = client.post(
        "/v1/reports/rep-label-001/label-review",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "label": "SIF",
            "reason": "Updated reason: Verified well control barrier breach",
            "notes": "Version 2 of review",
        },
    )
    assert res.status_code == 200

    # Fetch history
    hist_res = client.get(
        "/v1/reports/rep-label-001/label-history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert hist_res.status_code == 200
    hist = hist_res.json()
    assert hist["total_reviews"] >= 2
    # Verify versions are sequential (v1, v2)
    versions = [r["review_version"] for r in hist["reviews"]]
    assert 1 in versions
    assert 2 in versions


# ==============================================================================
# 4. MULTI-REVIEWER CONSENSUS (2 AGREEING REVIEWERS = GOLD LABEL)
# ==============================================================================

def test_two_agreeing_reviewers_produce_gold_validated_label(client):
    # Reviewer 2 (independent analyst) also marks SIF
    token = create_token("user-analyst-2", "access", 60)
    res = client.post(
        "/v1/reports/rep-label-001/label-review",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "label": "SIF",
            "reason": "Independent confirmation: Well kick with release of energy meets SIF criteria",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["validation_status"] == "VALIDATED"
    assert data["validated_label"] == "SIF"
    assert data["label_source"] == "CONSENSUS_VALIDATED"
    assert data["final_sif_label"] is True


# ==============================================================================
# 5. DISAGREEMENT AND SENIOR HSE ADJUDICATION
# ==============================================================================

def test_disagreement_and_senior_adjudication(setup_db, client):
    db = setup_db
    # Create Report 2 for disagreement test
    rep2 = Report(
        id="rep-label-002",
        source_report_id="INC-LAB-002",
        report_type="incident",
        site_id="site-test-lab",
        department="Maintenance",
        raw_text_redacted="Hydraulic hose rupture during pressure testing. Safety shield contained spray.",
        reported_at=utcnow(),
        lifecycle_status="AI_ANALYZED",
        human_label="UNLABELED",
        validated_label=None,
        label_source="UNLABELED",
        validation_status="UNLABELED",
        data_type="synthetic",
    )
    db.add(rep2)
    db.commit()

    # Reviewer 1 (analyst 1) says SIF
    token1 = create_token("user-analyst-1", "access", 60)
    client.post(
        "/v1/reports/rep-label-002/label-review",
        headers={"Authorization": f"Bearer {token1}"},
        json={"label": "SIF", "reason": "High hydraulic pressure hazard"},
    )

    # Reviewer 2 (analyst 2) says NON_SIF
    token2 = create_token("user-analyst-2", "access", 60)
    res2 = client.post(
        "/v1/reports/rep-label-002/label-review",
        headers={"Authorization": f"Bearer {token2}"},
        json={"label": "NON_SIF", "reason": "Safety shield fully contained spray; no exposure path"},
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["validation_status"] == "DISAGREEMENT"
    assert data2["validated_label"] is None  # Must NOT be gold validated
    assert data2["label_source"] == "DISAGREEMENT"

    # Senior HSE adjudicates the disagreement
    senior_token = create_token("user-senior-hse", "access", 60)
    res_senior = client.post(
        "/v1/reports/rep-label-002/label-review",
        headers={"Authorization": f"Bearer {senior_token}"},
        json={
            "label": "NON_SIF",
            "reason": "Senior arbitration: Engineering barrier prevented credible fatal exposure",
            "notes": "Adjudicated conflict between analyst_1 and analyst_2",
        },
    )
    assert res_senior.status_code == 200
    data_senior = res_senior.json()
    assert data_senior["validation_status"] == "VALIDATED"
    assert data_senior["validated_label"] == "NON_SIF"
    assert data_senior["label_source"] == "SENIOR_HSE_OVERRIDE"


# ==============================================================================
# 6. INTER-RATER AGREEMENT (COHEN'S KAPPA)
# ==============================================================================

def test_cohens_kappa_calculation():
    # Perfect agreement
    r1 = ["SIF", "NON_SIF", "SIF", "NON_SIF"]
    r2 = ["SIF", "NON_SIF", "SIF", "NON_SIF"]
    k_perf = calculate_cohens_kappa(r1, r2)
    assert k_perf["cohens_kappa"] == 1.0
    assert k_perf["observed_agreement"] == 1.0

    # Total disagreement
    r3 = ["SIF", "SIF"]
    r4 = ["NON_SIF", "NON_SIF"]
    k_dis = calculate_cohens_kappa(r3, r4)
    assert k_dis["observed_agreement"] == 0.0


def test_reviewer_agreement_endpoint(client):
    token = create_token("user-analyst-1", "access", 60)
    res = client.get("/v1/reports/reviewer-agreement", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert "cohens_kappa" in data
    assert "observed_agreement" in data
    assert "multi_reviewed_reports" in data
    assert data["multi_reviewed_reports"] >= 1


# ==============================================================================
# 7. AUDIT LOGGING FOR EVERY LABEL CHANGE
# ==============================================================================

def test_audit_log_created_for_label_review(setup_db):
    db = setup_db
    audits = (
        db.query(AuditLog)
        .filter(AuditLog.action_type == "label_review_submitted")
        .all()
    )
    assert len(audits) >= 1
    sample = audits[0]
    assert sample.entity_type == "report"
    assert "human_label" in sample.after_value
    assert "validated_label" in sample.after_value
    assert "reason" in sample.after_value


# ==============================================================================
# 8. TRAINING GUARD: SYNTHETIC / UNVALIDATED NEVER LEAK INTO PRODUCTION TRAINING
# ==============================================================================

def test_training_rejects_unvalidated_or_synthetic_data(setup_db):
    db = setup_db
    # Create an isolated clean DB without any validated human labels
    empty_engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(bind=empty_engine)
    run_lsr_migrations(empty_engine)
    run_labeling_migrations(empty_engine)
    EmptySession = sessionmaker(bind=empty_engine)
    empty_db = EmptySession()

    site = Site(id="site-clean", name="Clean Site", region="Assam")
    empty_db.add(site)

    # Add only synthetic / unvalidated reports
    rep_synth = Report(
        id="rep-pure-synthetic",
        source_report_id="SYNTH-999",
        report_type="incident",
        site_id="site-clean",
        department="Drilling",
        raw_text_redacted="Synthetic incident text without human review.",
        reported_at=utcnow(),
        human_label="UNLABELED",
        validated_label=None,  # Not validated!
        label_source="UNLABELED",
        validation_status="UNLABELED",
        data_type="synthetic",
    )
    empty_db.add(rep_synth)
    empty_db.commit()

    # In production mode (force_demo_fallback=False), training MUST raise ValueError
    # to protect production ML models from unvalidated synthetic data contamination
    with pytest.raises(ValueError, match="No validated human-labelled records found for production training."):
        run_ml_training(empty_db, force_demo_fallback=False)

    empty_db.close()


# ==============================================================================
# 9. HUMAN-IN-THE-LOOP CLASSIFICATION: AI PREDICTION PRESERVED
# ==============================================================================

def test_confirmed_sif_preserves_ai_prediction(client, setup_db):
    """When analyst confirms SIF, AI prediction must be preserved unchanged."""
    db = setup_db
    token = create_token("user-analyst-1", "access", 60)
    report_id = "rep-label-001"
    report = db.get(Report, report_id)
    clf = report.classification
    original_ai_probability = clf.sif_probability
    original_ai_label = clf.sif_label
    original_model_version = clf.model_version

    resp = client.post(
        f"/v1/reports/{report_id}/confirm",
        headers={"Authorization": f"Bearer {token}"},
        json={"notes": "Confirmed SIF assessment"},
    )
    assert resp.status_code == 200
    data = resp.json()

    # AI prediction must be preserved
    assert data["sif_probability"] == original_ai_probability
    assert data["sif_label"] == original_ai_label
    assert data["model_version"] == original_model_version
    assert data["ai_prediction"]["ai_probability"] == original_ai_probability
    assert data["ai_prediction"]["ai_label"] == original_ai_label
    assert data["ai_prediction"]["model_version"] == original_model_version

    # Analyst decision must be recorded
    assert data["analyst_decision"] is not None
    assert data["analyst_decision"]["review_action"] == "CONFIRMED"
    assert data["analyst_decision"]["analyst_label"] == original_ai_label

    # AnalystDecision record must exist
    decisions = db.query(AnalystDecision).filter(AnalystDecision.report_id == report_id).order_by(AnalystDecision.reviewed_at.desc()).all()
    assert len(decisions) >= 1
    assert decisions[0].review_action == "CONFIRMED"
    assert decisions[0].ai_sif_probability_at_time == original_ai_probability

    # SifClassification must NOT be modified
    db.refresh(clf)
    assert clf.sif_probability == original_ai_probability
    assert clf.sif_label == original_ai_label
    assert clf.model_version == original_model_version


def test_overridden_sif_preserves_ai_prediction(client, setup_db):
    """When analyst overrides SIF, AI prediction must be preserved unchanged."""
    db = setup_db
    token = create_token("user-analyst-1", "access", 60)

    # Create a separate report for override testing
    report_id = "rep-label-005"
    report = Report(
        id=report_id,
        source_report_id="INC-LAB-005",
        report_type="incident",
        site_id="site-test-lab",
        department="Operations",
        raw_text_redacted="Pressure vessel showing signs of fatigue cracking.",
        reported_at=utcnow(),
        lifecycle_status="AI_ANALYZED",
        human_label="UNLABELED",
        validated_label=None,
        label_source="UNLABELED",
        validation_status="UNLABELED",
        data_type="synthetic",
    )
    report.classification = SifClassification(
        sif_probability=0.75,
        sif_label=True,
        model_version="heuristic-v1",
        classified_at=utcnow(),
    )
    db.add(report)
    db.commit()
    # Reload with classification joined
    report = db.query(Report).options(joinedload(Report.classification)).filter(Report.id == report_id).first()
    clf = report.classification
    original_ai_probability = clf.sif_probability
    original_ai_label = clf.sif_label

    resp = client.post(
        f"/v1/reports/{report_id}/override",
        headers={"Authorization": f"Bearer {token}"},
        json={"final_sif_label": False, "reason": "False positive - no credible fatal exposure", "notes": "Surface hazard only"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # AI prediction must be preserved
    assert data["sif_probability"] == original_ai_probability
    assert data["sif_label"] == original_ai_label
    assert data["ai_prediction"]["ai_probability"] == original_ai_probability
    assert data["ai_prediction"]["ai_label"] == original_ai_label

    # Analyst decision must reflect override
    decisions = db.query(AnalystDecision).filter(AnalystDecision.report_id == report_id).order_by(AnalystDecision.reviewed_at.desc()).all()
    assert len(decisions) >= 1
    assert decisions[0].review_action == "OVERRIDDEN"
    assert decisions[0].analyst_label is False

    # SifClassification must NOT be modified
    db.refresh(clf)
    assert clf.sif_probability == original_ai_probability
    assert clf.sif_label == original_ai_label

    # AI prediction must be preserved
    assert data["sif_probability"] == original_ai_probability
    assert data["sif_label"] == original_ai_label
    assert data["ai_prediction"]["ai_probability"] == original_ai_probability
    assert data["ai_prediction"]["ai_label"] == original_ai_label

    # Analyst decision must reflect override
    decisions = db.query(AnalystDecision).filter(AnalystDecision.report_id == report_id).order_by(AnalystDecision.reviewed_at.desc()).all()
    assert len(decisions) >= 1
    assert decisions[0].review_action == "OVERRIDDEN"
    assert decisions[0].analyst_label is False

    # SifClassification must NOT be modified
    db.refresh(clf)
    assert clf.sif_probability == original_ai_probability
    assert clf.sif_label == original_ai_label


def test_confirmed_non_sif_preserves_ai_prediction(client, setup_db):
    """When analyst confirms NON-SIF, AI prediction must be preserved."""
    db = setup_db
    token = create_token("user-analyst-1", "access", 60)

    # Create a non-SIF report
    rep2 = Report(
        id="rep-label-003",
        source_report_id="INC-LAB-003",
        report_type="incident",
        site_id="site-test-lab",
        department="Maintenance",
        raw_text_redacted="Minor spill on walkway. Wet floor sign deployed.",
        reported_at=utcnow(),
        lifecycle_status="AI_ANALYZED",
    )
    rep2.classification = SifClassification(
        sif_probability=0.15,
        sif_label=False,
        model_version="heuristic-v1",
        classified_at=utcnow(),
    )
    db.add(rep2)
    db.commit()

    resp = client.post(
        f"/v1/reports/rep-label-003/confirm",
        headers={"Authorization": f"Bearer {token}"},
        json={"notes": "Confirmed non-SIF assessment"},
    )
    assert resp.status_code == 200
    data = resp.json()

    # AI prediction must be preserved
    assert data["sif_probability"] == 0.15
    assert data["sif_label"] is False
    assert data["ai_prediction"]["ai_probability"] == 0.15
    assert data["ai_prediction"]["ai_label"] is False

    # Analyst decision must be recorded
    assert data["analyst_decision"] is not None
    assert data["analyst_decision"]["review_action"] == "CONFIRMED"
    assert data["analyst_decision"]["analyst_label"] is False

    # SifClassification must NOT be modified
    clf = rep2.classification
    db.refresh(clf)
    assert clf.sif_probability == 0.15
    assert clf.sif_label is False


def test_analyst_decision_without_ai_prediction(client, setup_db):
    """When analyst submits a label review on a report with no AI classification,
    the analyst decision must still be recorded with null AI fields."""
    db = setup_db
    token = create_token("user-analyst-1", "access", 60)

    # Create a report without AI classification
    rep_no_ai = Report(
        id="rep-label-004",
        source_report_id="INC-LAB-004",
        report_type="incident",
        site_id="site-test-lab",
        department="Operations",
        raw_text_redacted="Incident text without AI analysis.",
        reported_at=utcnow(),
        lifecycle_status="AI_ANALYZED",
    )
    db.add(rep_no_ai)
    db.commit()

    resp = client.post(
        f"/v1/reports/rep-label-004/label-review",
        headers={"Authorization": f"Bearer {token}"},
        json={"label": "SIF", "reason": "Analyst determination without AI prediction"},
    )
    assert resp.status_code == 200
    data = resp.json()

    # AI prediction should be None
    assert data["ai_prediction"] is None

    # Analyst decision must still be recorded
    assert data["analyst_decision"] is not None
    assert data["analyst_decision"]["review_action"] == "LABELED"
    assert data["analyst_decision"]["analyst_label"] is True

    # AnalystDecision record must have null AI fields
    decisions = db.query(AnalystDecision).filter(AnalystDecision.report_id == "rep-label-004").all()
    assert len(decisions) >= 1
    assert decisions[0].ai_sif_label_at_time is None
    assert decisions[0].ai_sif_probability_at_time is None
    assert decisions[0].analyst_label is True


def test_feedback_does_not_modify_ai_probability(client, setup_db):
    """The /feedback endpoint must NOT modify SifClassification sif_probability or sif_label."""
    db = setup_db
    token = create_token("user-analyst-1", "access", 60)
    report_id = "rep-label-001"
    report = db.get(Report, report_id)
    clf = report.classification
    original_probability = clf.sif_probability
    original_label = clf.sif_label

    resp = client.post(
        "/v1/feedback",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "report_id": report_id,
            "feedback_type": "confirm_sif",
            "new_value": {"sif_label": True, "confirmed": True},
            "comment": "Confirming SIF",
            "review_action": "CONFIRMED",
        },
    )
    assert resp.status_code == 201

    # SifClassification must NOT be modified
    db.refresh(clf)
    assert clf.sif_probability == original_probability
    assert clf.sif_label == original_label

# AnalystDecision must exist
    decisions = db.query(AnalystDecision).filter(AnalystDecision.report_id == report_id).order_by(AnalystDecision.reviewed_at.desc()).all()
    assert len(decisions) >= 1
    assert decisions[0].review_action == "CONFIRMED"


def test_ai_prediction_immutability_through_label_review(client, setup_db):
    """Label review must not modify the SifClassification table."""
    db = setup_db
    token = create_token("user-analyst-1", "access", 60)
    report_id = "rep-label-001"
    report = db.get(Report, report_id)
    clf = report.classification
    original_probability = clf.sif_probability
    original_label = clf.sif_label

    resp = client.post(
        f"/v1/reports/{report_id}/label-review",
        headers={"Authorization": f"Bearer {token}"},
        json={"label": "NON_SIF", "reason": "Analyst disagrees with AI"},
    )
    assert resp.status_code == 200

    # SifClassification must NOT be modified
    db.refresh(clf)
    assert clf.sif_probability == original_probability
    assert clf.sif_label == original_label

    # AnalystDecision must have recorded the original AI prediction
    decisions = db.query(AnalystDecision).filter(AnalystDecision.report_id == report_id).order_by(AnalystDecision.reviewed_at.desc()).all()
    assert len(decisions) >= 1
    last_decision = decisions[0]
    assert last_decision.ai_sif_probability_at_time == original_probability
    assert last_decision.ai_sif_label_at_time == original_label
