from datetime import date, datetime, timezone

from pydantic import BaseModel, Field
from typing import Optional

class FilterParams(BaseModel):
    start_date: Optional[date] = Field(None, description="Start of date range filter")
    end_date: Optional[date] = Field(None, description="End of date range filter")
    site_id: Optional[str] = Field(None, description="Site identifier filter")
    department: Optional[str] = Field(None, description="Department filter")
    lsr_category: Optional[str] = Field(None, description="LSR category filter")
    min_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Minimum SIF confidence/probability")

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_user, scoped_site_ids
from app.database import get_db
from app.models import LsrTag, PrecursorTriple, Recommendation, Report, ReportReview, Site, SifClassification, User, utcnow
from app.nlp.lsr import get_rule_by_id, get_rule_by_name, load_canonical_lsr_rules
from app.priority.engine import score_report
from app.schemas import (
    AgreementAnalyticsOut,
    DensityRow,
    ErrorAnalysisOut,
    InterventionEffectivenessOut,
    LifecycleKpiOut,
    LsrDistributionRow,
    ModelDriftOut,
    ModelHealthOut,
    PrioritySummaryRow,
    SiteOut,
    TrendRow,
)
from app.services import analytics_service


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _scoped(q, user: User):
    allowed = scoped_site_ids(user)
    if allowed is not None:
        q = q.filter(Report.site_id.in_(allowed or ["__none__"]))
    return q

def _apply_filters(q, filters: 'FilterParams'):
    """Apply common filter parameters to a SQLAlchemy query.
    All params are optional.
    """
    if not hasattr(filters, "start_date"):
        return q
    if filters.start_date:
        q = q.filter(func.date(Report.reported_at) >= filters.start_date)
    if filters.end_date:
        q = q.filter(func.date(Report.reported_at) <= filters.end_date)
    if filters.site_id:
        q = q.filter(Report.site_id == filters.site_id)
    if hasattr(Report, "department") and getattr(filters, "department", None):
        q = q.filter(Report.department == filters.department)
    if filters.min_confidence is not None:
        q = q.filter(SifClassification.sif_probability >= filters.min_confidence)
    return q


@router.get("/sites", response_model=list[SiteOut])
def list_sites(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Site)
    allowed = scoped_site_ids(user)
    if allowed is not None:
        q = q.filter(Site.id.in_(allowed or ["__none__"]))
    return [SiteOut(id=s.id, name=s.name, region=s.region) for s in q.order_by(Site.name).all()]


