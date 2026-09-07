from app.nlp.calibration import choose_threshold, classification_metrics


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
