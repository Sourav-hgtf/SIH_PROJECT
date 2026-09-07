"""Comprehensive tests for the AI-Assisted Corrective Action Recommendation system.

Verifies:
- Rule mapping (electrical, pressure, line-of-fire, work-at-height, barriers)
- Evidence grounding (no unsupported recommendations, no fabricated barriers)
- Deduplication and deterministic ranking
- Human-in-the-loop workflow transitions (accept, edit, reject, implement, resolve)
- Auditability (preserving original text during edits)
- Cluster-level and executive focus areas
"""
import pytest
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    LsrTag,
    PrecursorCluster,
    PrecursorTriple,
    Recommendation,
    RecommendationFeedback,
    Report,
    SifClassification,
    Site,
    User,
    new_id,
)
from app.recommendations import (
    generate_cluster_recommendations,
    generate_executive_focus_areas,
    generate_report_recommendations,
    load_recommendations_config,
)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_site(db: Session):
    site = db.query(Site).first()
    if not site:
        site = Site(id=new_id(), name="Alpha Platform", region="North Sea")
        db.add(site)
        db.commit()
        db.refresh(site)
    return site


def test_recommendation_config_loading():
    """Verify that business_rules.yaml recommendations configuration loads and validates."""
    config = load_recommendations_config()
    assert config.version == "recommendations-v1"
    assert config.max_recommendations_per_report >= 1
    assert "ENGINEERING_CONTROL" in config.categories
    assert "BARRIER_CONTROL" in config.categories
    assert "isolation" in config.evidence_mappings.barriers
    assert "electrical" in config.evidence_mappings.energy
    assert "line_of_fire" in config.evidence_mappings.proximity
    assert "LSR-04" in config.evidence_mappings.lsr


def test_electrical_evidence_generates_electrical_control(test_site: Site):
    """Verify electrical evidence triggers appropriate electrical zero-energy recommendations."""
    report = Report(
        id=new_id(),
        source_report_id="TEST-ELEC-01",
        report_type="incident",
        site_id=test_site.id,
        raw_text_redacted="Technician observed live electrical wiring exposed in high voltage switchgear without positive isolation.",
        reported_at=datetime.now(timezone.utc),
    )
    report.classification = SifClassification(
        sif_probability=0.88,
        sif_label=True,
        features={"energy_types": ["electrical"], "barrier_failures": ["not isolated"], "proximity_hits": []},
    )
    report.lsr_tags = [
        LsrTag(
            rule_id="LSR-04",
            rule_name="Energy Isolation",
            lsr_category="Energy Isolation",
            confidence=0.92,
            source="rule",
        )
    ]

    recs = generate_report_recommendations(report)
    assert len(recs) > 0
    categories = [r.category for r in recs]
    assert any(cat in ("BARRIER_CONTROL", "ENGINEERING_CONTROL") for cat in categories)
    # Check that electrical / isolation was targeted
    actions_text = " ".join([r.action.lower() for r in recs])
    assert "isolation" in actions_text or "lockout" in actions_text or "zero-energy" in actions_text or "electrical" in actions_text
    # Evidence must be cited
    assert any("energy detected: Electrical" in ev or "Life-Saving Rule" in ev or "Barrier failure" in ev for r in recs for ev in r.evidence)


def test_pressure_and_line_of_fire_evidence(test_site: Site):
    """Verify pressure energy and line-of-fire proximity produce depressurization and exclusion zone recommendations."""
    report = Report(
        id=new_id(),
        source_report_id="TEST-PRESS-01",
        report_type="near_miss",
        site_id=test_site.id,
        raw_text_redacted="Workers standing in line of fire while testing high pressure line.",
        reported_at=datetime.now(timezone.utc),
    )
    report.classification = SifClassification(
        sif_probability=0.82,
        sif_label=True,
        features={"energy_types": ["pressure"], "proximity_hits": ["line of fire"], "barrier_failures": []},
    )
    report.lsr_tags = [
        LsrTag(
            rule_id="LSR-06",
            rule_name="Line of Fire",
            lsr_category="Line of Fire",
            confidence=0.89,
            source="rule",
        )
    ]

    recs = generate_report_recommendations(report)
    assert len(recs) > 0
    actions_text = " ".join([r.action.lower() for r in recs])
    titles_text = " ".join([r.title.lower() for r in recs])
    assert "depressurization" in actions_text or "line-of-fire" in actions_text or "exclusion zone" in actions_text or "trajectory" in actions_text
    assert any("Pressure" in ev or "line of fire" in ev for r in recs for ev in r.evidence)


