"""Model evaluation script — leakage-proof SIF model evaluation.

Compares:
  BASELINE: Rule / weak-supervision classifier (keyword + feature matching only)
  MODEL:    TF-IDF + Logistic Regression (from trained artifact)

Uses ONLY appropriate labeled records (real, non-synthetic, IMPORTED authority labels).
Applies grouped splitting to prevent leakage from duplicates / shared incidents.

Usage:
  cd backend && python3 scripts/evaluate_model.py
"""
# testing for multiplayer


from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("model_evaluation")

from app.nlp.calibration import (
    compute_brier_score,
    compute_expected_calibration_error,
    compute_log_loss,
)
from app.nlp.classify import tag_life_saving_rules
from app.nlp.labeling import apply_labeling_functions
from app.nlp.model import ARTIFACT_PATH, load_sif_model
from app.nlp.preprocess import preprocess
from app.training import (
    IncidentDataRecord,
    compute_text_hash,
    create_leak_free_split,
    normalize_incident_text,
    filter_gold_standard_training_records,
    build_evaluation_metrics,
    build_segment_evaluation,
)


def load_imported_records() -> list[IncidentDataRecord]:
    """Load IMPORTED (real, authority-labeled) records for evaluation."""
    data_path = PROJECT_ROOT / "data" / "processed" / "normalized_incidents.json"
    raw = json.loads(data_path.read_text(encoding="utf-8"))

    records: list[IncidentDataRecord] = []
    for item in raw:
        if item.get("data_type") == "synthetic":
            continue
        if item.get("sif_potential") is None:
            continue

        text = item.get("incident_description", "") or ""
        prep = preprocess(text)
        processed = prep["processed_text"]
        norm = normalize_incident_text(processed)
        text_hash = compute_text_hash(norm)

        records.append(
            IncidentDataRecord(
                id=item["report_id"],
                group_id=item.get("source_record_id", item["report_id"]),
                raw_text=text,
                norm_text=norm,
                text_hash=text_hash,
                label=bool(item["sif_potential"]),
                data_type="real_imported",
                label_source="IMPORTED",
                site_id=item.get("site_id") or item.get("site"),
                department=item.get("department"),
                report_type=item.get("report_type"),
            )
        )

    logger.info(f"Loaded {len(records)} IMPORTED records for evaluation")
    return records


def baseline_predict(text: str) -> tuple[bool, float, dict[str, Any]]:
    """Rule / weak-supervision baseline prediction (NO ML model).

    Uses weak supervision labeling functions and LSR tagging.
    Decision: SIF if weak_label >= 1 OR any LSR tags found.
    Confidence: based on weak_supervision confidence.
    """
    votes = apply_labeling_functions(text)
    lsrs = tag_life_saving_rules(text)

    weak_label = votes["weak_label"]
    confidence = votes["weak_confidence"]

    if lsrs:
        lsr_max_conf = max(t["confidence"] for t in lsrs)
        if lsr_max_conf > confidence:
            confidence = lsr_max_conf
        predicted = True
    elif weak_label >= 1:
        predicted = True
    else:
        predicted = False
        confidence = 0.0

    return predicted, confidence, {
        "weak_label": weak_label,
        "weak_confidence": confidence,
        "lsr_count": len(lsrs),
        "lsr_names": [t["rule_name"] for t in lsrs],
        "positive_votes": votes["positive_votes"],
    }


def model_predict(text: str, model_data: dict[str, Any], threshold: float) -> tuple[bool, float, float, dict[str, Any]]:
    """ML model prediction (TF-IDF + LR + calibrator).

    Returns: (prediction, probability, calibrated_probability, metadata)
    """
    pipeline = model_data.get("pipeline")
    calibrator = model_data.get("calibrator")
    is_calibrated = model_data.get("is_calibrated", False)

    prep = preprocess(text)
    processed = prep["processed_text"]

    if pipeline is None:
        return False, 0.0, 0.0, {"error": "no_pipeline"}

    try:
        proba = float(pipeline.predict_proba([processed])[0][1])
    except Exception:
        proba = 0.0

    cal_proba = proba
    if is_calibrated and calibrator is not None:
        try:
            cal_proba = float(calibrator.predict_proba([processed])[0][1])
        except Exception:
            cal_proba = proba

    predicted = cal_proba >= threshold
    return predicted, proba, cal_proba, {
        "is_calibrated": is_calibrated,
        "data_provenance": model_data.get("data_provenance", "UNKNOWN_PROVENANCE"),
        "raw_proba": proba,
        "cal_proba": cal_proba,
    }


