import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import Base, engine
from app.migrations import (
    run_feedback_migrations,
    run_labeling_migrations,
    run_lsr_migrations,
    run_recommendation_migrations,
)

Base.metadata.create_all(bind=engine)
run_lsr_migrations(engine)
run_recommendation_migrations(engine)
run_labeling_migrations(engine)
run_feedback_migrations(engine)


@pytest.fixture
def isolated_model_artifacts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect training and inference artifact I/O away from production files."""
    from app import training
    from app.nlp import model

    artifact_dir = tmp_path / "model_artifacts"
    artifact_path = artifact_dir / "sif_model.joblib"
    manifest_path = artifact_dir / "model_manifest.json"

    monkeypatch.setattr(training, "ARTIFACT_PATH", artifact_path)
    monkeypatch.setattr(model, "ARTIFACT_PATH", artifact_path)
    monkeypatch.setattr(model, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(model, "_MODEL_CACHE", None)
    yield artifact_dir
    model._MODEL_CACHE = None