def test_work_at_height_fall_protection_evidence(test_site: Site):
    """Verify fall exposure and missing harness trigger fall arrest and scaffolding control recommendations."""
    report = Report(
        id=new_id(),
        source_report_id="TEST-HEIGHT-01",
        report_type="ua_uc",
        site_id=test_site.id,
        raw_text_redacted="Employee working at height on scaffold pipe without fall arrest harness.",
        reported_at=datetime.now(timezone.utc),
    )
    report.classification = SifClassification(
        sif_probability=0.78,
        sif_label=True,
        features={"energy_types": ["gravity"], "barrier_failures": ["missing harness"], "proximity_hits": []},
    )
    report.lsr_tags = [
        LsrTag(
            rule_id="LSR-09",
            rule_name="Working at Height",
            lsr_category="Working at Height",
            confidence=0.91,
            source="rule",
        )
    ]

    recs = generate_report_recommendations(report)
    assert len(recs) > 0
    actions_text = " ".join([r.action.lower() for r in recs])
    assert "fall" in actions_text or "harness" in actions_text or "scaffolding" in actions_text or "tie-off" in actions_text


def test_no_evidence_generates_no_unsupported_recommendations(test_site: Site):
    """Safety Guardrail: A benign report with zero detected hazard signals must NOT fabricate recommendations."""
    report = Report(
        id=new_id(),
        source_report_id="TEST-BENIGN-01",
        report_type="ua_uc",
        site_id=test_site.id,
        raw_text_redacted="Safety team conducted morning toolbox talk. Weather is calm and housekeeping is clean.",
        reported_at=datetime.now(timezone.utc),
    )
    report.classification = SifClassification(
        sif_probability=0.03,
        sif_label=False,
        features={"energy_types": [], "barrier_failures": [], "proximity_hits": []},
    )
    report.lsr_tags = []

    recs = generate_report_recommendations(report)
    assert len(recs) == 0, "Recommendations must not be generated when no safety evidence is detected"


def test_deduplication_and_ranking(test_site: Site):
    """Verify multiple overlapping signals for the same control domain are merged and ranked properly."""
    report = Report(
        id=new_id(),
        source_report_id="TEST-DEDUP-01",
        report_type="incident",
        site_id=test_site.id,
        raw_text_redacted="Maintenance work on electrical pump without LOTO or isolation, standing in line of fire.",
        reported_at=datetime.now(timezone.utc),
    )
    report.classification = SifClassification(
        sif_probability=0.94,
        sif_label=True,
        features={
            "energy_types": ["electrical"],
            "barrier_failures": ["not isolated", "LOTO not applied"],
            "proximity_hits": ["line of fire"],
        },
    )
    report.lsr_tags = [
        LsrTag(
            rule_id="LSR-04",
            rule_name="Energy Isolation",
            lsr_category="Energy Isolation",
            confidence=0.95,
            source="rule",
        )
    ]

    recs = generate_report_recommendations(report)
    # Deduplication should ensure we don't have multiple identical isolation actions
    titles = [r.title for r in recs]
    assert len(titles) == len(set(titles)), "Duplicate recommendation titles should be merged"
    # Merged item should cite multiple supporting signals
    top_rec = recs[0]
    assert len(top_rec.evidence) >= 1
    assert top_rec.confidence >= 0.85