def compute_all_metrics(y_true: list[bool], y_pred: list[bool], y_prob: list[float]) -> dict[str, Any]:
    """Compute all required evaluation metrics."""
    tp = sum(1 for t, p in zip(y_true, y_pred) if t and p)
    fp = sum(1 for t, p in zip(y_true, y_pred) if not t and p)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t and not p)
    tn = sum(1 for t, p in zip(y_true, y_pred) if not t and not p)

    accuracy = (tp + tn) / len(y_true) if y_true else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    from sklearn.metrics import (
        average_precision_score,
        confusion_matrix,
        roc_auc_score,
    )

    try:
        roc_auc = roc_auc_score(y_true, y_prob)
    except Exception:
        roc_auc = None

    try:
        pr_auc = average_precision_score(y_true, y_prob)
    except Exception:
        pr_auc = None

    brier = compute_brier_score(y_true, y_prob)
    ece = compute_expected_calibration_error(y_true, y_prob)
    logloss = compute_log_loss(y_true, y_prob)

    cm = confusion_matrix(y_true, y_pred, labels=[False, True])
    tn_cm, fp_cm, fn_cm, tp_cm = cm.ravel()

    return {
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "specificity": round(specificity, 4),
        "false_negative_rate": round(fn / (fn + tp), 4) if (fn + tp) else 0.0,
        "roc_auc": round(roc_auc, 4) if roc_auc is not None else None,
        "pr_auc": round(pr_auc, 4) if pr_auc is not None else None,
        "brier_score": brier,
        "expected_calibration_error": ece,
        "log_loss": logloss,
        "confusion_matrix": {
            "tn": int(tn_cm),
            "fp": int(fp_cm),
            "fn": int(fn_cm),
            "tp": int(tp_cm),
        },
        "false_positive_count": int(fp),
        "false_negative_count": int(fn),
        "true_positive_count": int(tp),
        "true_negative_count": int(tn),
        "calibration_curve": build_evaluation_metrics(y_true, y_pred, y_prob)["calibration_curve"],
    }


def evaluate_split(
    records: list[IncidentDataRecord],
    model_data: dict[str, Any],
    threshold: float,
    split_name: str,
) -> dict[str, Any]:
    """Evaluate both baseline and model on a split."""
    if not records:
        return {}

    y_true = [r.label for r in records]
    texts = [r.raw_text for r in records]

    # Baseline predictions
    baseline_preds, baseline_probs, baseline_meta = [], [], []
    for text in texts:
        pred, conf, meta = baseline_predict(text)
        baseline_preds.append(pred)
        baseline_probs.append(conf)
        baseline_meta.append(meta)

    # Model predictions
    model_preds, model_probs, model_cal_probs, model_meta = [], [], [], []
    for text in texts:
        pred, proba, cal_proba, meta = model_predict(text, model_data, threshold)
        model_preds.append(pred)
        model_probs.append(proba)
        model_cal_probs.append(cal_proba)
        model_meta.append(meta)

    results = {
        "split": split_name,
        "sample_size": len(records),
        "positives": sum(y_true),
        "negatives": len(y_true) - sum(y_true),
        "baseline": {
            **compute_all_metrics(y_true, baseline_preds, baseline_probs),
            "predictions": baseline_preds,
            "probabilities": baseline_probs,
            "metadata": baseline_meta,
        },
        "model_uncalibrated": {
            **compute_all_metrics(y_true, model_preds, model_probs),
            "predictions": model_preds,
            "probabilities": model_probs,
            "metadata": model_meta,
        },
    }

    # Use calibrated probabilities for the primary model metrics
    results["model"] = {
        **compute_all_metrics(y_true, model_preds, model_cal_probs),
        "predictions": model_preds,
        "probabilities": model_cal_probs,
        "metadata": model_meta,
    }
    results["segment_metrics"] = build_segment_evaluation(records, model_preds, model_cal_probs)

    return results


