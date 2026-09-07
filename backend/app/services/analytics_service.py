"""Model Monitoring, Agreement Analytics & Safety Effectiveness service.

Pure query functions — no route logic, no side effects.
All functions accept a SQLAlchemy Session and optional site-scope filter.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    LsrTag,
    ModelTrainingRun,
    Recommendation,
    Report,
    ReportReview,
    SifClassification,
    Site,
)

logger = logging.getLogger(__name__)

MIN_REVIEW_THRESHOLD = 10


# ---------------------------------------------------------------------------
# 1. Model Health & Agreement
# ---------------------------------------------------------------------------

def compute_model_health(db: Session, site_ids: list[str] | None = None) -> dict:
    """Confusion matrix, Cohen's Kappa, agreement rate, per-model-version breakdown."""
    q = db.query(ReportReview).join(Report, Report.id == ReportReview.report_id)
    if site_ids is not None:
        q = q.filter(Report.site_id.in_(site_ids or ["__none__"]))
    reviews = q.order_by(ReportReview.created_at.desc()).all()

    total = len(reviews)
    insufficient = total < MIN_REVIEW_THRESHOLD

    if total == 0:
        return {
            "total_reviewed": 0,
            "insufficient_data": True,
            "agreement_rate": 0.0,
            "cohen_kappa": 0.0,
            "confusion_matrix": {"tp": 0, "tn": 0, "fp": 0, "fn": 0},
            "false_positive_rate": 0.0,
            "false_negative_rate": 0.0,
            "agreement_by_model_version": {},
        }

    tp = tn = fp = fn = 0
    version_agree: dict[str, list[bool]] = defaultdict(list)

    for r in reviews:
        ai = r.ai_sif_label
        human = r.final_sif_label
        if ai and human:
            tp += 1
        elif not ai and not human:
            tn += 1
        elif ai and not human:
            fp += 1
        else:
            fn += 1
        version_agree[r.ai_model_version].append(ai == human)

    agreement_rate = round((tp + tn) / total * 100, 1) if total else 0.0
    fp_rate = round(fp / (fp + tn) * 100, 1) if (fp + tn) > 0 else 0.0
    fn_rate = round(fn / (fn + tp) * 100, 1) if (fn + tp) > 0 else 0.0

    # Cohen's Kappa
    po = (tp + tn) / total
    pe_ai_pos = (tp + fp) / total
    pe_hu_pos = (tp + fn) / total
    pe = pe_ai_pos * pe_hu_pos + (1 - pe_ai_pos) * (1 - pe_hu_pos)
    kappa = round((po - pe) / (1 - pe), 3) if pe < 1.0 else 1.0

    agreement_by_version = {
        ver: round(sum(agrees) / len(agrees) * 100, 1)
        for ver, agrees in version_agree.items()
    }

    return {
        "total_reviewed": total,
        "insufficient_data": insufficient,
        "agreement_rate": agreement_rate,
        "cohen_kappa": kappa,
        "confusion_matrix": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "false_positive_rate": fp_rate,
        "false_negative_rate": fn_rate,
        "agreement_by_model_version": agreement_by_version,
    }


# ---------------------------------------------------------------------------
# 2. Error Analysis (FP / FN drilldown)
# ---------------------------------------------------------------------------

