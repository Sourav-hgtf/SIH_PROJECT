import numpy as np
import pytest
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from app.nlp.calibration import (
    calibrate_classifier,
    choose_threshold,
    classification_metrics,
    compute_brier_score,
    compute_expected_calibration_error,
    compute_log_loss,
    compute_calibration_curve_data,
    optimize_threshold,
    select_calibration_method,
)


def test_calibration_metrics_and_threshold_prioritize_sif_recall():
    examples = [(0.92, True), (0.81, True), (0.44, True), (0.39, False), (0.18, False)]
    threshold, before, after = choose_threshold(examples, fallback_threshold=0.45)
    assert before == classification_metrics(examples, 0.45)
    assert after["recall"] >= 0.85
    assert 0.05 <= threshold <= 0.95


def test_calibration_keeps_existing_threshold_without_positive_feedback():
    threshold, before, after = choose_threshold([(0.2, False), (0.4, False)], fallback_threshold=0.45)
    assert threshold == 0.45
    assert before == after


def test_select_calibration_method():
    """Verify method selection uses sigmoid for small sets and isotonic only for large sets."""
    assert select_calibration_method(50) == "sigmoid"
    assert select_calibration_method(500) == "sigmoid"
    assert select_calibration_method(999) == "sigmoid"
    assert select_calibration_method(1000) == "isotonic"
    assert select_calibration_method(5000) == "isotonic"
    assert select_calibration_method(50, requested_method="isotonic") == "isotonic"


def test_calibrate_classifier_sigmoid_success():
    """Test successful probability calibration using validation data with FrozenEstimator."""
    # Create base fitted pipeline
    base_pipe = Pipeline([
        ("tfidf", TfidfVectorizer()),
        ("clf", LogisticRegression(random_state=42)),
    ])
    X_train = [
        "high pressure gas blowout and fire at wellhead",
        "routine safety inspection of walkway",
        "heavy dropped object near drill floor",
        "minor office housekeeping checklist completed",
        "toxic hydrogen sulfide gas leak detected",
        "regular tool check in storage room",
    ]
    y_train = [True, False, True, False, True, False]
    base_pipe.fit(X_train, y_train)

    X_val = [
        "catastrophic explosion on drilling rig",
        "clean oil spill absorbent pads safely stored",
        "worker fell into open sump pit without harness",
        "routine lighting audit on perimeter fence",
    ]
    y_val = [True, False, True, False]

    calibrator, cal_version, diag = calibrate_classifier(base_pipe, X_val, y_val, method="sigmoid")

    assert "sklearn-ccv-sigmoid-v1" in cal_version
    assert diag["is_calibrated"] is True
    assert diag["status"] == "CALIBRATED"
    assert diag["method"] == "sigmoid"
    assert diag["brier_score_before"] is not None
    assert diag["brier_score_after"] is not None
    assert diag["val_samples_used"] == 4

    # Verify probability prediction on unseen test cases
    X_test = ["explosion and fire at production separator", "sweeping dust off hallway floor"]
    probs = calibrator.predict_proba(X_test)[:, 1]
    assert len(probs) == 2
    assert 0.0 <= probs[0] <= 1.0
    assert 0.0 <= probs[1] <= 1.0
    assert probs[0] > probs[1]  # SIF hazard should have higher probability than benign activity


def test_calibrate_classifier_insufficient_data_handling():
    """Test graceful handling when validation data is insufficient (need >=4 samples, both classes)."""
    base_pipe = Pipeline([
        ("tfidf", TfidfVectorizer()),
        ("clf", LogisticRegression(random_state=42)),
    ])
    base_pipe.fit(["fire hazard", "clean floor"], [True, False])

    # Case 1: Too few samples (<4)
    calibrator1, cal_version1, diag1 = calibrate_classifier(
        base_pipe,
        ["fire hazard", "clean floor"],
        [True, False],
    )
    assert diag1["is_calibrated"] is False
    assert diag1["status"] == "INSUFFICIENT_VALIDATION_DATA"
    assert "uncalibrated" in cal_version1

    # Case 2: Only one class present in validation set
    calibrator2, cal_version2, diag2 = calibrate_classifier(
        base_pipe,
        ["clean floor 1", "clean floor 2", "clean floor 3", "clean floor 4"],
        [False, False, False, False],
    )
    assert diag2["is_calibrated"] is False
    assert diag2["status"] == "INSUFFICIENT_VALIDATION_DATA"
    assert "uncalibrated" in cal_version2


def test_calibration_curve_data_computation():
    """Test computation of reliability curve points."""
    y_true = [True, False, True, False, True, True, False, False]
    y_prob = [0.95, 0.05, 0.85, 0.15, 0.75, 0.80, 0.20, 0.10]

    curve = compute_calibration_curve_data(y_true, y_prob, n_bins=4)
    assert curve is not None
    assert "prob_true" in curve
    assert "prob_pred" in curve
    assert len(curve["prob_true"]) > 0
    assert len(curve["prob_pred"]) == len(curve["prob_true"])