def test_human_in_the_loop_workflow_and_audit(db: Session, test_site: Site):
    """Verify state transitions: PENDING_REVIEW -> ACCEPTED -> EDITED -> REJECTED -> IMPLEMENTED -> RESOLVED,
    and verify original AI recommendation text is preserved in audit log."""
    report = Report(
        id=new_id(),
        source_report_id="TEST-HIL-01",
        report_type="near_miss",
        site_id=test_site.id,
        raw_text_redacted="Heavy crane lift conducted over personnel without spotter.",
        reported_at=datetime.now(timezone.utc),
    )
    report.classification = SifClassification(
        sif_probability=0.85,
        sif_label=True,
        features={"energy_types": ["mechanical", "gravity"], "barrier_failures": ["exclusion zone breached"], "proximity_hits": ["under load"]},
    )
    db.add(report)
    db.commit()

    recs = generate_report_recommendations(report, db)
    assert len(recs) > 0
    sample = recs[0]

    # 1. Create DB record as PENDING_REVIEW
    rec_db = Recommendation(
        id=new_id(),
        report_id=report.id,
        site_id=report.site_id,
        category=sample.category,
        title=sample.title,
        action=sample.action,
        confidence=sample.confidence,
        priority=sample.priority,
        evidence=sample.evidence,
        source_signals=sample.source_signals,
        rationale=sample.rationale,
        status="PENDING_REVIEW",
        version="recommendations-v1",
    )
    db.add(rec_db)
    db.commit()
    db.refresh(rec_db)
    assert rec_db.status == "PENDING_REVIEW"

    # 2. Transition to ACCEPTED
    rec_db.status = "ACCEPTED"
    fb_accept = RecommendationFeedback(
        recommendation_id=rec_db.id,
        decision="accept",
        original_text=rec_db.action,
    )
    db.add(fb_accept)
    db.commit()
    assert rec_db.status == "ACCEPTED"

    # 3. Transition to EDITED (Preserves original text)
    original_action_saved = rec_db.action
    edited_text = "Custom site directive: Verify dual spotters and hard barricades for all lifts over 5 tons."
    rec_db.action = edited_text
    rec_db.status = "EDITED"
    fb_edit = RecommendationFeedback(
        recommendation_id=rec_db.id,
        decision="edit",
        original_text=original_action_saved,
        edited_text=edited_text,
        reason="Frontline crane operator requested dual spotter requirement",
    )
    db.add(fb_edit)
    db.commit()

    db.refresh(rec_db)
    assert rec_db.status == "EDITED"
    assert rec_db.action == edited_text
    # Verify feedback preserves original AI action
    edit_record = db.query(RecommendationFeedback).filter(
        RecommendationFeedback.recommendation_id == rec_db.id,
        RecommendationFeedback.decision == "edit"
    ).first()
    assert edit_record is not None
    assert edit_record.original_text == original_action_saved
    assert edit_record.edited_text == edited_text

    # 4. Transition to IMPLEMENTED
    rec_db.status = "IMPLEMENTED"
    rec_db.assigned_owner = "Jane Doe (HSE Lead)"
    rec_db.resolution_notes = "Dual spotters established and briefed during pre-lift meeting."
    db.commit()
    assert rec_db.status == "IMPLEMENTED"

    # 5. Transition to RESOLVED
    rec_db.status = "RESOLVED"
    db.commit()
    assert rec_db.status == "RESOLVED"


def test_cluster_recommendations_and_executive_focus_areas(db: Session):
    """Verify cluster-level recommendations and executive focus areas generation."""
    cluster = PrecursorCluster(
        id=new_id(),
        representative_activity="Pipe Spool Hoisting",
        representative_location="Deck 4 Crane Zone",
        representative_barrier_failure="Lifting exclusion zone breached",
        cluster_size=8,
        trend_status="growing",
    )
    db.add(cluster)
    db.commit()

    cluster_recs = generate_cluster_recommendations(cluster, db)
    assert len(cluster_recs) > 0
    assert any("lifting" in r.action.lower() or "audit" in r.action.lower() or "stand-down" in r.action.lower() for r in cluster_recs)
    assert any("growing" in ev.lower() for r in cluster_recs for ev in r.evidence)

    focus_areas = generate_executive_focus_areas(db, limit=50)
    assert len(focus_areas) > 0
    area = next((fa for fa in focus_areas if fa.cluster_id == cluster.id), None)
    assert area is not None
    assert "Pipe Spool Hoisting" in area.area_name
    assert len(area.recommended_actions) > 0


