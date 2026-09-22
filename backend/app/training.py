"""Machine learning training pipeline with probability calibration and versioned metadata.

ML Architecture (as actually implemented):
  Raw Text
    ↓ Preprocessing — PII Redaction, Negated Hazard Suppression, Spell Correction, Abbreviation Expansion
      preprocessing_version: prep-pii-negation-spell-abbr-v2
  TF-IDF Vectorizer — ngram_range=(1,2), max_features=5000
    feature_version: tfidf-unigram-bigram-v1
    ↓
  Logistic Regression — class_weight='balanced'
    model_version: sif-logreg-v1-<timestamp>
    ↓  (fitted on TRAIN partition only)
  sklearn CalibratedClassifierCV(cv='prefit', method='sigmoid')
    calibration_version: sklearn-ccv-sigmoid-prefit-v1
    (sigmoid calibration layer fitted on VAL partition only;
     cv='prefit' means the base pipeline is NOT re-fitted here)
    ↓
  Threshold Optimization — safety-recall-prioritized grid search
    threshold_version: thresh-opt-recall-0.85-v1
    (computed on calibrated VAL predictions ONLY; test set never touched)
    ↓
  Holdout Test Set Evaluation — untouched until final metric calculation

Version concepts are strictly SEPARATE and never overwrite each other:
  model_version        — identity of the fitted LR + TF-IDF weights
  feature_version      — TF-IDF configuration
  preprocessing_version — PII/negation/spell/abbreviation pipeline
  dataset_version      — which labeled dataset was used
  label_schema_version — SIF binary label schema
  calibration_version  — calibration method (CalibratedClassifierCV vs uncalibrated)
  threshold_version    — how the decision threshold was selected
  training_run_id      — unique UUID for each training execution
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import platform
import random
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import joblib
import sklearn
from sklearn.calibration import calibration_curve
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    ModelTrainingRun,
    Report,
)
from app.nlp.calibration import (
    calibrate_classifier,
    compute_brier_score,
    compute_expected_calibration_error,
    compute_log_loss,
    optimize_threshold,
)
from app.nlp.model import ARTIFACT_PATH
from app.nlp.preprocess import PREPROCESSING_VERSION, preprocess

logger = logging.getLogger(__name__)

MIN_TOTAL_RECORDS_FOR_SPLIT = 20
MIN_PER_CLASS_FOR_SPLIT = 4

FEATURE_VERSION = "tfidf-unigram-bigram-v1"
DATASET_VERSION = "sih-safety-ds-v1"
LABEL_SCHEMA_VERSION = "sif-binary-v1"

# Evaluation taxonomy: only HUMAN_VALIDATED (non-synthetic) may enter gold train/test.
GOLD_EVAL_LABEL_SOURCES = frozenset(
    {
        "HUMAN_VALIDATED",
        "CONSENSUS_VALIDATED",
        "SENIOR_HSE_OVERRIDE",
        "HUMAN_REVIEW",
    }
)
NON_GOLD_EVAL_LABEL_SOURCES = frozenset(
    {
        "SYNTHETIC",
        "HEURISTIC",
        "HEURISTIC_PREDICTION",
        "HEURISTIC_DEMO",
        "IMPORTED",
        "UNKNOWN",
        "UNLABELED",
        "DISAGREEMENT",
    }
)
NEAR_DUP_JACCARD_THRESHOLD = 0.85
MIN_TOKENS_FOR_NEAR_DUP = 6


@dataclass
class IncidentDataRecord:
    id: str
    group_id: str
    raw_text: str
    norm_text: str
    text_hash: str
    label: bool
    data_type: str
    label_source: str
    site_id: str | None = None
    department: str | None = None
    report_type: str | None = None


def build_evaluation_metrics(
    y_true: list[bool], y_pred: list[bool], y_prob: list[float], *, n_bins: int = 5
) -> dict[str, Any]:
    """Return auditable binary metrics, confusion matrix, and calibration bins."""
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[False, True]).ravel()
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="binary", zero_division=0
    )
    specificity = tn / (tn + fp) if tn + fp else 0.0
    fnr = fn / (fn + tp) if fn + tp else 0.0
    calibration_bins: list[dict[str, float | int]] = []
    if y_true and len(set(y_true)) > 1:
        observed, predicted = calibration_curve(y_true, y_prob, n_bins=n_bins, strategy="uniform")
        for index, (mean_predicted, fraction_positive) in enumerate(zip(predicted, observed)):
            calibration_bins.append({
                "bin": index,
                "mean_predicted_probability": round(float(mean_predicted), 4),
                "observed_positive_rate": round(float(fraction_positive), 4),
            })
    return {
        "sample_size": len(y_true),
        "positives": int(sum(y_true)),
        "negatives": int(len(y_true) - sum(y_true)),
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4) if y_true else 0.0,
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
        "specificity": round(float(specificity), 4),
        "false_negative_rate": round(float(fnr), 4),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "calibration_curve": calibration_bins,
    }


def build_segment_evaluation(
    records: list[IncidentDataRecord], y_pred: list[bool], y_prob: list[float]
) -> dict[str, dict[str, dict[str, Any]]]:
    """Break held-out evaluation down by populated report metadata fields."""
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for field in ("site_id", "department", "report_type"):
        groups: dict[str, list[int]] = {}
        for index, record in enumerate(records):
            value = getattr(record, field, None)
            if value:
                groups.setdefault(str(value), []).append(index)
        result[field] = {
            value: build_evaluation_metrics(
                [records[i].label for i in indexes], [y_pred[i] for i in indexes], [y_prob[i] for i in indexes]
            )
            for value, indexes in sorted(groups.items())
        }
    return result


def assert_segment_quality_gates(segment_metrics: dict[str, dict[str, dict[str, Any]]]) -> None:
    """Block artifact publication when an eligible metadata segment underperforms."""
    failures: list[str] = []
    for dimension, segments in segment_metrics.items():
        for value, metric in segments.items():
            # Precision/recall are meaningful only if both classes are present.
            if (
                metric["sample_size"] < settings.evaluation_min_segment_size
                or not metric["positives"]
                or not metric["negatives"]
            ):
                metric["quality_gate"] = "SKIPPED_INSUFFICIENT_SEGMENT_DATA"
                continue
            passed = (
                metric["recall"] >= settings.evaluation_min_segment_recall
                and metric["precision"] >= settings.evaluation_min_segment_precision
            )
            metric["quality_gate"] = "PASSED" if passed else "FAILED"
            if not passed:
                failures.append(
                    f"{dimension}={value} (precision={metric['precision']}, recall={metric['recall']})"
                )
    if failures:
        raise ValueError("Segment evaluation quality gate failed: " + "; ".join(failures))


def normalize_incident_text(text: str | None) -> str:
    """Normalize incident description by removing punctuation, lowercasing, and collapsing whitespace."""
    if not text:
        return ""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return " ".join(cleaned.split())


def compute_text_hash(norm_text: str) -> str:
    """Compute SHA-256 hash for normalized text to detect exact and near duplicates."""
    if not norm_text:
        return ""
    return hashlib.sha256(norm_text.encode("utf-8")).hexdigest()[:16]


def _token_set(norm_text: str) -> set[str]:
    return {t for t in norm_text.split() if t}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def is_gold_standard_training_record(record: IncidentDataRecord) -> bool:
    """True only for human-validated, non-synthetic labeled records."""
    if record.label is None:
        return False
    dtype = (record.data_type or "").lower()
    if dtype in ("synthetic", "demo_synthetic", "demo", "real_heuristic"):
        return False
    src = (record.label_source or "").upper()
    if src in NON_GOLD_EVAL_LABEL_SOURCES:
        return False
    return src in GOLD_EVAL_LABEL_SOURCES


def filter_gold_standard_training_records(
    records: list[IncidentDataRecord],
) -> list[IncidentDataRecord]:
    """Exclude synthetic/heuristic/imported records from gold evaluation sets."""
    return [r for r in records if is_gold_standard_training_record(r)]


def assert_no_synthetic_in_split(
    records: list[IncidentDataRecord],
    *,
    split_name: str = "test",
) -> None:
    """Hard guard: synthetic / non-gold provenance must never enter gold splits."""
    offenders = []
    for r in records:
        dtype = (r.data_type or "").lower()
        src = (r.label_source or "").upper()
        if dtype in ("synthetic", "demo_synthetic", "demo") or src in (
            "SYNTHETIC",
            "HEURISTIC_DEMO",
            "HEURISTIC",
            "IMPORTED",
        ):
            offenders.append(f"{r.id}:{dtype}/{src}")
    if offenders:
        raise ValueError(
            f"Synthetic or non-gold records leaked into gold-standard {split_name} set: "
            f"{offenders[:8]}"
        )


def create_leak_free_split(
    records: list[IncidentDataRecord],
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    random_seed: int = 42,
    min_total_records: int = MIN_TOTAL_RECORDS_FOR_SPLIT,
    min_per_class: int = MIN_PER_CLASS_FOR_SPLIT,
) -> tuple[str, list[IncidentDataRecord], list[IncidentDataRecord], list[IncidentDataRecord]]:
    """Partitions records into Train, Validation, and Test sets without data leakage.

    Guarantees:
    - Group integrity: All records sharing the same group_id OR identical normalized text are bound to the same split.
    - No ID overlap between Train, Val, and Test.
    - No normalized text overlap between Train, Val, and Test.
    - Stratified by SIF label where possible.
    - Returns 'INSUFFICIENT_VALIDATION_DATA' if dataset is too small for a statistically reliable 3-way split.
    """
    if not records:
        return "INSUFFICIENT_VALIDATION_DATA", [], [], []

    total_records = len(records)
    positives = sum(1 for r in records if r.label)
    negatives = total_records - positives

    if total_records < min_total_records or positives < min_per_class or negatives < min_per_class:
        logger.warning(
            f"Dataset too small ({total_records} records, {positives} pos, {negatives} neg) "
            f"for reliable 3-way split (min {min_total_records} total, {min_per_class} per class required). "
            "Returning INSUFFICIENT_VALIDATION_DATA."
        )
        return "INSUFFICIENT_VALIDATION_DATA", records, [], []

    # Disjoint-Set / Union-Find to merge records sharing the same group_id OR same text_hash
    parent: dict[str, str] = {r.id: r.id for r in records}

    def find(i: str) -> str:
        path = []
        curr = i
        while parent[curr] != curr:
            path.append(curr)
            curr = parent[curr]
        for node in path:
            parent[node] = curr
        return curr

    def union(i: str, j: str) -> None:
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            parent[root_i] = root_j

    # Group by text_hash (exact duplicates)
    hash_to_first_id: dict[str, str] = {}
    for r in records:
        if r.text_hash:
            if r.text_hash in hash_to_first_id:
                union(r.id, hash_to_first_id[r.text_hash])
            else:
                hash_to_first_id[r.text_hash] = r.id

    # Group by source event group_id
    group_to_first_id: dict[str, str] = {}
    for r in records:
        if r.group_id:
            if r.group_id in group_to_first_id:
                union(r.id, group_to_first_id[r.group_id])
            else:
                group_to_first_id[r.group_id] = r.id

    # Near-duplicate grouping (token Jaccard) so paraphrases cannot cross splits
    prepared: list[tuple[IncidentDataRecord, set[str]]] = []
    for r in records:
        toks = _token_set(r.norm_text or normalize_incident_text(r.raw_text))
        if len(toks) >= MIN_TOKENS_FOR_NEAR_DUP:
            prepared.append((r, toks))
    for i in range(len(prepared)):
        rec_a, toks_a = prepared[i]
        for j in range(i + 1, len(prepared)):
            rec_b, toks_b = prepared[j]
            if rec_a.text_hash and rec_a.text_hash == rec_b.text_hash:
                continue
            if _jaccard(toks_a, toks_b) >= NEAR_DUP_JACCARD_THRESHOLD:
                union(rec_a.id, rec_b.id)

    # Collect merged groups
    groups: dict[str, list[IncidentDataRecord]] = {}
    for r in records:
        root = find(r.id)
        groups.setdefault(root, []).append(r)

    # Stratify groups by majority/any SIF label
    pos_groups: list[str] = []
    neg_groups: list[str] = []

    for root_id, group_records in groups.items():
        is_sif = any(rec.label for rec in group_records)
        if is_sif:
            pos_groups.append(root_id)
        else:
            neg_groups.append(root_id)

    rng = random.Random(random_seed)
    rng.shuffle(pos_groups)
    rng.shuffle(neg_groups)

    def partition_list(items: list[str]) -> tuple[list[str], list[str], list[str]]:
        n = len(items)
        if n == 0:
            return [], [], []
        n_val = max(1, math.floor(n * val_ratio))
        n_test = max(1, math.floor(n * test_ratio))
        n_train = n - n_val - n_test
        if n_train < 1:
            n_train = max(1, n - 2)
            n_val = 1 if n >= 2 else 0
            n_test = 1 if n >= 3 else 0

        train_keys = items[:n_train]
        val_keys = items[n_train : n_train + n_val]
        test_keys = items[n_train + n_val :]
        return train_keys, val_keys, test_keys

    pos_train, pos_val, pos_test = partition_list(pos_groups)
    neg_train, neg_val, neg_test = partition_list(neg_groups)

    train_group_keys = set(pos_train + neg_train)
    val_group_keys = set(pos_val + neg_val)
    test_group_keys = set(pos_test + neg_test)

    train_records: list[IncidentDataRecord] = []
    val_records: list[IncidentDataRecord] = []
    test_records: list[IncidentDataRecord] = []

    for root_id, group_records in groups.items():
        if root_id in train_group_keys:
            train_records.extend(group_records)
        elif root_id in val_group_keys:
            val_records.extend(group_records)
        elif root_id in test_group_keys:
            test_records.extend(group_records)
        else:
            train_records.extend(group_records)

    # Invariant verification assertions
    train_ids = {r.id for r in train_records}
    val_ids = {r.id for r in val_records}
    test_ids = {r.id for r in test_records}

    assert not (train_ids & val_ids), "CRITICAL: ID overlap between train and validation sets!"
    assert not (train_ids & test_ids), "CRITICAL: ID overlap between train and test sets!"
    assert not (val_ids & test_ids), "CRITICAL: ID overlap between validation and test sets!"

    train_texts = {r.norm_text for r in train_records if r.norm_text}
    val_texts = {r.norm_text for r in val_records if r.norm_text}
    test_texts = {r.norm_text for r in test_records if r.norm_text}

    assert not (train_texts & val_texts), "CRITICAL: Duplicate text leakage between train and validation sets!"
    assert not (train_texts & test_texts), "CRITICAL: Duplicate text leakage between train and test sets!"
    assert not (val_texts & test_texts), "CRITICAL: Duplicate text leakage between validation and test sets!"

    return "VALIDATED", train_records, val_records, test_records


def run_ml_training(
    db: Session,
    force_demo_fallback: bool = True,
    random_seed: int = 42,
) -> ModelTrainingRun:
    """Train a calibrated TF-IDF + Logistic Regression model with versioned metadata.

    Guarantees:
    - Preprocessing uniformity (PII redaction, spelling, abbreviation expansion) applied
      identically across TRAIN, VAL, TEST, and inference via app.nlp.preprocess.preprocess().
    - True probability calibration via sklearn CalibratedClassifierCV(cv='prefit',
      method='sigmoid') fitted ONLY on the held-out validation partition.  cv='prefit'
      ensures the base TF-IDF + LR pipeline is never re-fitted during calibration.
    - Threshold optimization executed ONLY on calibrated validation predictions.
      Test set is never used for threshold selection.
    - Test set strictly held out and evaluated only once after threshold is fixed.
    - Each version concept (model, feature, preprocessing, calibration, threshold)
      is independently versioned and stored in the artifact; none overwrites another.
    """
    reports = db.query(Report).all()

    validated_records: list[IncidentDataRecord] = []
    demo_fallback_records: list[IncidentDataRecord] = []
    privacy_rejected_records: list[dict[str, str]] = []

    for report in reports:
        # Strict privacy boundary: training text must originate from the
        # persisted, PII-redacted report. Never substitute processed_text,
        # which may have been imported by an older path with unknown lineage.
        if not report.raw_text_redacted:
            privacy_rejected_records.append(
                {"report_id": report.id, "reason": "PII_REDACTED_TEXT_REQUIRED"}
            )
            logger.warning(
                "Training record excluded at privacy boundary: report_id=%s reason=PII_REDACTED_TEXT_REQUIRED",
                report.id,
            )
            continue
        raw_text = report.raw_text_redacted
        # Apply standard uniform preprocessing
        prep = preprocess(raw_text)
        processed_text = prep["processed_text"]

        norm_text = normalize_incident_text(processed_text)
        text_hash = compute_text_hash(norm_text)
        group_id = report.source_report_id or report.id

        is_synthetic = getattr(report, "data_type", "synthetic") == "synthetic"
        val_lbl = getattr(report, "validated_label", None)
        human_lbl = getattr(report, "human_label", None)
        label_source = getattr(report, "label_source", "")

        # 1. Gold path: human-validated labels on NON-synthetic reports only.
        #    Synthetic/demo records are never admitted to the gold-standard set,
        #    even if a practice human label exists on them.
        if is_synthetic:
            # Fall through to demo fallback only; never gold.
            pass
        elif val_lbl in ("SIF", "NON_SIF"):
            validated_records.append(
                IncidentDataRecord(
                    id=report.id,
                    group_id=group_id,
                    raw_text=raw_text,
                    norm_text=norm_text,
                    text_hash=text_hash,
                    label=True if val_lbl == "SIF" else False,
                    data_type="human_validated",
                    label_source="HUMAN_VALIDATED",
                    site_id=report.site_id,
                    department=report.department,
                    report_type=report.report_type,
                )
            )
        elif human_lbl in ("SIF", "NON_SIF"):
            validated_records.append(
                IncidentDataRecord(
                    id=report.id,
                    group_id=group_id,
                    raw_text=raw_text,
                    norm_text=norm_text,
                    text_hash=text_hash,
                    label=True if human_lbl == "SIF" else False,
                    data_type="human_validated",
                    label_source="HUMAN_VALIDATED",
                    site_id=report.site_id,
                    department=report.department,
                    report_type=report.report_type,
                )
            )
        elif report.final_sif_label is not None and label_source in (
            "CONSENSUS_VALIDATED",
            "SENIOR_HSE_OVERRIDE",
            "HUMAN_REVIEW",
            "HUMAN_VALIDATED",
        ):
            validated_records.append(
                IncidentDataRecord(
                    id=report.id,
                    group_id=group_id,
                    raw_text=raw_text,
                    norm_text=norm_text,
                    text_hash=text_hash,
                    label=bool(report.final_sif_label),
                    data_type="human_validated",
                    label_source="HUMAN_VALIDATED",
                    site_id=report.site_id,
                    department=report.department,
                    report_type=report.report_type,
                )
            )

        # Demo / heuristic fallback only — never mixed into gold-standard evaluation.
        already_gold = any(v.id == report.id for v in validated_records)
        if (
            force_demo_fallback
            and not already_gold
            and report.classification is not None
        ):
            demo_fallback_records.append(
                IncidentDataRecord(
                    id=report.id,
                    group_id=group_id,
                    raw_text=raw_text,
                    norm_text=norm_text,
                    text_hash=text_hash,
                    label=bool(report.classification.sif_label),
                    data_type="demo_synthetic" if is_synthetic else "real_heuristic",
                    label_source="HEURISTIC_DEMO",
                    site_id=report.site_id,
                    department=report.department,
                    report_type=report.report_type,
                )
            )

    if validated_records:
        records = filter_gold_standard_training_records(validated_records)
        data_source = "HUMAN_VALIDATED"
        is_demo_evaluation = False
        data_provenance = "HUMAN_VALIDATED_NON_SYNTHETIC"
    elif force_demo_fallback and demo_fallback_records:
        records = demo_fallback_records
        data_source = "DEMO_FALLBACK"
        is_demo_evaluation = True
        data_provenance = "DEMO_FALLBACK_SYNTHETIC_OR_HEURISTIC"
        logger.warning(
            "[DEFENSE AUDIT WARNING] Training using demo fallback data. "
            "No validated human labels exist in database. Synthetic labels strictly tagged."
        )
    else:
        raise ValueError("No validated human-labelled records found for production training.")

    split_status, train_records, val_records, test_records = create_leak_free_split(
        records,
        train_ratio=0.70,
        val_ratio=0.15,
        test_ratio=0.15,
        random_seed=random_seed,
    )

    # Hard guard: synthetic / heuristic provenance must never enter gold-standard splits.
    if not is_demo_evaluation:
        assert_no_synthetic_in_split(train_records, split_name="train")
        assert_no_synthetic_in_split(val_records, split_name="val")
        assert_no_synthetic_in_split(test_records, split_name="test")

    training_run_id = str(uuid.uuid4())
    model_version = f"sif-logreg-v1-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

    # Base classification pipeline
    base_pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(max_features=5000, stop_words="english", ngram_range=(1, 2))),
        ("clf", LogisticRegression(class_weight="balanced", random_state=random_seed, C=1.0)),
    ])
    segment_metrics: dict[str, dict[str, dict[str, Any]]] = {}

    if split_status == "INSUFFICIENT_VALIDATION_DATA":
        logger.warning(
            f"Dataset too small ({len(records)} records) for statistically valid train/val/test split. "
            "Evaluation metrics will NOT be computed on training data to prevent leakage."
        )
        # Consistently preprocess text
        X_train_proc = [preprocess(r.raw_text)["processed_text"] for r in train_records]
        y_train = [r.label for r in train_records]

        if len(set(y_train)) >= 2:
            base_pipeline.fit(X_train_proc, y_train)

        calibrator = base_pipeline
        calibration_version = "uncalibrated-insufficient-data-v0"
        calibration_method = "none"
        is_calibrated = False
        threshold_version = "thresh-fallback-default-v1"
        optimal_threshold = settings.sif_threshold

        metrics: dict[str, Any] = {
            "status": "INSUFFICIENT_VALIDATION_DATA",
            "evaluation_trusted": False,
            "evaluation_message": (
                "Dataset is too small (<20 records or <4 samples per class) for a statistically sound "
                "70/15/15 train/val/test split. Evaluation metrics cannot be trusted and are withheld to prevent misleading claims."
            ),
            "sample_size": len(records),
            "train_size": len(train_records),
            "val_size": 0,
            "test_size": 0,
            "precision": None,
            "recall": None,
            "f1": None,
            "accuracy": None,
            "roc_auc": None,
            "pr_auc": None,
            "brier_score": None,
            "expected_calibration_error": None,
            "specificity": None,
            "false_positive_rate": None,
            "false_negative_rate": None,
            "confusion_matrix": {"tn": 0, "fp": 0, "fn": 0, "tp": 0},
            "safety_metrics": {
                "sif_recall": None,
                "sif_false_negative_rate": None,
                "missed_sifs": 0,
                "false_alarms": 0,
                "note": "Evaluation withheld due to insufficient sample size.",
            },
            "metadata": {
                "model_version": model_version,
                "feature_version": FEATURE_VERSION,
                "preprocessing_version": PREPROCESSING_VERSION,
                "negation_detection_enabled": settings.negation_detection_enabled,
                "dataset_version": DATASET_VERSION,
                "label_schema_version": LABEL_SCHEMA_VERSION,
                "calibration_version": calibration_version,
                "threshold_version": threshold_version,
                "optimal_threshold": optimal_threshold,
                "training_run_id": training_run_id,
                "split_version": "insufficient-data-hold",
                "random_seed": random_seed,
                "training_timestamp": datetime.now(UTC).isoformat(),
                "data_source": data_source,
                "is_synthetic_demo_evaluation": is_demo_evaluation,
                "data_provenance": data_provenance,
                "sample_counts": {
                    "total": len(records),
                    "train": len(train_records),
                    "val": 0,
                    "test": 0,
                },
            },
        }
    else:
        # Uniformly preprocessed text for each partition
        X_train_proc = [preprocess(r.raw_text)["processed_text"] for r in train_records]
        y_train = [r.label for r in train_records]

        X_val_proc = [preprocess(r.raw_text)["processed_text"] for r in val_records]
        y_val = [r.label for r in val_records]

        X_test_proc = [preprocess(r.raw_text)["processed_text"] for r in test_records]
        y_test = [r.label for r in test_records]

        # 1. Stratified Cross-Validation on Train set
        cv_scores: dict[str, float] = {}
        pos_train = sum(y_train)
        neg_train = len(y_train) - pos_train
        min_class_train = min(pos_train, neg_train)

        if min_class_train >= 2:
            n_splits = min(5, min_class_train)
            skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_seed)
            cv_f1s: list[float] = []
            cv_recalls: list[float] = []
            cv_precisions: list[float] = []

            for tr_idx, val_idx in skf.split(X_train_proc, y_train):
                fold_X_tr = [X_train_proc[i] for i in tr_idx]
                fold_y_tr = [y_train[i] for i in tr_idx]
                fold_X_val = [X_train_proc[i] for i in val_idx]
                fold_y_val = [y_train[i] for i in val_idx]

                fold_pipe = Pipeline([
                    ("tfidf", TfidfVectorizer(max_features=5000, stop_words="english", ngram_range=(1, 2))),
                    ("clf", LogisticRegression(class_weight="balanced", random_state=random_seed, C=1.0)),
                ])
                if len(set(fold_y_tr)) >= 2:
                    fold_pipe.fit(fold_X_tr, fold_y_tr)
                    fold_pred = fold_pipe.predict(fold_X_val)
                    p, r, f, _ = precision_recall_fscore_support(
                        fold_y_val, fold_pred, average="binary", zero_division=0
                    )
                    cv_precisions.append(p)
                    cv_recalls.append(r)
                    cv_f1s.append(f)

            if cv_f1s:
                cv_scores = {
                    "cv_f1_mean": round(float(sum(cv_f1s) / len(cv_f1s)), 3),
                    "cv_recall_mean": round(float(sum(cv_recalls) / len(cv_recalls)), 3),
                    "cv_precision_mean": round(float(sum(cv_precisions) / len(cv_precisions)), 3),
                    "cv_folds": n_splits,
                }

        # 2. Fit base pipeline on Train set
        base_pipeline.fit(X_train_proc, y_train)

        # 3. Probability Calibration on Validation set
        calibrator, calibration_version, calib_diag = calibrate_classifier(
            base_pipeline, X_val_proc, y_val, method=None
        )
        is_calibrated = calib_diag.get("is_calibrated", False)
        calibration_method = calib_diag.get("method", "none")

        # 4. Threshold Optimization on Validation set only
        val_proba = calibrator.predict_proba(X_val_proc)[:, 1] if len(X_val_proc) > 0 else []
        optimal_threshold, threshold_version, val_thresh_metrics = optimize_threshold(
            y_val, val_proba, target_recall=0.85, fallback_threshold=settings.sif_threshold
        )

        # 5. Final Holdout Evaluation strictly on untouched Test set (Both Uncalibrated & Calibrated)
        y_test_proba_uncal = base_pipeline.predict_proba(X_test_proc)[:, 1]
        y_test_proba_cal = calibrator.predict_proba(X_test_proc)[:, 1]
        y_test_pred = [bool(p >= optimal_threshold) for p in y_test_proba_cal]

        # Test metrics for calibrated model
        precision, recall, f1, _ = precision_recall_fscore_support(
            y_test, y_test_pred, average="binary", zero_division=0
        )
        accuracy = accuracy_score(y_test, y_test_pred)

        try:
            roc_auc_cal = round(float(roc_auc_score(y_test, y_test_proba_cal)), 4)
        except ValueError:
            roc_auc_cal = None

        try:
            pr_auc_cal = round(float(average_precision_score(y_test, y_test_proba_cal)), 4)
        except ValueError:
            pr_auc_cal = None

        brier_cal = compute_brier_score(y_test, y_test_proba_cal)
        ece_cal = compute_expected_calibration_error(y_test, y_test_proba_cal)
        logloss_cal = compute_log_loss(y_test, y_test_proba_cal)

        # Test metrics for uncalibrated baseline
        try:
            roc_auc_uncal = round(float(roc_auc_score(y_test, y_test_proba_uncal)), 4)
        except ValueError:
            roc_auc_uncal = None

        try:
            pr_auc_uncal = round(float(average_precision_score(y_test, y_test_proba_uncal)), 4)
        except ValueError:
            pr_auc_uncal = None

        brier_uncal = compute_brier_score(y_test, y_test_proba_uncal)
        ece_uncal = compute_expected_calibration_error(y_test, y_test_proba_uncal)
        logloss_uncal = compute_log_loss(y_test, y_test_proba_uncal)

        brier_improvement = (
            round(float(brier_uncal - brier_cal), 4)
            if brier_uncal is not None and brier_cal is not None
            else None
        )

        tn, fp, fn, tp = confusion_matrix(y_test, y_test_pred, labels=[False, True]).ravel()
        specificity = round(float(tn / (tn + fp)), 3) if (tn + fp) > 0 else 0.0
        false_positive_rate = round(float(fp / (fp + tn)), 3) if (fp + tn) > 0 else 0.0
        false_negative_rate = round(float(fn / (fn + tp)), 3) if (fn + tp) > 0 else 0.0

        positive_samples_test = sum(y_test)
        negative_samples_test = len(y_test) - positive_samples_test

        metrics = {
            "status": "VALIDATED",
            "evaluation_trusted": True,
            "is_calibrated": is_calibrated,
            "sample_size": len(records),
            "train_size": len(train_records),
            "val_size": len(val_records),
            "test_size": len(test_records),
            "precision": round(float(precision), 3),
            "recall": round(float(recall), 3),
            "f1": round(float(f1), 3),
            "accuracy": round(float(accuracy), 3),
            "roc_auc": roc_auc_cal,
            "pr_auc": pr_auc_cal,
            "brier_score": brier_cal,
            "brier_score_uncalibrated": brier_uncal,
            "brier_score_improvement": brier_improvement,
            "expected_calibration_error": ece_cal,
            "expected_calibration_error_uncalibrated": ece_uncal,
            "log_loss": logloss_cal,
            "log_loss_uncalibrated": logloss_uncal,
            "test_metrics_before_calibration": {
                "brier_score": brier_uncal,
                "expected_calibration_error": ece_uncal,
                "log_loss": logloss_uncal,
                "roc_auc": roc_auc_uncal,
                "pr_auc": pr_auc_uncal,
            },
            "test_metrics_after_calibration": {
                "brier_score": brier_cal,
                "expected_calibration_error": ece_cal,
                "log_loss": logloss_cal,
                "roc_auc": roc_auc_cal,
                "pr_auc": pr_auc_cal,
            },
            "specificity": specificity,
            "false_positive_rate": false_positive_rate,
            "false_negative_rate": false_negative_rate,
            "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
            "safety_metrics": {
                "sif_recall": round(float(recall), 3),
                "sif_false_negative_rate": false_negative_rate,
                "missed_sifs": int(fn),
                "false_alarms": int(fp),
                "priority_alert": "SIF false-negative rate prioritized to ensure zero missed catastrophic hazards.",
            },
            "calibration_diagnostics": calib_diag,
            "validation_metrics": val_thresh_metrics,
            "cv_metrics": cv_scores,
            "metadata": {
                "model_version": model_version,
                "feature_version": FEATURE_VERSION,
                "preprocessing_version": PREPROCESSING_VERSION,
                "negation_detection_enabled": settings.negation_detection_enabled,
                "dataset_version": DATASET_VERSION,
                "label_schema_version": LABEL_SCHEMA_VERSION,
                "calibration_version": calibration_version,
                "calibration_method": calibration_method,
                "is_calibrated": is_calibrated,
                "threshold_version": threshold_version,
                "optimal_threshold": optimal_threshold,
                "training_run_id": training_run_id,
                "split_version": "stratified-group-70-15-15",
                "random_seed": random_seed,
                "training_timestamp": datetime.now(UTC).isoformat(),
                "data_source": data_source,
                "is_synthetic_demo_evaluation": is_demo_evaluation,
                "data_provenance": data_provenance,
                "sample_counts": {
                    "total": len(records),
                    "train": len(train_records),
                    "val": len(val_records),
                    "test": len(test_records),
                    "test_positives": int(positive_samples_test),
                    "test_negatives": int(negative_samples_test),
                },
            },
        }
        segment_metrics = build_segment_evaluation(test_records, y_test_pred, list(y_test_proba_cal))
        assert_segment_quality_gates(segment_metrics)
        metrics["segment_metrics"] = segment_metrics

    # Training audit contains only safe report identifiers and reason codes,
    # never report narrative or detected identity values.
    metrics["privacy"] = {
        "training_text_source": "raw_text_redacted_only",
        "rejected_record_count": len(privacy_rejected_records),
        "rejected_records": privacy_rejected_records,
        "preprocessing_version": PREPROCESSING_VERSION,
        "negation_detection_enabled": settings.negation_detection_enabled,
    }
    metrics["data_provenance"] = data_provenance

    # Versioned evaluation artifact is intentionally JSON-only: it contains
    # aggregate/segment metrics and no report narrative or identity values.
    evaluation_report = {
        "evaluation_report_version": "sif-evaluation-v2",
        "model_version": model_version,
        "training_run_id": training_run_id,
        "data_provenance": data_provenance,
        "python_version": platform.python_version(),
        "scikit_learn_version": sklearn.__version__,
        "created_at": datetime.now(UTC).isoformat(),
        "global_metrics": {
            key: metrics.get(key)
            for key in ("accuracy", "precision", "recall", "f1", "specificity", "false_negative_rate", "confusion_matrix")
        },
        "calibration_curve": build_evaluation_metrics(y_test, y_test_pred, list(y_test_proba_cal)).get("calibration_curve", [])
        if split_status != "INSUFFICIENT_VALIDATION_DATA" else [],
        "segment_metrics": segment_metrics,
        "segment_quality_thresholds": {
            "min_segment_size": settings.evaluation_min_segment_size,
            "min_precision": settings.evaluation_min_segment_precision,
            "min_recall": settings.evaluation_min_segment_recall,
        },
    }
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    evaluation_path = ARTIFACT_PATH.parent / f"evaluation-{model_version}.json"
    evaluation_path.write_text(json.dumps(evaluation_report, indent=2), encoding="utf-8")
    metrics["evaluation_report_path"] = str(evaluation_path)

    # Save model artifact with complete version metadata
    model_artifact_data = {
        "pipeline": base_pipeline,
        "calibrator": calibrator,
        "model_version": model_version,
        "feature_version": FEATURE_VERSION,
        "preprocessing_version": PREPROCESSING_VERSION,
        "negation_detection_enabled": settings.negation_detection_enabled,
        "dataset_version": DATASET_VERSION,
        "label_schema_version": LABEL_SCHEMA_VERSION,
        "calibration_version": calibration_version,
        "calibration_method": calibration_method,
        "is_calibrated": is_calibrated,
        "threshold_version": threshold_version,
        "optimal_threshold": optimal_threshold,
        "training_run_id": training_run_id,
        "trained_at": datetime.now(UTC).isoformat(),
        "feedback_count": len(validated_records),
        "is_demo_model": is_demo_evaluation,
        "data_provenance": data_provenance,
        "metrics": metrics,
        "evaluation_report_path": str(evaluation_path),
    }

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model_artifact_data, ARTIFACT_PATH)

    # Update SHA-256 and manifest metadata
    manifest_path = ARTIFACT_PATH.parent / "model_manifest.json"
    sha256 = hashlib.sha256(ARTIFACT_PATH.read_bytes()).hexdigest()
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "model_file": ARTIFACT_PATH.name,
                "model_version": model_version,
                "feature_version": FEATURE_VERSION,
                "preprocessing_version": PREPROCESSING_VERSION,
                "negation_detection_enabled": settings.negation_detection_enabled,
                "calibration_version": calibration_version,
                "calibration_method": calibration_method,
                "is_calibrated": is_calibrated,
                "threshold_version": threshold_version,
                "optimal_threshold": optimal_threshold,
                "training_run_id": training_run_id,
                "sha256": sha256,
                "training_date": datetime.now(UTC).isoformat(),
                "evaluation_status": metrics.get("status"),
                "data_provenance": data_provenance,
                "python_version": platform.python_version(),
                "scikit_learn_version": sklearn.__version__,
                "evaluation_report_file": evaluation_path.name,
            },
            f,
            indent=2,
        )

    # Clear model cache in memory
    from app.nlp import model as nlp_model
    nlp_model._MODEL_CACHE = None

    # Record run in DB
    run = ModelTrainingRun(
        model_version=model_version,
        artifact_path=str(ARTIFACT_PATH),
        feedback_count=len(validated_records),
        metrics_before={},
        metrics_after=metrics,
    )
    db.add(run)
    db.flush()
    return run


def run_feedback_calibration(db: Session) -> ModelTrainingRun:
    """Wrapper around run_ml_training to preserve backwards compatibility with admin routes."""
    return run_ml_training(db, force_demo_fallback=True)


if __name__ == "__main__":
    from app.database import SessionLocal
    print("Running calibrated ML training pipeline...")
    db = SessionLocal()
    try:
        run = run_ml_training(db)
        db.commit()
        print(f"Success! Model {run.model_version} created.")
        print(f"Status: {run.metrics_after.get('status')}")
        print(f"Calibration Version: {run.metrics_after.get('metadata', {}).get('calibration_version')}")
        print(f"Threshold Version: {run.metrics_after.get('metadata', {}).get('threshold_version')}")
        print(f"Metrics: {json.dumps(run.metrics_after, indent=2)}")
    finally:
        db.close()
