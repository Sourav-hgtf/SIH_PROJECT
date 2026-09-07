import pytest
from app.database import SessionLocal
from app.models import ReportReview, Report, Site, ModelTrainingRun
from app.services import (
    compute_model_health,
    compute_error_analysis,
    compute_model_version_drift,
    compute_intervention_effectiveness,
    compute_agreement_trend,
)


def test_analytics_empty_db():
    db = SessionLocal()
    try:
        health = compute_model_health(db)
        assert "total_reviewed" in health
        assert "insufficient_data" in health

        errors = compute_error_analysis(db)
        assert "false_positives" in errors
        assert "false_negatives" in errors

        drift = compute_model_version_drift(db)
        assert "versions" in drift

        eff = compute_intervention_effectiveness(db)
        assert "total_recommendations" in eff

        trend = compute_agreement_trend(db)
        assert isinstance(trend, list)
    finally:
        db.close()


def test_sif_density_activity_calculation():
    import uuid
    from app.models import Report, SifClassification, PrecursorTriple, Site
    from app.routers.dashboard import sif_density
    from app.auth import User
    from datetime import datetime, timezone

    db = SessionLocal()
    try:
        # Create test site
        site = db.query(Site).first()
        if not site:
            site = Site(name="Test Site Analytics", region="North")
            db.add(site)
            db.commit()

        uid = str(uuid.uuid4())[:8]
        act_name = f"Unique Test Activity {uid}"

        # Create 2 reports with same activity: 1 SIF=True, 1 SIF=False
        r1 = Report(source_report_id=f"DENS-1-{uid}", report_type="INCIDENT", site_id=site.id, raw_text_redacted="Electrical arc flash near panel", reported_at=datetime.now(timezone.utc))
        r2 = Report(source_report_id=f"DENS-2-{uid}", report_type="HAZARD", site_id=site.id, raw_text_redacted="Minor spill near workshop", reported_at=datetime.now(timezone.utc))
        db.add_all([r1, r2])
        db.commit()

        s1 = SifClassification(report_id=r1.id, sif_probability=0.9, sif_label=True)
        s2 = SifClassification(report_id=r2.id, sif_probability=0.1, sif_label=False)
        p1 = PrecursorTriple(report_id=r1.id, activity=act_name, location_asset="Substation", barrier_failure="LOTO")
        p2 = PrecursorTriple(report_id=r2.id, activity=act_name, location_asset="Substation", barrier_failure="PPE")
        db.add_all([s1, s2, p1, p2])
        db.commit()

        test_user = User(username=f"analyst_test_{uid}", password_hash="pass", role="admin")

        res = sif_density(group_by="activity", db=db, user=test_user)
        match = next((r for r in res if r.group_label == act_name), None)
        assert match is not None
        assert match.sif_count == 1
        assert match.total_count == 2
        assert match.sif_rate == 0.5  # Exactly 1 / 2 = 0.5, NOT 1.0 (100%)
    finally:
        db.close()
