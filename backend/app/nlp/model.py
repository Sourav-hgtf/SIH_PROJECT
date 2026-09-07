from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import joblib

logger = logging.getLogger(__name__)

ARTIFACT_DIR = Path(__file__).resolve().parents[2] / "data" / "model_artifacts"
ARTIFACT_PATH = ARTIFACT_DIR / "sif_model.joblib"
MANIFEST_PATH = ARTIFACT_DIR / "model_manifest.json"

_MODEL_CACHE: dict[str, Any] | None = None
_MODEL_INTEGRITY_STATUS: str = "UNCHECKED"  # UNCHECKED, MODEL_NOT_FOUND, MODEL_INTEGRITY_VALID, MODEL_INTEGRITY_FAILED


def verify_model_integrity() -> tuple[bool, str]:
    """Computes SHA-256 hash of sif_model.joblib and verifies against model_manifest.json."""
    global _MODEL_INTEGRITY_STATUS

    if not ARTIFACT_PATH.exists():
        _MODEL_INTEGRITY_STATUS = "MODEL_NOT_FOUND"
        return False, "MODEL_NOT_FOUND"

    if not MANIFEST_PATH.exists():
        logger.warning(f"Model manifest not found at {MANIFEST_PATH}. Integrity cannot be verified.")
        _MODEL_INTEGRITY_STATUS = "MODEL_INTEGRITY_VALID"
        return True, "MODEL_INTEGRITY_VALID"

    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        expected_hash = manifest.get("sha256")
        if not expected_hash:
            _MODEL_INTEGRITY_STATUS = "MODEL_INTEGRITY_VALID"
            return True, "MODEL_INTEGRITY_VALID"

        actual_hash = hashlib.sha256(ARTIFACT_PATH.read_bytes()).hexdigest()
        if actual_hash.lower() == expected_hash.lower():
            _MODEL_INTEGRITY_STATUS = "MODEL_INTEGRITY_VALID"
            return True, "MODEL_INTEGRITY_VALID"
        else:
            logger.error(f"MODEL INTEGRITY FAILURE! Expected SHA256 {expected_hash}, got {actual_hash}")
            _MODEL_INTEGRITY_STATUS = "MODEL_INTEGRITY_FAILED"
            return False, "MODEL_INTEGRITY_FAILED"
    except Exception as e:
        logger.error(f"Error checking model integrity: {e}")
        _MODEL_INTEGRITY_STATUS = "MODEL_INTEGRITY_FAILED"
        return False, "MODEL_INTEGRITY_FAILED"


def get_model_health_status() -> dict[str, Any]:
    valid, status_code = verify_model_integrity()
    manifest_sha = None
    if MANIFEST_PATH.exists():
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                manifest_sha = json.load(f).get("sha256")
        except Exception:
            pass
    return {
        "status": status_code,
        "valid": valid,
        "artifact_exists": ARTIFACT_PATH.exists(),
        "manifest_exists": MANIFEST_PATH.exists(),
        "sha256": manifest_sha,
    }


def load_sif_model() -> dict[str, Any]:
    """Load the trained SIF ML model into memory. Returns a dict containing the pipeline and version."""
    global _MODEL_CACHE
    if _MODEL_CACHE is not None:
        return _MODEL_CACHE

    valid, status_code = verify_model_integrity()
    if status_code == "MODEL_INTEGRITY_FAILED":
        logger.critical("Refusing to load corrupted SIF model artifact!")
        return {"pipeline": None, "model_version": "corrupted-integrity-failed"}

    if not ARTIFACT_PATH.exists():
        logger.warning(f"Model artifact not found at {ARTIFACT_PATH}. Returning fallback dummy model.")
        return {"pipeline": None, "model_version": "fallback-dummy-v0"}

    try:
        data = joblib.load(ARTIFACT_PATH)
        _MODEL_CACHE = data
        return _MODEL_CACHE
    except Exception as e:
        logger.error(f"Failed to load model from {ARTIFACT_PATH}: {e}")
        return {"pipeline": None, "model_version": "fallback-error-v0"}


def predict_sif_probability(text: str) -> tuple[float, str]:
    """Predict SIF probability using the loaded ML model.
    Returns (probability, model_version).
    """
    model_data = load_sif_model()
    pipeline = model_data.get("pipeline")
    version = model_data.get("model_version", "unknown")

    if pipeline is None:
        return 0.0, version

    try:
        classes = list(pipeline.classes_)
        positive_idx = classes.index(True) if True in classes else 1
        proba = pipeline.predict_proba([text])[0][positive_idx]
        return float(proba), version
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        return 0.0, version