def compute_error_analysis(db: Session, site_ids: list[str] | None = None) -> dict:
    """Detailed FP/FN lists with excerpts and breakdowns by site/model/LSR."""
    q = (
        db.query(ReportReview, Report, Site)
        .join(Report, Report.id == ReportReview.report_id)
        .outerjoin(Site, Site.id == Report.site_id)
    )
    if site_ids is not None:
        q = q.filter(Report.site_id.in_(site_ids or ["__none__"]))
    rows = q.order_by(ReportReview.created_at.desc()).all()

    total = len(rows)
    insufficient = total < MIN_REVIEW_THRESHOLD

    fp_list: list[dict] = []
    fn_list: list[dict] = []
    errors_by_version: dict[str, dict[str, int]] = defaultdict(lambda: {"fp": 0, "fn": 0})
    errors_by_site: dict[str, dict[str, int]] = defaultdict(lambda: {"fp": 0, "fn": 0})

    for review, report, site in rows:
        ai = review.ai_sif_label
        human = review.final_sif_label
        is_fp = ai and not human
        is_fn = not ai and human

        if not is_fp and not is_fn:
            continue

        excerpt = (report.raw_text_redacted or "")[:200]
        site_name = site.name if site else "Unknown"
        item = {
            "report_id": report.id,
            "source_report_id": report.source_report_id,
            "excerpt": excerpt,
            "ai_sif_label": ai,
            "human_sif_label": human,
            "model_version": review.ai_model_version,
            "site_name": site_name,
            "reviewed_at": review.created_at.isoformat() if review.created_at else None,
        }

        if is_fp:
            fp_list.append(item)
            errors_by_version[review.ai_model_version]["fp"] += 1
            errors_by_site[site_name]["fp"] += 1
        else:
            fn_list.append(item)
            errors_by_version[review.ai_model_version]["fn"] += 1
            errors_by_site[site_name]["fn"] += 1

    # Error breakdown by LSR rule — which hazard categories are most misclassified?
    error_report_ids = [e["report_id"] for e in fp_list + fn_list]
    errors_by_lsr: dict[str, dict[str, int]] = defaultdict(lambda: {"fp": 0, "fn": 0})
    if error_report_ids:
        lsr_rows = (
            db.query(LsrTag.report_id, LsrTag.rule_name)
            .filter(LsrTag.report_id.in_(error_report_ids))
            .all()
        )
        # Build report_id -> error_type mapping
        fp_ids = {e["report_id"] for e in fp_list}
        for report_id, rule_name in lsr_rows:
            if rule_name:
                error_type = "fp" if report_id in fp_ids else "fn"
                errors_by_lsr[rule_name][error_type] += 1

    return {
        "insufficient_data": insufficient,
        "false_positives": fp_list[:50],  # Cap at 50 for API performance
        "false_negatives": fn_list[:50],
        "errors_by_model_version": dict(errors_by_version),
        "errors_by_site": dict(errors_by_site),
        "errors_by_lsr": dict(errors_by_lsr),
    }


# ---------------------------------------------------------------------------
# 3. Model Version Drift
# ---------------------------------------------------------------------------

def compute_model_version_drift(db: Session) -> dict:
    """Training run metrics over time to detect performance drift."""
    runs = db.query(ModelTrainingRun).order_by(ModelTrainingRun.created_at.asc()).all()

    versions: list[dict] = []
    for run in runs:
        metrics = run.metrics_after or {}
        versions.append({
            "model_version": run.model_version,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "feedback_count": run.feedback_count,
            "precision": metrics.get("precision"),
            "recall": metrics.get("recall"),
            "f1": metrics.get("f1"),
            "roc_auc": metrics.get("roc_auc"),
            "accuracy": metrics.get("accuracy"),
            "sample_size": metrics.get("sample_size"),
        })

    # Detect regression: latest F1 < previous F1
    has_regression = False
    if len(versions) >= 2:
        latest_f1 = versions[-1].get("f1")
        prev_f1 = versions[-2].get("f1")
        if latest_f1 is not None and prev_f1 is not None:
            has_regression = latest_f1 < prev_f1

    return {
        "versions": versions,
        "has_regression": has_regression,
    }


# ---------------------------------------------------------------------------
# 4. Intervention Effectiveness
# ---------------------------------------------------------------------------