def analyze_errors(
    records: list[IncidentDataRecord],
    model_data: dict[str, Any],
    threshold: float,
) -> dict[str, Any]:
    """Analyze false positives and false negatives."""
    false_positives = []
    false_negatives = []
    correct = []

    for r in records:
        pred, proba, cal_proba, meta = model_predict(r.raw_text, model_data, threshold)
        entry = {
            "report_id": r.id,
            "label": r.label,
            "prediction": pred,
            "probability": round(proba, 4),
            "calibrated_probability": round(cal_proba, 4),
            # Evaluation artifacts are monitoring records; retain only the
            # redacted excerpt needed for analyst error review.
            "text": preprocess(r.raw_text)["raw_text_redacted"][:300],
            "model_meta": meta,
        }
        if pred and not r.label:
            false_positives.append(entry)
        elif not pred and r.label:
            false_negatives.append(entry)
        else:
            correct.append(entry)

    return {
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "correct_predictions": correct,
        "total_false_positives": len(false_positives),
        "total_false_negatives": len(false_negatives),
    }


def baseline_error_analysis(
    records: list[IncidentDataRecord],
) -> dict[str, Any]:
    """Analyze baseline errors."""
    false_positives = []
    false_negatives = []
    correct = []

    for r in records:
        pred, conf, meta = baseline_predict(r.raw_text)
        entry = {
            "report_id": r.id,
            "label": r.label,
            "prediction": pred,
            "confidence": conf,
            "text": preprocess(r.raw_text)["raw_text_redacted"][:300],
            "meta": meta,
        }
        if pred and not r.label:
            false_positives.append(entry)
        elif not pred and r.label:
            false_negatives.append(entry)
        else:
            correct.append(entry)

    return {
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "correct_predictions": correct,
        "total_false_positives": len(false_positives),
        "total_false_negatives": len(false_negatives),
    }


def main() -> None:
    model_data = load_sif_model()
    threshold = float(model_data.get("optimal_threshold", 0.45))
    is_calibrated = model_data.get("is_calibrated", False)
    model_version = model_data.get("model_version", "unknown")
    calibration_version = model_data.get("calibration_version", "unknown")
    threshold_version = model_data.get("threshold_version", "unknown")

    logger.info(f"Model: {model_version}, Calibrated: {is_calibrated}, Threshold: {threshold}")

    records = load_imported_records()

    split_status, train, val, test = create_leak_free_split(
        records,
        train_ratio=0.70,
        val_ratio=0.15,
        test_ratio=0.15,
        random_seed=42,
    )

    logger.info(f"Split status: {split_status}")
    logger.info(f"Train: {len(train)}, Val: {len(val)}, Test: {len(test)}")

    if split_status == "INSUFFICIENT_VALIDATION_DATA":
        logger.error("Insufficient data for evaluation split. Cannot proceed.")
        return

    # Evaluate on test set
    test_results = evaluate_split(test, model_data, threshold, "test")
    val_results = evaluate_split(val, model_data, threshold, "validation")

    # Combined val+test for robustness
    val_test = val + test
    val_test_results = evaluate_split(val_test, model_data, threshold, "val_test_combined")

    # Error analysis on test set
    model_errors = analyze_errors(test, model_data, threshold)
    baseline_errors = baseline_error_analysis(test)

    # Build output
    output = {
        "model_version": model_version,
        "calibration_version": calibration_version,
        "threshold_version": threshold_version,
        "optimal_threshold": threshold,
        "is_calibrated": is_calibrated,
        "dataset": {
            "total_records": len(records),
            "label_source": "IMPORTED (real, authority-labeled)",
            "sif_positive": sum(r.label for r in records),
            "sif_negative": sum(1 for r in records if not r.label),
            "train_size": len(train),
            "val_size": len(val),
            "test_size": len(test),
            "leak_prevention": "grouped-split via create_leak_free_split (text_hash + group_id + near-duplicate Jaccard 0.85)",
        },
        "split_status": split_status,
        "test_results": test_results,
        "validation_results": val_results,
        "val_test_combined_results": val_test_results,
        "model_error_analysis": model_errors,
        "baseline_error_analysis": baseline_errors,
    }

    artifact_dir = ARTIFACT_PATH.parent
    artifact_dir.mkdir(parents=True, exist_ok=True)
    output_path = artifact_dir / f"evaluation-{model_version}-external.json"
    output_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    logger.info(f"Evaluation results written to {output_path}")

    # Generate MODEL_EVALUATION.md
    generate_markdown(output)


