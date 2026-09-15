"""Phase 9 complete immutable AI-to-analyst triage workflow."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_token
from app.database import Base, get_db
from app.main import app
from app.models import AnalystDecision, Report, SifClassification, Site, User


def test_triage_progress_tracks_confirm_and_override_without_mutating_ai_prediction():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        Site(id="triage-site", name="Triage Site", region="North"),
        User(id="triage-analyst", username="triage-analyst", password_hash="x", role="analyst", site_scope=["triage-site"]),
    ])
    first = Report(id="triage-r1", source_report_id="T1", report_type="near_miss", site_id="triage-site", raw_text_redacted="first", reported_at=datetime.now(timezone.utc), lifecycle_status="AI_ANALYZED")
    first.classification = SifClassification(sif_probability=0.93, sif_label=True, model_version="test-model")
    second = Report(id="triage-r2", source_report_id="T2", report_type="near_miss", site_id="triage-site", raw_text_redacted="second", reported_at=datetime.now(timezone.utc), lifecycle_status="AI_ANALYZED")
    second.classification = SifClassification(sif_probability=0.20, sif_label=False, model_version="test-model")
    db.add_all([first, second])
    db.commit()
    db.close()

    def override_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    headers = {"Authorization": f"Bearer {create_token('triage-analyst', 'access', 60)}"}
    try:
        with TestClient(app) as client:
            before = client.get("/v1/reports/triage-progress", headers=headers)
            assert before.status_code == 200
            assert before.json() == {"reviewed": 0, "remaining": 2, "confirmed_sif": 0, "overridden": 0}

            confirmed = client.post("/v1/reports/triage-r1/confirm", headers=headers, json={"notes": "Evidence supports SIF"})
            assert confirmed.status_code == 200
            assert confirmed.json()["analyst_decision"]["review_action"] == "CONFIRMED"

            overridden = client.post("/v1/reports/triage-r2/override", headers=headers, json={"final_sif_label": True, "reason": "Escalated energy exposure", "notes": "Analyst review"})
            assert overridden.status_code == 200
            assert overridden.json()["analyst_decision"]["review_action"] == "OVERRIDDEN"

            after = client.get("/v1/reports/triage-progress", headers=headers)
            assert after.status_code == 200
            assert after.json() == {"reviewed": 2, "remaining": 0, "confirmed_sif": 2, "overridden": 1}
    finally:
        app.dependency_overrides.clear()

    verify = Session()
    try:
        ai_rows = verify.query(SifClassification).order_by(SifClassification.report_id).all()
        assert [(row.sif_label, row.sif_probability, row.model_version) for row in ai_rows] == [(True, 0.93, "test-model"), (False, 0.20, "test-model")]
        decisions = verify.query(AnalystDecision).all()
        assert all(decision.analyst_id == "triage-analyst" and decision.reviewed_at for decision in decisions)
        assert any(decision.analyst_comment == "Escalated energy exposure" for decision in decisions)
    finally:
        verify.close()
        Base.metadata.drop_all(engine)