@router.get("/sif-density", response_model=list[DensityRow])
def sif_density(
    filters: FilterParams = Depends(),
    group_by: str = Query("site", pattern="^(site|department|activity)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sif_sum = func.sum(case((SifClassification.sif_label.is_(True), 1), else_=0))
    total = func.count(Report.id)
    q = db.query(Report).join(SifClassification, SifClassification.report_id == Report.id)
    q = _scoped(q, user)
    q = _apply_filters(q, filters)

    if group_by == "department":
        rows = (
            q.with_entities(Report.department, sif_sum, total)
            .group_by(Report.department)
            .all()
        )
        return [
            DensityRow(
                group_label=label or "Unspecified",
                sif_count=int(sif or 0),
                total_count=int(tot or 0),
                sif_rate=round((sif or 0) / tot, 3) if tot else 0,
            )
            for label, sif, tot in rows
        ]
    if group_by == "activity":
        q2 = (
            db.query(
                PrecursorTriple.activity,
                func.sum(case((SifClassification.sif_label.is_(True), 1), else_=0)).label("sif_cnt"),
                func.count(func.distinct(Report.id)).label("tot_cnt"),
            )
            .join(Report, Report.id == PrecursorTriple.report_id)
            .outerjoin(SifClassification, SifClassification.report_id == Report.id)
        )
        q2 = _scoped(q2, user)
        q2 = _apply_filters(q2, filters)
        rows = q2.group_by(PrecursorTriple.activity).all()
        out = [
            DensityRow(
                group_label=a or "Unspecified",
                sif_count=int(sif or 0),
                total_count=int(tot or 0),
                sif_rate=round((sif or 0) / tot, 3) if tot else 0.0,
            )
            for a, sif, tot in rows
        ]
        out.sort(key=lambda r: r.sif_rate, reverse=True)
        return out

    rows = (
        q.join(Site, Site.id == Report.site_id)
        .with_entities(Site.name, sif_sum, total)
        .group_by(Site.name)
        .all()
    )
    out = [
        DensityRow(
            group_label=name,
            sif_count=int(sif or 0),
            total_count=int(tot or 0),
            sif_rate=round((sif or 0) / tot, 3) if tot else 0,
        )
        for name, sif, tot in rows
    ]
    out.sort(key=lambda r: r.sif_rate, reverse=True)
    return out


@router.get("/lsr-distribution", response_model=list[LsrDistributionRow])
def lsr_distribution(
    filters: FilterParams = Depends(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    canonical_rules = load_canonical_lsr_rules()

    q = (
        db.query(LsrTag.lsr_category, LsrTag.rule_id, func.count(func.distinct(Report.id)))
        .join(Report, Report.id == LsrTag.report_id)
    )
    q = _scoped(q, user)
    q = _apply_filters(q, filters)

    rows = q.group_by(LsrTag.lsr_category, LsrTag.rule_id).all()

    counts_by_rule_id: dict[str, int] = {r.id: 0 for r in canonical_rules}
    for cat, rid, count in rows:
        matched_rule = get_rule_by_id(rid) if rid else get_rule_by_name(cat)
        if matched_rule:
            counts_by_rule_id[matched_rule.id] = counts_by_rule_id.get(matched_rule.id, 0) + int(count)

    return [
        LsrDistributionRow(
            rule_id=r.id,
            rule_name=r.name,
            lsr_category=r.name,
            count=counts_by_rule_id.get(r.id, 0),
        )
        for r in canonical_rules
    ]


@router.get("/trend", response_model=list[TrendRow])
def trend(
    filters: FilterParams = Depends(),
    interval: str = Query("week", pattern="^(day|week|month)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        if interval == "day":
            bucket = func.strftime("%Y-%m-%d", Report.reported_at)
        elif interval == "month":
            bucket = func.strftime("%Y-%m-01", Report.reported_at)
        else:
            bucket = func.strftime("%Y-%W", Report.reported_at)
    else:
        trunc = {"day": "day", "week": "week", "month": "month"}[interval]
        bucket = func.date_trunc(trunc, Report.reported_at)

    q = db.query(
        bucket.label("period"),
        func.sum(case((SifClassification.sif_label.is_(True), 1), else_=0)),
        func.count(Report.id),
    ).join(SifClassification, SifClassification.report_id == Report.id)
    q = _scoped(q, user)
    q = _apply_filters(q, filters)
    rows = q.group_by("period").order_by("period").all()
    return [
        TrendRow(period=str(p), sif_count=int(s or 0), total_count=int(t or 0))
        for p, s, t in rows
        if p is not None
    ]


@router.get("/kpis")
def kpis(filters: FilterParams = Depends(), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Report).join(SifClassification, SifClassification.report_id == Report.id)
    q = _scoped(q, user)
    q = _apply_filters(q, filters)
    total = q.count()
    sif = q.filter(SifClassification.sif_label.is_(True)).count()
    avg = db.query(func.avg(SifClassification.sif_probability)).join(Report).filter(
        SifClassification.report_id == Report.id
    )
    avg = _scoped(avg, user)
    avg = _apply_filters(avg, filters).scalar() or 0
    pending = q.filter(Report.lifecycle_status.in_(["INGESTED", "AI_ANALYZED", "HSE_REVIEW", "REOPENED"])).count()
    return {
        "total_reports": total,
        "sif_flagged": sif,
        "sif_rate": round(sif / total, 3) if total else 0,
        "avg_confidence": round(float(avg), 3),
        "queue_size": pending,
    }


@router.get("/lifecycle-kpis", response_model=LifecycleKpiOut)
def get_lifecycle_kpis(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Computes dynamic case lifecycle and action KPIs directly from database."""
    base_q = _scoped(db.query(Report), user)

    pending = base_q.filter(Report.lifecycle_status.in_(["INGESTED", "AI_ANALYZED", "HSE_REVIEW", "REOPENED"])).count()
    confirmed = base_q.filter(Report.lifecycle_status == "CONFIRMED").count()
    overridden = base_q.filter(Report.lifecycle_status == "OVERRIDDEN").count()
    resolved = base_q.filter(Report.lifecycle_status == "RESOLVED").count()
    reopened = base_q.filter(Report.lifecycle_status == "REOPENED").count()

    # Open actions
    open_actions_count = (
        db.query(Recommendation)
        .join(Report, Report.id == Recommendation.report_id)
        .filter(Recommendation.status.in_(["ACCEPTED", "EDITED", "IMPLEMENTED"]))
        .count()
    )

    # Overdue actions
    now_dt = utcnow()
    overdue_count = (
        db.query(Recommendation)
        .join(Report, Report.id == Recommendation.report_id)
        .filter(
            Recommendation.status.in_(["ACCEPTED", "EDITED", "IMPLEMENTED"]),
            Recommendation.due_date.isnot(None),
            Recommendation.due_date < now_dt,
        )
        .count()
    )

    # Agreement rate
    reviews = (
        db.query(ReportReview)
        .join(Report, Report.id == ReportReview.report_id)
        .all()
    )
    if reviews:
        agreed = sum(1 for r in reviews if r.ai_sif_label == r.final_sif_label)
        agreement_rate = round((agreed / len(reviews)) * 100.0, 1)
    else:
        agreement_rate = 100.0

    total_cases = base_q.count()

    return LifecycleKpiOut(
        pending_review=pending,
        confirmed_sif=confirmed,
        ai_overrides=overridden,
        open_actions=open_actions_count,
        overdue_actions=overdue_count,
        resolved_cases=resolved,
        reopened_cases=reopened,
        agreement_rate=agreement_rate,
        total_cases=total_cases,
    )


@router.get("/agreement-analytics", response_model=AgreementAnalyticsOut)
def get_agreement_analytics(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Computes AI vs Human Agreement metrics, false positives, false negatives, and override reasons."""
    reviews = (
        db.query(ReportReview)
        .join(Report, Report.id == ReportReview.report_id)
        .order_by(ReportReview.created_at.desc())
        .all()
    )
    total = len(reviews)
    if total == 0:
        return AgreementAnalyticsOut(
            total_reviewed=0,
            agreement_count=0,
            agreement_rate=100.0,
            confirm_count=0,
            confirm_rate=100.0,
            override_count=0,
            override_rate=0.0,
            false_positives=0,
            false_negatives=0,
            reason_breakdown={},
        )

    agreed = sum(1 for r in reviews if r.ai_sif_label == r.final_sif_label)
    confirms = sum(1 for r in reviews if r.decision == "CONFIRMED")
    overrides = sum(1 for r in reviews if r.decision == "OVERRIDDEN")
    fp = sum(1 for r in reviews if r.ai_sif_label is True and r.final_sif_label is False)
    fn = sum(1 for r in reviews if r.ai_sif_label is False and r.final_sif_label is True)

    reasons: dict[str, int] = {}
    for r in reviews:
        if r.decision == "OVERRIDDEN" and r.reason:
            clean_reason = r.reason.strip()
            reasons[clean_reason] = reasons.get(clean_reason, 0) + 1

    return AgreementAnalyticsOut(
        total_reviewed=total,
        agreement_count=agreed,
        agreement_rate=round((agreed / total) * 100.0, 1),
        confirm_count=confirms,
        confirm_rate=round((confirms / total) * 100.0, 1),
        override_count=overrides,
        override_rate=round((overrides / total) * 100.0, 1),
        false_positives=fp,
        false_negatives=fn,
        reason_breakdown=reasons,
    )


@router.get("/priority-summary", response_model=list[PrioritySummaryRow])
def priority_summary(
    filters: FilterParams = Depends(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Report).options(
        joinedload(Report.classification),
        joinedload(Report.lsr_tags),
        joinedload(Report.triples),
        joinedload(Report.site),
    )
    q = _scoped(q, user)
    q = _apply_filters(q, filters)
    reports = q.all()
    tier_counts: dict[str, int] = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for r in reports:
        p = score_report(r, db)
        tier_counts[p.tier] = tier_counts.get(p.tier, 0) + 1
    total = len(reports)
    return [
        PrioritySummaryRow(
            tier=t,  # type: ignore[arg-type]
            count=count,
            percentage=round((count / total) * 100.0, 1) if total > 0 else 0.0,
        )
        for t, count in tier_counts.items()
    ]


@router.get("/model-health", response_model=ModelHealthOut)
def get_model_health(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    allowed = scoped_site_ids(user)
    return analytics_service.compute_model_health(db, allowed)


@router.get("/error-analysis", response_model=ErrorAnalysisOut)
def get_error_analysis(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    allowed = scoped_site_ids(user)
    return analytics_service.compute_error_analysis(db, allowed)


@router.get("/model-drift", response_model=ModelDriftOut)
def get_model_drift(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return analytics_service.compute_model_version_drift(db)


@router.get("/intervention-effectiveness", response_model=InterventionEffectivenessOut)
def get_intervention_effectiveness(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    allowed = scoped_site_ids(user)
    return analytics_service.compute_intervention_effectiveness(db, allowed)