def compute_intervention_effectiveness(db: Session, site_ids: list[str] | None = None) -> dict:
    """Recommendation funnel, resolution velocity, before/after SIF rate."""
    rec_q = db.query(Recommendation)
    if site_ids is not None:
        rec_q = rec_q.join(Report, Report.id == Recommendation.report_id).filter(
            Report.site_id.in_(site_ids or ["__none__"])
        )
    recs = rec_q.all()
    total = len(recs)
    insufficient = total < 5

    accepted = sum(1 for r in recs if r.status in ("ACCEPTED", "EDITED", "IMPLEMENTED", "RESOLVED"))
    rejected = sum(1 for r in recs if r.status == "REJECTED")
    implemented = sum(1 for r in recs if r.status in ("IMPLEMENTED", "RESOLVED"))
    resolved = sum(1 for r in recs if r.status == "RESOLVED")

    acceptance_rate = round(accepted / total * 100, 1) if total else 0.0
    implementation_rate = round(implemented / total * 100, 1) if total else 0.0
    resolution_rate = round(resolved / total * 100, 1) if total else 0.0

    # Mean days to resolution
    report_q = db.query(Report).filter(
        Report.lifecycle_status == "RESOLVED",
        Report.resolved_at.isnot(None),
    )
    if site_ids is not None:
        report_q = report_q.filter(Report.site_id.in_(site_ids or ["__none__"]))
    resolved_reports = report_q.all()

    if resolved_reports:
        total_days = 0.0
        count = 0
        for rpt in resolved_reports:
            if rpt.resolved_at and rpt.ingested_at:
                delta = (rpt.resolved_at - rpt.ingested_at).total_seconds() / 86400
                total_days += delta
                count += 1
        mean_days = round(total_days / count, 1) if count else None
    else:
        mean_days = None

    # Monthly resolution trend
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        month_bucket = func.strftime("%Y-%m", Report.resolved_at)
    else:
        month_bucket = func.to_char(func.date_trunc("month", Report.resolved_at), "YYYY-MM")

    monthly_q = (
        db.query(month_bucket.label("month"), func.count(Report.id).label("count"))
        .filter(Report.lifecycle_status == "RESOLVED", Report.resolved_at.isnot(None))
    )
    if site_ids is not None:
        monthly_q = monthly_q.filter(Report.site_id.in_(site_ids or ["__none__"]))
    monthly_rows = monthly_q.group_by("month").order_by("month").all()
    monthly_trend = [{"month": str(m), "resolved_count": int(c)} for m, c in monthly_rows if m]

    # Before/After SIF rate — compare first half vs second half by reported_at
    all_reports_q = db.query(Report).join(SifClassification, SifClassification.report_id == Report.id)
    if site_ids is not None:
        all_reports_q = all_reports_q.filter(Report.site_id.in_(site_ids or ["__none__"]))
    all_reports = all_reports_q.order_by(Report.reported_at.asc()).all()

    sif_rate_before = None
    sif_rate_after = None
    if len(all_reports) >= 10:
        mid = len(all_reports) // 2
        first_half = all_reports[:mid]
        second_half = all_reports[mid:]
        fh_sif = sum(1 for r in first_half if r.classification and r.classification.sif_label)
        sh_sif = sum(1 for r in second_half if r.classification and r.classification.sif_label)
        sif_rate_before = round(fh_sif / len(first_half) * 100, 1) if first_half else None
        sif_rate_after = round(sh_sif / len(second_half) * 100, 1) if second_half else None

    return {
        "insufficient_data": insufficient,
        "total_recommendations": total,
        "accepted": accepted,
        "rejected": rejected,
        "implemented": implemented,
        "resolved": resolved,
        "acceptance_rate": acceptance_rate,
        "implementation_rate": implementation_rate,
        "resolution_rate": resolution_rate,
        "mean_days_to_resolution": mean_days,
        "monthly_resolution_trend": monthly_trend,
        "sif_rate_before_intervention": sif_rate_before,
        "sif_rate_after_intervention": sif_rate_after,
    }


# ---------------------------------------------------------------------------
# 5. Agreement Trend (monthly)
# ---------------------------------------------------------------------------

def compute_agreement_trend(db: Session, site_ids: list[str] | None = None) -> list[dict]:
    """Monthly agreement rate, FP rate, and FN rate for trend visualization."""
    q = db.query(ReportReview).join(Report, Report.id == ReportReview.report_id)
    if site_ids is not None:
        q = q.filter(Report.site_id.in_(site_ids or ["__none__"]))
    reviews = q.order_by(ReportReview.created_at.asc()).all()

    monthly: dict[str, dict] = defaultdict(lambda: {"total": 0, "agree": 0, "fp": 0, "fn": 0})
    for r in reviews:
        if not r.created_at:
            continue
        month_key = r.created_at.strftime("%Y-%m")
        monthly[month_key]["total"] += 1
        if r.ai_sif_label == r.final_sif_label:
            monthly[month_key]["agree"] += 1
        if r.ai_sif_label and not r.final_sif_label:
            monthly[month_key]["fp"] += 1
        if not r.ai_sif_label and r.final_sif_label:
            monthly[month_key]["fn"] += 1

    result = []
    for month in sorted(monthly.keys()):
        data = monthly[month]
        total = data["total"]
        result.append({
            "month": month,
            "total_reviews": total,
            "agreement_rate": round(data["agree"] / total * 100, 1) if total else 0.0,
            "false_positive_rate": round(data["fp"] / total * 100, 1) if total else 0.0,
            "false_negative_rate": round(data["fn"] / total * 100, 1) if total else 0.0,
        })
    return result
