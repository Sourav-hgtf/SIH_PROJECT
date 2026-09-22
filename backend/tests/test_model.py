from datetime import UTC, datetime

import pytest
from sklearn.pipeline import Pipeline

from app.database import Base, SessionLocal, engine
from app.models import Report, SifClassification
from app.nlp.model import load_sif_model, predict_sif_probability
from app.training import run_ml_training


@pytest.fixture(scope="module")
def setup_test_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    # Insert some dummy labeled reports for training
    from app.models import Site
    site = Site(name="Test Site", region="Test")
    db.add(site)
    db.commit()
    
    # 5 SIF
    for i in range(5):
        r = Report(
            source_report_id=f"test-sif-{i}",
            report_type="incident",
            site_id=site.id,
            raw_text_redacted=f"Terrible accident with energy isolation failure and fall {i}",
            reported_at=datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
        )
        db.add(r)
        db.flush()
        db.add(SifClassification(
            report_id=r.id,
            sif_probability=0.9,
            sif_label=True,
            model_version="heuristic-v1"
        ))
        
    # 5 NON-SIF
    for i in range(5):
        r = Report(
            source_report_id=f"test-safe-{i}",
            report_type="observation",
            site_id=site.id,
            raw_text_redacted=f"Good housekeeping observation safe work {i}",
            reported_at=datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
        )
        db.add(r)
        db.flush()
        db.add(SifClassification(
            report_id=r.id,
            sif_probability=0.1,
            sif_label=False,
            model_version="heuristic-v1"
        ))
        
    db.commit()
    yield db
    
    db.close()


def test_model_training_and_artifact_creation(setup_test_db, isolated_model_artifacts):
    db = setup_test_db
    # Run training
    run = run_ml_training(db, force_demo_fallback=True)
    
    assert run is not None
    assert "sif-logreg-v1" in run.model_version or "tfidf-logreg-v1" in run.model_version
    assert (isolated_model_artifacts / "sif_model.joblib").exists()
    assert (isolated_model_artifacts / "model_manifest.json").exists()

def test_model_loading_and_prediction(setup_test_db, isolated_model_artifacts):
    # Train an isolated artifact; tests must never depend on a previous test's output.
    run_ml_training(setup_test_db, force_demo_fallback=True)
    model_data = load_sif_model()
    
    assert model_data is not None
    assert "pipeline" in model_data
    assert isinstance(model_data["pipeline"], Pipeline)
    assert "sif-logreg-v1" in model_data["model_version"] or "tfidf-logreg-v1" in model_data["model_version"]
    
    # Test prediction
    text = "Terrible accident with energy isolation failure"
    prob, version = predict_sif_probability(text)
    
    assert 0.0 <= prob <= 1.0
    assert "sif-logreg-v1" in version or "tfidf-logreg-v1" in version
    
def test_missing_model_fallback(isolated_model_artifacts):
    # The isolated artifact directory intentionally contains no model.
    import app.nlp.model as model_module
    model_module._MODEL_CACHE = None
    
    model_data = load_sif_model()
    assert model_data["pipeline"] is None
    assert model_data["model_version"] == "fallback-dummy-v0"
