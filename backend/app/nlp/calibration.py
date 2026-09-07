"""Feedback-driven threshold calibration for the offline prototype classifier.

This intentionally calibrates the existing transparent heuristic rather than
claiming to train a transformer without analyst-validated data.  The artifact
format is small, versioned JSON so it can be replaced by a real model registry
in production without changing ingestion callers.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

BASE_MODEL_VERSION = "weak-supervision-hybrid-v1"
ARTIFACT_PATH = Path(__file__).resolve().parents[2] / "data" / "model_artifacts" / "sif_calibration.json"


def load_active_calibration(default_threshold: float) -> dict:
    """Return the deployed calibration, falling back safely when absent/corrupt."""
    try:
        payload = json.loads(ARTIFACT_PATH.read_text())
        threshold = float(payload["threshold"])
        if not 0.01 <= threshold <= 0.99:
            raise ValueError("threshold outside accepted range")
        return {"threshold": threshold, "model_version": str(payload["model_version"])}
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return {"threshold": default_threshold, "model_version": BASE_MODEL_VERSION}


def classification_metrics(examples: Iterable[tuple[float, bool]], threshold: float) -> dict:
    rows = list(examples)
    tp = sum(score >= threshold and label for score, label in rows)
    fp = sum(score >= threshold and not label for score, label in rows)
    fn = sum(score < threshold and label for score, label in rows)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"sample_size": len(rows), "precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)}


def choose_threshold(examples: list[tuple[float, bool]], fallback_threshold: float) -> tuple[float, dict, dict]:
    """Pick the strongest F1 threshold while preserving high SIF recall.

    Feedback corpora are initially small, so the method is deterministic and
    explainable; it does not pretend a training split is statistically valid.
    """
    before = classification_metrics(examples, fallback_threshold)
    positives = sum(label for _, label in examples)
    if not examples or positives == 0:
        return fallback_threshold, before, before
    candidates = [round(i / 100, 2) for i in range(5, 96, 5)]
    scored = [(classification_metrics(examples, value), value) for value in candidates]
    eligible = [(metrics, value) for metrics, value in scored if metrics["recall"] >= 0.85]
    best_metrics, best_threshold = max(
        eligible or scored,
        key=lambda item: (item[0]["f1"], item[0]["recall"], item[0]["precision"], item[1]),
    )
    return best_threshold, before, best_metrics


def write_calibration(threshold: float, feedback_count: int) -> dict:
    version = f"{BASE_MODEL_VERSION}+calibrated-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    payload = {
        "model_version": version,
        "threshold": threshold,
        "feedback_count": feedback_count,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    return payload