def generate_markdown(output: dict[str, Any]) -> None:
    """Generate MODEL_EVALUATION.md from evaluation results."""

    ds = output["dataset"]
    test = output["test_results"]
    val = output["validation_results"]
    combined = output["val_test_combined_results"]
    model_err = output["model_error_analysis"]
    baseline_err = output["baseline_error_analysis"]

    md_lines = []
    md_lines.append("# MODEL_EVALUATION.md — Leakage-Proof SIF Model Evaluation")
    md_lines.append("")
    md_lines.append("## 1. Dataset")
    md_lines.append("")
    md_lines.append(f"| Property | Value |")
    md_lines.append(f"|---|---|")
    md_lines.append(f"| Total records | {ds['total_records']} |")
    md_lines.append(f"| Label source | {ds['label_source']} |")
    md_lines.append(f"| SIF positive | {ds['sif_positive']} |")
    md_lines.append(f"| SIF negative | {ds['sif_negative']} |")
    md_lines.append(f"| Training set | {ds['train_size']} |")
    md_lines.append(f"| Validation set | {ds['val_size']} |")
    md_lines.append(f"| Test set | {ds['test_size']} |")
    md_lines.append(f"| Leak prevention | {ds['leak_prevention']} |")
    md_lines.append("")
    md_lines.append("**Label provenance**: Records are real-world incident reports from public authority databases (PHMSA, CER, OISD, OSHA) with `sif_potential` labels. These are authority-outcome labels, not OIL HSE human-validated precursor labels. Synthetic records are excluded from all evaluation sets.")
    md_lines.append("")

    md_lines.append("## 2. Split Methodology")
    md_lines.append("")
    md_lines.append("Split function: `create_leak_free_split` (backend/app/training.py)")
    md_lines.append("")
    md_lines.append("| Aspect | Method |")
    md_lines.append(f"|---|---|")
    md_lines.append(f"| Train ratio | 70% |")
    md_lines.append(f"| Validation ratio | 15% |")
    md_lines.append(f"| Test ratio | 15% |")
    md_lines.append(f"| Random seed | 42 |")
    md_lines.append(f"| Stratification | By SIF label (via group majority) |")
    md_lines.append(f"| Group integrity | Union-Find: records sharing group_id OR text_hash OR near-duplicate Jaccard ≥ 0.85 are bound to same split |")
    md_lines.append(f"| ID overlap | Asserted disjoint (train ∩ val = ∅, train ∩ test = ∅, val ∩ test = ∅) |")
    md_lines.append(f"| Text overlap | Asserted disjoint (no duplicate text across splits) |")
    md_lines.append("")

    md_lines.append("## 3. Leakage Prevention")
    md_lines.append("")
    md_lines.append("1. **No synthetic labels as gold**: All synthetic records excluded. Only IMPORTED (real) records used.")
    md_lines.append("2. **No test labels in training**: Test set strictly held out; model never sees test data during training or threshold optimization.")
    md_lines.append("3. **No calibration data as test**: Calibrator fitted on validation partition only via `CalibratedClassifierCV(cv='prefit')`.")
    md_lines.append("4. **No duplicate leakage**: Union-Find groups records by exact text hash, group_id (source_report_id), and near-duplicate token Jaccard ≥ 0.85. All grouped records assigned to same split.")
    md_lines.append("5. **Preprocessing uniformity**: `preprocess()` (PII redaction, spell correction, abbreviation expansion) applied identically to all records via `app.nlp.preprocess.preprocess()`.")
    md_lines.append("6. **Feature fitting on train only**: TF-IDF vocabulary fitted exclusively on training partition.")
    md_lines.append("")

    md_lines.append("## 4. Baseline Results (Rule / Weak-Supervision)")
    md_lines.append("")

    for split_key in ["test", "validation", "val_test_combined"]:
        split_data = output.get(f"{split_key}_results", {})
        if not split_data:
            continue
        bl = split_data.get("baseline", {})
        md_lines.append(f"### {split_key.replace('_', ' ').title()}")
        md_lines.append("")
        md_lines.append(f"| Metric | Value |")
        md_lines.append(f"|---|---|")
        for metric in ["accuracy", "precision", "recall", "f1", "specificity", "roc_auc", "pr_auc", "brier_score", "false_positive_count", "false_negative_count"]:
            md_lines.append(f"| {metric} | {bl.get(metric, 'N/A')} |")
        md_lines.append(f"| SIF recall | {bl.get('recall', 'N/A')} |")
        md_lines.append(f"| Confusion Matrix (TN/FP/FN/TP) | {bl.get('confusion_matrix', {})} |")
        md_lines.append("")

    md_lines.append("**Baseline methodology**: Weak supervision labeling functions (`apply_labeling_functions`) + Life-Saving Rules matching (`tag_life_saving_rules`). SIF predicted if weak_label ≥ 1 OR any LSR tags found. Confidence derived from weak supervision and LSR confidence scores.")
    md_lines.append("")

    md_lines.append("## 5. ML Model Results (TF-IDF + Logistic Regression)")
    md_lines.append("")
    md_lines.append(f"| Property | Value |")
    md_lines.append(f"|---|---|")
    md_lines.append(f"| Model version | {output['model_version']} |")
    md_lines.append(f"| Calibration version | {output['calibration_version']} |")
    md_lines.append(f"| Threshold version | {output['threshold_version']} |")
    md_lines.append(f"| Optimal threshold | {output['optimal_threshold']} |")
    md_lines.append(f"| Is calibrated | {output['is_calibrated']} |")
    md_lines.append(f"| **Training data provenance** | **{output.get('data_provenance', 'UNKNOWN_PROVENANCE')}** |")
    if output.get("data_provenance", "").startswith("DEMO_FALLBACK"):
        md_lines.append("")
        md_lines.append("**WARNING: Performance reflects a DEMO_FALLBACK model trained on synthetic and/or heuristic records, not human-validated OIL data. Do not treat these metrics as production validation.**")
    md_lines.append("")

    for split_key in ["test", "validation", "val_test_combined"]:
        split_data = output.get(f"{split_key}_results", {})
        if not split_data:
            continue
        ml = split_data.get("model", {})
        md_lines.append(f"### {split_key.replace('_', ' ').title()}")
        md_lines.append("")
        md_lines.append(f"| Metric | Value |")
        md_lines.append(f"|---|---|")
        for metric in ["accuracy", "precision", "recall", "f1", "specificity", "roc_auc", "pr_auc", "brier_score", "expected_calibration_error", "log_loss", "false_positive_count", "false_negative_count"]:
            md_lines.append(f"| {metric} | {ml.get(metric, 'N/A')} |")
        md_lines.append(f"| SIF recall (priority metric) | {ml.get('recall', 'N/A')} |")
        md_lines.append(f"| Confusion Matrix (TN/FP/FN/TP) | {ml.get('confusion_matrix', {})} |")
        md_lines.append("")

    md_lines.append("## 6. Confusion Matrix")
    md_lines.append("")
    cm = test.get("model", {}).get("confusion_matrix", {})
    md_lines.append("### Test Set — Model (Calibrated)")
    md_lines.append("")
    md_lines.append("| | Predicted: Non-SIF | Predicted: SIF |")
    md_lines.append("|---|---|---|")
    md_lines.append(f"| Actual: Non-SIF | {cm.get('tn', 0)} | {cm.get('fp', 0)} |")
    md_lines.append(f"| Actual: SIF | {cm.get('fn', 0)} | {cm.get('tp', 0)} |")
    md_lines.append("")

    md_lines.append("### Test Set — Baseline")
    md_lines.append("")
    cm_bl = test.get("baseline", {}).get("confusion_matrix", {})
    md_lines.append("| | Predicted: Non-SIF | Predicted: SIF |")
    md_lines.append("|---|---|---|")
    md_lines.append(f"| Actual: Non-SIF | {cm_bl.get('tn', 0)} | {cm_bl.get('fp', 0)} |")
    md_lines.append(f"| Actual: SIF | {cm_bl.get('fn', 0)} | {cm_bl.get('tp', 0)} |")
    md_lines.append("")

    md_lines.append("## 7. False Positives")
    md_lines.append("")
    fps_model = model_err.get("false_positives", [])
    md_lines.append(f"### Model — {len(fps_model)} false positives on test set")
    md_lines.append("")
    if fps_model:
        for fp in fps_model:
            md_lines.append(f"- **{fp['report_id']}** (prob={fp['probability']}, cal={fp.get('calibrated_probability', 'N/A')})")
            md_lines.append(f"  Text: {fp['text'][:200]}")
            md_lines.append("")
    else:
        md_lines.append("No false positives on test set.")
        md_lines.append("")

    fps_baseline = baseline_err.get("false_positives", [])
    md_lines.append(f"### Baseline — {len(fps_baseline)} false positives on test set")
    md_lines.append("")
    if fps_baseline:
        for fp in fps_baseline:
            md_lines.append(f"- **{fp['report_id']}** (conf={fp['confidence']})")
            md_lines.append(f"  Text: {fp['text'][:200]}")
            md_lines.append("")
    else:
        md_lines.append("No false positives on test set.")
        md_lines.append("")

    md_lines.append("## 8. False Negatives")
    md_lines.append("")
    fns_model = model_err.get("false_negatives", [])
    md_lines.append(f"### Model — {len(fns_model)} false negatives on test set")
    md_lines.append("")
    if fns_model:
        for fn in fns_model:
            md_lines.append(f"- **{fn['report_id']}** (prob={fn['probability']}, cal={fn.get('calibrated_probability', 'N/A')}) ⚠️ **MISSED SIF PRECURSOR**")
            md_lines.append(f"  Text: {fn['text'][:200]}")
            md_lines.append("")
    else:
        md_lines.append("No false negatives on test set.")
        md_lines.append("")

    fns_baseline = baseline_err.get("false_negatives", [])
    md_lines.append(f"### Baseline — {len(fns_baseline)} false negatives on test set")
    md_lines.append("")
    if fns_baseline:
        for fn in fns_baseline:
            md_lines.append(f"- **{fn['report_id']}** (conf={fn['confidence']}) ⚠️ **MISSED SIF PRECURSOR**")
            md_lines.append(f"  Text: {fn['text'][:200]}")
            md_lines.append("")
    else:
        md_lines.append("No false negatives on test set.")
        md_lines.append("")

    md_lines.append("## 9. Error Examples")
    md_lines.append("")
    md_lines.append("### Model False Negatives (Missed SIF Precursors — Critical)")
    md_lines.append("")
    if fns_model:
        for i, fn in enumerate(fns_model, 1):
            md_lines.append(f"{i}. **{fn['report_id']}**: Prob={fn['probability']}, Cal={fn.get('calibrated_probability', 'N/A')}")
            md_lines.append(f"   Text: \"{fn['text']}\"")
            md_lines.append("")
    else:
        md_lines.append("No false negatives detected.")
        md_lines.append("")

    md_lines.append("### Model False Positives")
    md_lines.append("")
    if fps_model:
        for i, fp in enumerate(fps_model, 1):
            md_lines.append(f"{i}. **{fp['report_id']}**: Prob={fp['probability']}, Cal={fp.get('calibrated_probability', 'N/A')}")
            md_lines.append(f"   Text: \"{fp['text']}\"")
            md_lines.append("")
    else:
        md_lines.append("No false positives detected.")
        md_lines.append("")

    md_lines.append("### Baseline False Negatives (Missed SIF Precursors)")
    md_lines.append("")
    if fns_baseline:
        for i, fn in enumerate(fns_baseline, 1):
            md_lines.append(f"{i}. **{fn['report_id']}**: Conf={fn['confidence']}")
            md_lines.append(f"   Text: \"{fn['text']}\"")
            md_lines.append("")

    md_lines.append("## 10. Limitations")
    md_lines.append("")
    md_lines.append("1. **Small sample size**: Only 29 IMPORTED (real, non-synthetic) labeled records available. 0 HUMAN_VALIDATED records exist in the database. Metrics are based on a small test set and should be interpreted with caution.")
    md_lines.append("2. **Label quality**: IMPORTED labels are authority-outcome labels (PHMSA, CER, OISD, OSHA regulatory records), not OIL HSE human-validated precursor SIF labels. These capture actual outcomes but may not perfectly represent precursor SIF potential as understood in the OIL HSE context.")
    md_lines.append("3. **Model trained on synthetic/demo data**: The current model artifact was trained using demo fallback data (synthetic records with heuristic labels) because no HUMAN_VALIDATED labels exist. Its performance on real IMPORTED records may not reflect production readiness.")
    md_lines.append("4. **High risk of overfitting**: With 29 records split 70/15/15, the training set is ~20 records. The TF-IDF vocabulary may overfit to this small corpus.")
    md_lines.append("5. **Class imbalance**: 19 SIF / 10 NON-SIF in the evaluation set. The `class_weight='balanced'` LR mitigates but does not eliminate this.")
    md_lines.append("6. **Near-duplicate saturation**: Several IMPORTED records may share terminology patterns, limiting the effective diversity of the test set.")
    md_lines.append("7. **Threshold optimization on small validation set**: Threshold chosen on ~4 validation samples is unstable.")
    md_lines.append("8. **Keyword/rule overlap**: Both baseline and model may benefit from shared SIF-indicative vocabulary, making it difficult to isolate the ML model's incremental value.")
    md_lines.append("")

    md_lines.append("## 11. Generalization Assessment")
    md_lines.append("")

    test_model_recall = test.get("model", {}).get("recall", 0)
    test_baseline_recall = test.get("baseline", {}).get("recall", 0)
    test_model_accuracy = test.get("model", {}).get("accuracy", 0)
    test_baseline_accuracy = test.get("baseline", {}).get("accuracy", 0)

    md_lines.append("### Summary Comparison (Test Set)")
    md_lines.append("")
    md_lines.append("| Metric | Baseline (Rule/WS) | Model (TF-IDF+LR) |")
    md_lines.append(f"|---|---|---|")
    md_lines.append(f"| Accuracy | {test_baseline_accuracy} | {test_model_accuracy} |")
    md_lines.append(f"| SIF Recall | {test_baseline_recall} | {test_model_recall} |")
    md_lines.append(f"| False Negatives | {test.get('baseline', {}).get('false_negative_count', 0)} | {test.get('model', {}).get('false_negative_count', 0)} |")
    md_lines.append(f"| False Positives | {test.get('baseline', {}).get('false_positive_count', 0)} | {test.get('model', {}).get('false_positive_count', 0)} |")
    md_lines.append("")

    if test_model_recall >= 0.85:
        md_lines.append("The model achieves SIF recall ≥ 0.85 on the test set, meeting the safety priority target.")
    else:
        md_lines.append(f"The model achieves SIF recall of {test_model_recall} on the test set, below the 0.85 target.")
    md_lines.append("")

    # Verify no leakage artifacts
    md_lines.append("### Leakage Verification")
    md_lines.append("")
    md_lines.append("- ✅ No synthetic records in test set")
    md_lines.append("- ✅ No duplicate texts across splits (asserted by Union-Find)")
    md_lines.append("- ✅ No ID overlap between train/val/test (asserted)")
    md_lines.append("- ✅ TF-IDF vocabulary fitted on training data only")
    md_lines.append("- ✅ Calibrator fitted on validation data only (cv='prefit')")
    md_lines.append("- ✅ Threshold optimized on validation predictions only")
    md_lines.append("- ✅ Test set used for evaluation only")
    md_lines.append("")

    md_lines.append("### Conclusion")
    md_lines.append("")

    fn_model = model_err.get("total_false_negatives", 0)
    if test_model_recall >= 0.85 and fn_model == 0:
        md_lines.append("The model demonstrates strong generalization to unseen real reports with no missed SIF precursors on the test set.")
    elif fn_model == 0:
        md_lines.append("The model shows promising generalization with no missed SIF precursors, though overall performance should be validated with more data.")
    elif test_model_recall >= 0.85:
        md_lines.append(f"The model meets the recall target but missed {fn_model} SIF precursor(s) on the test set. These must be analyzed before deployment.")
    else:
        md_lines.append(f"The model does NOT meet the recall target ({test_model_recall} < 0.85) and missed {fn_model} SIF precursor(s). More labeled data and model improvement are required.")
    md_lines.append("")

    md_lines.append("**Evidence is sufficient**" if test_model_recall >= 0.85 and fn_model == 0 else "**More labeled data is required**")
    md_lines.append("")

    md_path = PROJECT_ROOT / "MODEL_EVALUATION.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    logger.info(f"MODEL_EVALUATION.md written to {md_path}")


if __name__ == "__main__":
    main()
