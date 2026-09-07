"""Probability calibration and validation-only threshold optimization.

Implements rigorous ML probability calibration using sklearn's native
CalibratedClassifierCV (cv='prefit', method='sigmoid'):

    1. Sklearn CalibratedClassifierCV (sigmoid / Platt scaling) fitted on held-out
       validation data using cv='prefit' — the base pipeline is first trained on the
       training partition, then the calibrator wraps it and fits the sigmoid layer
       on the separate validation partition.  This matches the definition of
       "calibrated logistic regression" used in this system.
    2. Calibration error metrics: Brier Score, Expected Calibration Error (ECE),
       and cross-entropy log loss — all measured on the validation partition before
       they are reported.
    3. Threshold optimization executed strictly on validation predictions, targeting
       high safety recall (>=0.85) without test set contamination.

Why CalibratedClassifierCV(cv='prefit') instead of full cross-val calibration?
    Using cv='prefit' is correct here because we explicitly control the train /
    validation / test partition upstream (create_leak_free_split) and hand the
    already-fitted pipeline plus the *separate* validation partition to this
    function.  cv='prefit' allows using a pre-fitted base estimator without
    internal refitting, ensuring no data from the validation or test sets leaks
    into the feature extractor (TF-IDF vocabulary) or the logistic regression
    weights.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import brier_score_loss, log_loss

logger = logging.getLogger(__name__)

BASE_CALIBRATION_VERSION = "sklearn-ccv-sigmoid-prefit-v1"
BASE_THRESHOLD_VERSION = "thresh-recall-prioritized-v1"
ARTIFACT_PATH = Path(__file__).resolve().parents[2] / "data" / "model_artifacts" / "sif_calibration.json"


def compute_brier_score(y_true: Sequence[bool], y_prob: Sequence[float]) -> float | None:
    """Compute Brier Score (mean squared error of probability forecasts)."""
    if len(y_true) == 0 or len(y_prob) == 0 or len(y_true) != len(y_prob):
        return None
    try:
        score = brier_score_loss([int(y) for y in y_true], list(y_prob))
        return round(float(score), 4)
    except Exception as e:
        logger.warning(f"Error computing Brier score: {e}")
        return None


def compute_expected_calibration_error(
    y_true: Sequence[bool],
    y_prob: Sequence[float],
    n_bins: int = 5,
) -> float | None:
    """Compute Expected Calibration Error (ECE) across equal-width probability bins."""
    if len(y_true) == 0 or len(y_prob) == 0 or len(y_true) != len(y_prob):
        return None

    y_t = np.array([1 if y else 0 for y in y_true])
    y_p = np.array(list(y_prob), dtype=float)

    n_samples = len(y_t)
    if n_samples == 0:
        return None

    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0

    for i in range(n_bins):
        low, high = bin_edges[i], bin_edges[i + 1]
        mask = (y_p >= low) & (y_p < high) if i < n_bins - 1 else (y_p >= low) & (y_p <= high)
        bin_count = np.sum(mask)

        if bin_count > 0:
            bin_acc = np.mean(y_t[mask])
            bin_conf = np.mean(y_p[mask])
            ece += (bin_count / n_samples) * abs(bin_acc - bin_conf)

    return round(float(ece), 4)


def compute_log_loss(y_true: Sequence[bool], y_prob: Sequence[float]) -> float | None:
    """Compute cross-entropy log loss."""
    if len(y_true) == 0 or len(y_prob) == 0 or len(y_true) != len(y_prob):
        return None
    if len(set(y_true)) < 2:
        return None
    try:
        # Clip probabilities to prevent log(0)
        clipped = np.clip(list(y_prob), 1e-6, 1.0 - 1e-6)
        return round(float(log_loss(y_true, clipped)), 4)
    except Exception as e:
        logger.warning(f"Error computing log loss: {e}")
        return None


def calibrate_classifier(
    base_estimator: Any,
    X_val: Sequence[str],
    y_val: Sequence[bool],
    method: str = "sigmoid",
) -> tuple[Any, str, dict[str, Any]]:
    """Fits sklearn CalibratedClassifierCV(cv='prefit') on held-out validation data.

    The base_estimator must already be fitted on the TRAINING partition.
    CalibratedClassifierCV with cv='prefit' wraps the fitted estimator and fits
    only the sigmoid calibration layer on X_val / y_val, never re-fitting the
    base model weights or TF-IDF vocabulary.

    Returns:
        (calibrated_estimator, calibration_version, calibration_diagnostics)

    calibration_version format: sklearn-ccv-{method}-prefit-v1
    """
    if len(X_val) < 4 or len(set(y_val)) < 2:
        logger.warning(
            "Validation set insufficient for CalibratedClassifierCV (need >=4 samples, both classes present); "
            "returning base estimator uncalibrated."
        )
        return base_estimator, "uncalibrated-insufficient-val-v0", {
            "method": "none",
            "calibrator": "none",
            "brier_score_before": None,
            "brier_score_after": None,
            "ece_before": None,
            "ece_after": None,
        }

    # Measure uncalibrated probabilities on validation set
    try:
        uncal_prob = base_estimator.predict_proba(X_val)[:, 1]
        brier_before = compute_brier_score(y_val, uncal_prob)
        ece_before = compute_expected_calibration_error(y_val, uncal_prob)
        logloss_before = compute_log_loss(y_val, uncal_prob)
    except Exception as e:
        logger.warning(f"Failed to measure uncalibrated metrics: {e}")
        brier_before = ece_before = logloss_before = None

    # Fit CalibratedClassifierCV(cv='prefit') on validation partition only
    try:
        calibrated = CalibratedClassifierCV(
            estimator=base_estimator,
            method=method,       # 'sigmoid' = Platt scaling
            cv="prefit",         # base estimator is already fitted; only the sigmoid layer is trained here
        )
        calibrated.fit(X_val, [1 if y else 0 for y in y_val])

        cal_prob = calibrated.predict_proba(X_val)[:, 1]
        brier_after = compute_brier_score(y_val, cal_prob)
        ece_after = compute_expected_calibration_error(y_val, cal_prob)
        logloss_after = compute_log_loss(y_val, cal_prob)

        cal_version = f"sklearn-ccv-{method}-prefit-v1"

        metrics = {
            "method": method,
            "calibrator": "CalibratedClassifierCV",
            "cv": "prefit",
            "brier_score_before": brier_before,
            "brier_score_after": brier_after,
            "ece_before": ece_before,
            "ece_after": ece_after,
            "log_loss_before": logloss_before,
            "log_loss_after": logloss_after,
            "val_samples_used": len(X_val),
        }

        improvement = (
            round(float(brier_before - brier_after), 4)
            if brier_before is not None and brier_after is not None
            else None
        )
        metrics["brier_score_improvement"] = improvement

        logger.info(
            f"CalibratedClassifierCV(method={method}, cv='prefit') fitted on {len(X_val)} validation samples. "
            f"Brier: {brier_before} → {brier_after}  ECE: {ece_before} → {ece_after}"
        )
        return calibrated, cal_version, metrics

    except Exception as e:
        logger.error(
            f"CalibratedClassifierCV fitting failed: {e}. Falling back to base (uncalibrated) model."
        )
        return base_estimator, "uncalibrated-fit-error-v0", {
            "method": "failed",
            "calibrator": "none",
            "error": str(e),
            "brier_score_before": brier_before,
            "brier_score_after": None,
        }


def classification_metrics(examples: Iterable[tuple[float, bool]], threshold: float) -> dict[str, Any]:
    """Compute precision, recall, and F1 at a specific decision threshold."""
    rows = list(examples)
    tp = sum(score >= threshold and label for score, label in rows)
    fp = sum(score >= threshold and not label for score, label in rows)
    fn = sum(score < threshold and label for score, label in rows)
    tn = sum(score < threshold and not label for score, label in rows)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0

    return {
        "sample_size": len(rows),
        "threshold": round(threshold, 3),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "false_positive_rate": round(fpr, 3),
        "false_negative_rate": round(fnr, 3),
        "tp": int(tp),
        "fp": int(fp),
        "fn": int(fn),
        "tn": int(tn),
    }


def optimize_threshold(
    y_val: Sequence[bool],
    y_val_prob: Sequence[float],
    target_recall: float = 0.85,
    fallback_threshold: float = 0.45,
) -> tuple[float, str, dict[str, Any]]:
    """Optimizes decision threshold strictly on validation set predictions.

    Prioritizes safety: ensures high SIF recall (>=target_recall) while maximizing F1.
    This function MUST only ever be called with validation-set predictions.
    Test set predictions must never be passed here.
    """
    if len(y_val) == 0 or len(y_val_prob) == 0 or len(y_val) != len(y_val_prob):
        return fallback_threshold, "thresh-fallback-default-v1", {"threshold": fallback_threshold}

    examples = list(zip(list(y_val_prob), y_val))
    positives = sum(1 for y in y_val if y)

    if positives == 0:
        logger.warning("No positive SIF examples in validation set; using fallback threshold.")
        return fallback_threshold, "thresh-fallback-no-positives-v1", classification_metrics(examples, fallback_threshold)

    candidates = [round(i / 100, 2) for i in range(10, 91, 5)]
    scored = [(classification_metrics(examples, value), value) for value in candidates]

    # High safety priority: filter candidates satisfying minimum recall
    eligible = [(metrics, value) for metrics, value in scored if metrics["recall"] >= target_recall]

    if eligible:
        best_metrics, best_threshold = max(
            eligible,
            key=lambda item: (item[0]["f1"], item[0]["recall"], item[0]["precision"], -abs(item[1] - fallback_threshold)),
        )
        version = f"thresh-opt-recall-{target_recall}-v1"
    else:
        # Max recall if target cannot be achieved
        best_metrics, best_threshold = max(
            scored,
            key=lambda item: (item[0]["recall"], item[0]["f1"], item[0]["precision"]),
        )
        version = "thresh-max-recall-fallback-v1"

    return best_threshold, version, best_metrics


# --- Backwards compatibility functions ---

def choose_threshold(examples: list[tuple[float, bool]], fallback_threshold: float = 0.45) -> tuple[float, dict, dict]:
    """Legacy helper for threshold optimization."""
    if not examples:
        return fallback_threshold, {}, {}
    probs = [e[0] for e in examples]
    labels = [e[1] for e in examples]
    before = classification_metrics(examples, fallback_threshold)
    best_thresh, _, after = optimize_threshold(labels, probs, fallback_threshold=fallback_threshold)
    return best_thresh, before, after


def load_active_calibration(default_threshold: float = 0.45) -> dict:
    """Return the deployed calibration metadata, falling back safely when absent."""
    try:
        payload = json.loads(ARTIFACT_PATH.read_text())
        threshold = float(payload.get("threshold", default_threshold))
        if not 0.01 <= threshold <= 0.99:
            raise ValueError("threshold outside accepted range")
        return {
            "threshold": threshold,
            "model_version": str(payload.get("model_version", "unknown")),
            "calibration_version": str(payload.get("calibration_version", BASE_CALIBRATION_VERSION)),
            "threshold_version": str(payload.get("threshold_version", BASE_THRESHOLD_VERSION)),
        }
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return {
            "threshold": default_threshold,
            "model_version": "weak-supervision-hybrid-v1",
            "calibration_version": BASE_CALIBRATION_VERSION,
            "threshold_version": BASE_THRESHOLD_VERSION,
        }


def write_calibration(threshold: float, feedback_count: int) -> dict:
    """Legacy write helper for calibration json."""
    payload = {
        "model_version": "weak-supervision-hybrid-v1",
        "calibration_version": BASE_CALIBRATION_VERSION,
        "threshold_version": f"{BASE_THRESHOLD_VERSION}-{threshold}",
        "threshold": threshold,
        "feedback_count": feedback_count,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    return payload
