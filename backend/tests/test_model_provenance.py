"""Provenance disclosure contracts for model and evaluation metadata."""

import json
from pathlib import Path

from app.database import SessionLocal
from app.training import run_ml_training


def test_training_persists_demo_provenance_in_artifact_manifest_and_evaluation(isolated_model_artifacts):
    db = SessionLocal()
    try:
        run = run_ml_training(db, force_demo_fallback=True)
        metrics = run.metrics_after
        assert metrics["data_provenance"] in {"DEMO_FALLBACK_SYNTHETIC_OR_HEURISTIC", "HUMAN_VALIDATED_NON_SYNTHETIC"}
        report = json.loads(Path(metrics["evaluation_report_path"]).read_text())
        assert report["data_provenance"] == metrics["data_provenance"]
        manifest = json.loads((isolated_model_artifacts / "model_manifest.json").read_text())
        assert manifest["data_provenance"] == metrics["data_provenance"]
    finally:
        db.close()