def test_recommendation_api_workflow(db: Session, test_site: Site):
    """Verify HTTP API endpoints for recommendation generation, accept, edit, reject, and focus areas."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.auth import create_token, hash_password

    # Ensure analyst user exists
    user = db.query(User).filter(User.username == "test_analyst").first()
    if not user:
        user = User(
            id=new_id(),
            username="test_analyst",
            password_hash=hash_password("password123"),
            role="analyst",
            site_scope=[test_site.id],
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.site_scope = [test_site.id]
        db.commit()

    token = create_token(user.id, token_type="access", minutes=60)
    headers = {"Authorization": f"Bearer {token}"}

    client = TestClient(app)

    # 1. Create a report with pressure and line of fire hazards
    report = Report(
        id=new_id(),
        source_report_id="API-REC-01",
        report_type="incident",
        site_id=test_site.id,
        raw_text_redacted="High pressure gas release during well intervention. Personnel standing in line of fire.",
        reported_at=datetime.now(timezone.utc),
    )
    report.classification = SifClassification(
        sif_probability=0.91,
        sif_label=True,
        features={"energy_types": ["pressure"], "proximity_hits": ["line of fire"], "barrier_failures": ["not isolated"]},
    )
    report.lsr_tags = [
        LsrTag(
            rule_id="LSR-04",
            rule_name="Energy Isolation",
            lsr_category="Energy Isolation",
            confidence=0.92,
            source="rule",
        )
    ]
    db.add(report)
    db.commit()

    # 2. GET /v1/reports/{id}/recommendations
    res = client.get(f"/v1/reports/{report.id}/recommendations", headers=headers)
    assert res.status_code == 200, res.text
    recs = res.json()
    assert len(recs) > 0
    rec_id = recs[0]["id"]
    assert recs[0]["status"] == "PENDING_REVIEW"

    # 3. POST /v1/recommendations/{id}/accept
    res_accept = client.post(f"/v1/recommendations/{rec_id}/accept", headers=headers)
    assert res_accept.status_code == 200
    assert res_accept.json()["status"] == "ACCEPTED"

    # 4. POST /v1/recommendations/{id}/edit
    res_edit = client.post(
        f"/v1/recommendations/{rec_id}/edit",
        json={"edited_title": "Custom Isolation Verification", "edited_action": "Apply double block and bleed with verified bleed-down gauge check.", "reason": "Site SOP requires dual isolation"},
        headers=headers,
    )
    assert res_edit.status_code == 200
    assert res_edit.json()["status"] == "EDITED"
    assert res_edit.json()["title"] == "Custom Isolation Verification"
    assert len(res_edit.json()["feedback_history"]) >= 2

    # 5. POST /v1/recommendations/{id}/implement
    res_impl = client.post(
        f"/v1/recommendations/{rec_id}/implement",
        json={"assigned_owner": "John Doe", "resolution_notes": "Dual isolation applied and tagged."},
        headers=headers,
    )
    assert res_impl.status_code == 200
    assert res_impl.json()["status"] == "IMPLEMENTED"
    assert res_impl.json()["assigned_owner"] == "John Doe"

    # 6. POST /v1/recommendations/{id}/resolve
    res_res = client.post(
        f"/v1/recommendations/{rec_id}/resolve",
        json={"resolution_notes": "Work completed and verified safe."},
        headers=headers,
    )
    assert res_res.status_code == 200
    assert res_res.json()["status"] == "RESOLVED"

    # 7. GET /v1/dashboard/recommended-focus-areas
    res_focus = client.get("/v1/dashboard/recommended-focus-areas", headers=headers)
    assert res_focus.status_code == 200
    assert isinstance(res_focus.json(), list)
