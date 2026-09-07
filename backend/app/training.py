"""Machine learning training entry point and persistence helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import logging

import joblib
from sqlalchemy.orm import Session
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import precision_recall_fscore_support, accuracy_score, roc_auc_score, average_precision_score, confusion_matrix

from app.config import settings
from app.models import AnalystFeedback, ModelTrainingRun, Report, ReportReview, SifClassification
from app.nlp.model import ARTIFACT_PATH

logger = logging.getLogger(__name__)

def _feedback_label(feedback: AnalystFeedback) -> bool | None:
    if feedback.feedback_type == "override_sif":
        value = (feedback.new_value or {}).get("sif_label")
        return bool(value) if isinstance(value, bool) else None
    if feedback.feedback_type == "confirm_sif":
        value = (feedback.previous_value or {}).get("sif_label")
        return bool(value) if isinstance(value, bool) else None
    return None

def run_ml_training(db: Session, force_demo_fallback: bool = True) -> ModelTrainingRun:
    """Train a new TF-IDF + Logistic Regression model for SIF classification.
    
    If there is not enough analyst feedback, it falls back to using the heuristically
    generated labels from the seed dataset if force_demo_fallback is True.
    """
    # 1. Fetch analyst reviews & feedback
    reviews = db.query(ReportReview).order_by(ReportReview.created_at.desc()).all()
    labels_by_report: dict[str, bool] = {}
    for r in reviews:
        if r.report_id not in labels_by_report:
            labels_by_report[r.report_id] = r.final_sif_label

    feedback_rows = (
        db.query(AnalystFeedback)
        .filter(AnalystFeedback.feedback_type.in_(["confirm_sif", "override_sif"]))
        .order_by(AnalystFeedback.created_at.desc())
        .all()
    )
    for feedback in feedback_rows:
        label = _feedback_label(feedback)
        if label is not None and feedback.report_id not in labels_by_report:
            labels_by_report[feedback.report_id] = label

    # 2. Fetch all reports
    reports = db.query(Report).all()
    
    X_raw = []
    y_raw = []
    
    # 3. Build training dataset
    for report in reports:
        # Get label from AnalystFeedback if available
        if report.id in labels_by_report:
            X_raw.append(report.processed_text or report.raw_text_redacted)
            y_raw.append(labels_by_report[report.id])
        elif force_demo_fallback and report.classification is not None:
            # Fallback to the heuristic label (often present in seed data)
            X_raw.append(report.processed_text or report.raw_text_redacted)
            y_raw.append(report.classification.sif_label)
            
    if not X_raw:
        raise ValueError("No labeled records found for training.")

    # Convert to standard python bools just in case
    y_raw = [bool(lbl) for lbl in y_raw]
    
    feedback_count = len(labels_by_report)
    
    # If we have very few examples, we skip the test split or use a tiny one
    if len(X_raw) < 10:
        # Fallback to training on everything and testing on everything if data is extremely sparse
        X_train, X_test, y_train, y_test = X_raw, X_raw, y_raw, y_raw
    else:
        # We try to stratify if we have both classes, else we might fail stratification
        has_both_classes = len(set(y_raw)) > 1
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X_raw, y_raw, test_size=0.2, random_state=42, stratify=y_raw if has_both_classes else None
            )
        except ValueError:
            # Fallback if stratification fails due to too few samples of a class
            X_train, X_test, y_train, y_test = train_test_split(
                X_raw, y_raw, test_size=0.2, random_state=42
            )
            
    # 4. Define and train pipeline
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(max_features=5000, stop_words="english")),
        ("clf", LogisticRegression(class_weight="balanced", random_state=42))
    ])
    
    # Check if there is only 1 class in the training data (can happen in extreme edge cases)
    if len(set(y_train)) < 2:
        logger.warning("Only one class present in training data. Model will not learn meaningful differences.")
        
    pipeline.fit(X_train, y_train)
    
    # 5. Evaluate
    # If the test set only has 1 class, metrics might be poorly defined, but we catch it with zero_division
    y_pred = pipeline.predict(X_test)
    # Basic binary metrics
    precision, recall, f1, _ = precision_recall_fscore_support(
        y_test, y_pred, average="binary", zero_division=0
    )
    # Additional metrics
    accuracy = accuracy_score(y_test, y_pred)
    # ROC AUC and PR AUC require both classes present; otherwise set to None
    try:
        roc_auc = roc_auc_score(y_test, pipeline.predict_proba(X_test)[:, 1])
    except ValueError:
        roc_auc = None
    try:
        pr_auc = average_precision_score(y_test, pipeline.predict_proba(X_test)[:, 1])
    except ValueError:
        pr_auc = None
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred, labels=[False, True]).ravel()
    positive_samples = sum(y_test)
    negative_samples = len(y_test) - positive_samples

    metrics = {
        "sample_size": len(X_raw),
        "test_size": len(X_test),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "accuracy": round(accuracy, 3),
        "roc_auc": round(roc_auc, 3) if roc_auc is not None else None,
        "pr_auc": round(pr_auc, 3) if pr_auc is not None else None,
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "positive_samples": int(positive_samples),
        "negative_samples": int(negative_samples),
    }
    
    # 6. Save model artifact
    version = f"tfidf-logreg-v1-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    
    model_data = {
        "pipeline": pipeline,
        "model_version": version,
        "feedback_count": feedback_count,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model_data, ARTIFACT_PATH)

    # Update SHA-256 in model_manifest.json
    import hashlib
    manifest_path = ARTIFACT_PATH.parent / "model_manifest.json"
    sha256 = hashlib.sha256(ARTIFACT_PATH.read_bytes()).hexdigest()
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({"model_file": ARTIFACT_PATH.name, "model_version": version, "sha256": sha256}, f, indent=2)

    # Clear model cache in memory
    from app.nlp import model as nlp_model
    nlp_model._MODEL_CACHE = None

    
    # 7. Record run in DB
    run = ModelTrainingRun(
        model_version=version,
        artifact_path=str(ARTIFACT_PATH),
        feedback_count=feedback_count,
        metrics_before={},  # Not easily computable without loading old model
        metrics_after=metrics,
    )
    db.add(run)
    db.flush()
    return run

# Keep the old function signature for compatibility with admin.py, but wire it to the new ML training
def run_feedback_calibration(db: Session) -> ModelTrainingRun:
    """Wrapper around run_ml_training to preserve backwards compatibility with admin routes."""
    return run_ml_training(db, force_demo_fallback=True)

if __name__ == "__main__":
    from app.database import SessionLocal
    print("Running ML training pipeline...")
    db = SessionLocal()
    try:
        run = run_ml_training(db)
        db.commit()
        print(f"Success! Model {run.model_version} created.")
        print(f"Metrics: {run.metrics_after}")
    finally:
        db.close()
