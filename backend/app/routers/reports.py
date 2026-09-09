from datetime import date, datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_user, require_roles, scoped_site_ids
from app.database import get_db
from app.lifecycle import transition_report_lifecycle
from app.models import (
    AnalystDecision,
    AnalystFeedback,
    AuditLog,
    ClusterMember,
    LabelReview,
    LsrTag,
    PrecursorFeedback,
    PrecursorTriple,
    Recommendation,
    Report,
    ReportReview,
    SifClassification,
    Site,
    User,
    utcnow,
)
from app.nlp.lsr import get_canonical_rule_metadata, get_rule_by_id, get_rule_by_name
from app.priority.engine import score_report
from app.schemas import (
    AiPredictionOut,
    AnalystDecisionOut,
    CaseReopenIn,
    CaseResolutionIn,
    LabelReviewIn,
    LabelReviewOut,
    LsrEvidenceItem,
    LsrReviewIn,
    LsrRuleMetadataOut,
    LsrTagOut,
    PaginatedReports,
    PhraseWeight,
    PrecursorReviewIn,
    PriorityAdjustmentIn,
    ReportConfirmIn,
    ReportCreate,
    ReportDetail,
    ReportLabelHistoryOut,
    ReportOverrideIn,
    ReportReviewOut,
    ReportSummary,
    ReviewerAgreementSummaryOut,
    SifClassificationOut,
    TimelineEventOut,
)
from app.services import ingest_and_process, log_ingestion_run, rebuild_clusters, write_audit

router = APIRouter(tags=["Reports"])


def _to_lsr_tag_out(t: LsrTag) -> LsrTagOut:
    rule = get_rule_by_id(t.rule_id) if t.rule_id else get_rule_by_name(t.lsr_category)
    rule_id = t.rule_id or (rule.id if rule else None)
    rule_name = t.rule_name or (rule.name if rule else t.lsr_category)
    evidence_items = []
    if t.evidence:
        for ev in t.evidence:
            if isinstance(ev, dict):
                evidence_items.append(LsrEvidenceItem(text=ev.get("text", ""), type=ev.get("type", "phrase")))
            elif isinstance(ev, str):
                evidence_items.append(LsrEvidenceItem(text=ev, type="phrase"))
    return LsrTagOut(
        rule_id=rule_id,
        rule_name=rule_name,
        lsr_category=rule_name,
        confidence=t.confidence,
        source=t.source,  # type: ignore[arg-type]
        evidence=evidence_items,
    )


def _apply_site_scope(query, user: User):
    allowed = scoped_site_ids(user)
    if allowed is not None:
        query = query.filter(Report.site_id.in_(allowed or ["__none__"]))
    return query


def _summary(report: Report, db: Session | None = None) -> ReportSummary:
    clf = report.classification
    tags = [_to_lsr_tag_out(t) for t in report.lsr_tags]
    text = report.raw_text_redacted or ""
    priority_out = score_report(report, db)
    ai_prediction = None
    if clf:
        ai_prediction = AiPredictionOut(
            ai_label=clf.sif_label,
            ai_probability=clf.sif_probability,
            model_version=clf.model_version,
            model_timestamp=clf.classified_at,
        )
    analyst_decision = None
    if report.analyst_decisions:
        ad = report.analyst_decisions[0]
        analyst_decision = AnalystDecisionOut(
            id=ad.id,
            report_id=ad.report_id,
            analyst_id=ad.analyst_id,
            analyst_label=ad.analyst_label,
            review_action=ad.review_action,
            analyst_comment=ad.analyst_comment,
            ai_sif_label_at_time=ad.ai_sif_label_at_time,
            ai_sif_probability_at_time=ad.ai_sif_probability_at_time,
            reviewed_at=ad.reviewed_at,
        )
    return ReportSummary(
        id=report.id,
        report_type=report.report_type,
        site_id=report.site_id,
        site_name=report.site.name if report.site else None,
        department=report.department,
        reported_at=report.reported_at,
        sif_label=clf.sif_label if clf else None,
        sif_probability=clf.sif_probability if clf else None,
        lifecycle_status=report.lifecycle_status or "AI_ANALYZED",
        final_sif_label=report.final_sif_label,
        final_priority=report.final_priority,
        lsr_tags=tags,
        excerpt=text[:180] + ("…" if len(text) > 180 else ""),
        priority=priority_out,
        predicted_sif=report.predicted_sif,
        human_label=report.human_label or "UNLABELED",
        validated_label=report.validated_label,
        label_source=report.label_source or "UNLABELED",
        validation_status=report.validation_status or "UNLABELED",
        data_type=getattr(report, "data_type", "synthetic") or "synthetic",
        ai_prediction=ai_prediction,
        analyst_decision=analyst_decision,
    )


@router.get("/reports", response_model=PaginatedReports)
def list_reports(
    site_id: str | None = None,
    department: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sif_label: bool | None = None,
    min_confidence: float | None = None,
    lsr_category: str | None = None,
    lifecycle_status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Report).options(
        joinedload(Report.classification),
        joinedload(Report.lsr_tags),
        joinedload(Report.site),
        joinedload(Report.triples),
    )
    q = _apply_site_scope(q, user)
    if site_id:
        q = q.filter(Report.site_id == site_id)
    if department:
        q = q.filter(Report.department == department)
    if date_from:
        q = q.filter(func.date(Report.reported_at) >= date_from)
    if date_to:
        q = q.filter(func.date(Report.reported_at) <= date_to)
    if sif_label is not None or min_confidence is not None:
        q = q.join(SifClassification)
        if sif_label is not None:
            q = q.filter(SifClassification.sif_label == sif_label)
        if min_confidence is not None:
            q = q.filter(SifClassification.sif_probability >= min_confidence)
    if lsr_category:
        q = q.join(LsrTag).filter(LsrTag.lsr_category == lsr_category)
    if lifecycle_status:
        if lifecycle_status == "PENDING_REVIEW":
            q = q.filter(Report.lifecycle_status.in_(["INGESTED", "AI_ANALYZED", "HSE_REVIEW", "REOPENED"]))
        elif lifecycle_status == "REVIEWED":
            q = q.filter(Report.lifecycle_status.in_(["CONFIRMED", "OVERRIDDEN"]))
        elif lifecycle_status == "OPEN_ACTIONS":
            q = q.filter(Report.lifecycle_status.in_(["ACTION_ASSIGNED", "IN_PROGRESS"]))
        elif lifecycle_status == "RESOLVED":
            q = q.filter(Report.lifecycle_status == "RESOLVED")
        else:
            q = q.filter(Report.lifecycle_status == lifecycle_status)

    q = q.order_by(Report.reported_at.desc())
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedReports(total=total, page=page, page_size=page_size, items=[_summary(r, db) for r in items])


@router.post("/reports", response_model=ReportSummary, status_code=status.HTTP_201_CREATED)
def create_report(
    body: ReportCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "analyst", "site_manager")),
):
    if not db.get(Site, body.site_id):
        raise HTTPException(status_code=400, detail="Unknown site_id")
    report = ingest_and_process(
        db,
        source_report_id=body.source_report_id,
        report_type=body.report_type,
        site_id=body.site_id,
        raw_text=body.raw_text,
        reported_at=body.reported_at,
        department=body.department,
        shift=body.shift,
        equipment_type=body.equipment_type,
        job_type=body.job_type,
        user_id=user.id,
    )
    log_ingestion_run(db, source="api", record_count=1)
    rebuild_clusters(db)
    db.commit()
    report = (
        db.query(Report)
        .options(joinedload(Report.classification), joinedload(Report.lsr_tags), joinedload(Report.site), joinedload(Report.triples))
        .filter(Report.id == report.id)
        .first()
    )
    return _summary(report, db)


def _build_report_detail(report: Report, db: Session) -> ReportDetail:
    base = _summary(report, db)
    clf = report.classification
    cluster_id = None
    triple = db.query(PrecursorTriple).filter(PrecursorTriple.report_id == report.id).first()
    if triple:
        member = db.query(ClusterMember).filter(ClusterMember.triple_id == triple.id).first()
        if member:
            cluster_id = member.cluster_id

    # Latest review
    review_out = None
    latest_review = (
        db.query(ReportReview)
        .filter(ReportReview.report_id == report.id)
        .order_by(ReportReview.created_at.desc())
        .first()
    )
    if latest_review:
        review_out = ReportReviewOut(
            id=latest_review.id,
            report_id=latest_review.report_id,
            user_id=latest_review.user_id,
            username=latest_review.user.username if latest_review.user else None,
            decision=latest_review.decision,
            final_sif_label=latest_review.final_sif_label,
            reason=latest_review.reason,
            notes=latest_review.notes,
            ai_sif_label=latest_review.ai_sif_label,
            ai_sif_probability=latest_review.ai_sif_probability,
            ai_model_version=latest_review.ai_model_version,
            final_priority=latest_review.final_priority,
            priority_reason=latest_review.priority_reason,
            created_at=latest_review.created_at,
            updated_at=latest_review.updated_at,
        )

    # Precursors list
    triples_out = []
    for t in report.triples:
        triples_out.append(
            {
                "id": t.id,
                "activity": t.activity,
                "location_asset": t.location_asset,
                "barrier_failure": t.barrier_failure,
                "extracted_at": t.extracted_at.isoformat(),
            }
        )

    return ReportDetail(
        **base.model_dump(),
        raw_text_redacted=report.raw_text_redacted,
        shift=report.shift,
        equipment_type=report.equipment_type,
        job_type=report.job_type,
        contributing_phrases=[PhraseWeight(**p) for p in (clf.contributing_phrases if clf else [])],
        model_version=clf.model_version if clf else None,
        classified_at=clf.classified_at if clf else None,
        cluster_id=cluster_id,
        resolution_notes=report.resolution_notes,
        resolved_at=report.resolved_at,
        features=clf.features if clf else {},
        feedback_history=[
            {
                "id": f.id,
                "user_id": f.user_id,
                "feedback_type": f.feedback_type,
                "comment": f.comment,
                "new_value": f.new_value,
                "created_at": f.created_at.isoformat(),
            }
            for f in report.feedback
        ],
        review=review_out,
        label_reviews=[
            LabelReviewOut(
                id=lr.id,
                report_id=lr.report_id,
                reviewer_id=lr.reviewer_id,
                reviewer_username=lr.reviewer.username if getattr(lr, "reviewer", None) else None,
                reviewer_role=lr.reviewer_role,
                label=lr.label,
                reason=lr.reason,
                notes=lr.notes,
                review_version=lr.review_version,
                created_at=lr.created_at,
            )
            for lr in (getattr(report, "label_reviews", None) or [])
        ],
        precursor_triples=triples_out,
    )


@router.get("/reports/reviewer-agreement", response_model=ReviewerAgreementSummaryOut)
def get_reviewer_agreement(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Calculates overall inter-rater reliability (Cohen's Kappa) across multi-reviewed incidents."""
    from app.services.label_service import get_reviewer_agreement_summary

    return get_reviewer_agreement_summary(db)


@router.get("/reports/{report_id}", response_model=ReportDetail)
def get_report(report_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report = (
        db.query(Report)
        .options(
            joinedload(Report.classification),
            joinedload(Report.lsr_tags),
            joinedload(Report.site),
            joinedload(Report.feedback),
            joinedload(Report.triples),
            joinedload(Report.reviews),
            joinedload(Report.label_reviews),
            joinedload(Report.analyst_decisions),
        )
        .filter(Report.id == report_id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    allowed = scoped_site_ids(user)
    if allowed is not None and report.site_id not in allowed:
        raise HTTPException(status_code=403, detail="Outside site scope")
    return _build_report_detail(report, db)


@router.post("/reports/{report_id}/label-review", response_model=ReportDetail)
def submit_label_review(
    report_id: str,
    body: LabelReviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "analyst", "site_manager", "leadership")),
):
    """Submits a human review for SIF potential, versioning history and applying consensus policies."""
    from app.services.label_service import record_label_review

    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    clf = report.classification

    try:
        record_label_review(
            db=db,
            report_id=report_id,
            reviewer_id=user.id,
            label=body.label,
            reason=body.reason,
            notes=body.notes,
            reviewer_role=user.role,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    # Create immutable AnalystDecision separating human decision from AI prediction
    label_bool = None
    if body.label == "SIF":
        label_bool = True
    elif body.label == "NON_SIF":
        label_bool = False
    db.add(
        AnalystDecision(
            report_id=report.id,
            analyst_id=user.id,
            analyst_label=label_bool,
            review_action="LABELED",
            analyst_comment=body.reason,
            ai_sif_label_at_time=clf.sif_label if clf else None,
            ai_sif_probability_at_time=clf.sif_probability if clf else None,
        )
    )
    db.commit()

    report = (
        db.query(Report)
        .options(
            joinedload(Report.classification),
            joinedload(Report.lsr_tags),
            joinedload(Report.site),
            joinedload(Report.feedback),
            joinedload(Report.triples),
            joinedload(Report.reviews),
            joinedload(Report.label_reviews),
            joinedload(Report.analyst_decisions),
        )
        .filter(Report.id == report_id)
        .first()
    )
    return _build_report_detail(report, db)


@router.get("/reports/{report_id}/label-history", response_model=ReportLabelHistoryOut)
def get_report_label_history_endpoint(
    report_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns the immutable versioned audit history of all human reviews and consensus status."""
    from app.services.label_service import get_report_label_history

    try:
        return get_report_label_history(db, report_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/reports/{report_id}/confirm", response_model=ReportDetail)
def confirm_report_sif(
    report_id: str,
    body: ReportConfirmIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "analyst", "site_manager")),
):
    """Analyst confirms the AI's SIF classification. AI prediction remains untouched."""
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    clf = report.classification
    if not clf:
        raise HTTPException(status_code=400, detail="Report has not been classified by AI yet")

    report.final_sif_label = clf.sif_label

    # Create immutable review decision
    review = ReportReview(
        report_id=report.id,
        user_id=user.id,
        decision="CONFIRMED",
        final_sif_label=clf.sif_label,
        reason="Analyst confirmed AI SIF assessment",
        notes=body.notes,
        ai_sif_label=clf.sif_label,
        ai_sif_probability=clf.sif_probability,
        ai_model_version=clf.model_version,
    )
    db.add(review)

    # Record feedback record for retraining compatibility
    db.add(
        AnalystFeedback(
            report_id=report.id,
            user_id=user.id,
            feedback_type="confirm_sif",
            previous_value={"sif_label": clf.sif_label, "sif_probability": clf.sif_probability},
            new_value={"sif_label": clf.sif_label, "confirmed": True},
            comment=body.notes,
        )
    )

    # Create immutable AnalystDecision separating human decision from AI prediction
    db.add(
        AnalystDecision(
            report_id=report.id,
            analyst_id=user.id,
            analyst_label=clf.sif_label,
            review_action="CONFIRMED",
            analyst_comment=body.notes,
            ai_sif_label_at_time=clf.sif_label,
            ai_sif_probability_at_time=clf.sif_probability,
        )
    )

    try:
        transition_report_lifecycle(db, report, "CONFIRMED", user.id, reason="Confirmed SIF assessment", notes=body.notes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    db.commit()
    db.refresh(report)
    return _build_report_detail(report, db)


@router.post("/reports/{report_id}/override", response_model=ReportDetail)
def override_report_sif(
    report_id: str,
    body: ReportOverrideIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "analyst", "site_manager")),
):
    """Analyst overrides the AI's SIF classification. Mandatory reason required. AI probability remains immutable."""
    if not (body.reason or "").strip():
        raise HTTPException(status_code=400, detail="Override reason is mandatory")

    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    clf = report.classification
    if not clf:
        raise HTTPException(status_code=400, detail="Report has not been classified by AI yet")

    report.final_sif_label = body.final_sif_label

    # Create immutable review decision
    review = ReportReview(
        report_id=report.id,
        user_id=user.id,
        decision="OVERRIDDEN",
        final_sif_label=body.final_sif_label,
        reason=body.reason.strip(),
        notes=body.notes,
        ai_sif_label=clf.sif_label,
        ai_sif_probability=clf.sif_probability,
        ai_model_version=clf.model_version,
    )
    db.add(review)

    # Record feedback record for retraining compatibility
    db.add(
        AnalystFeedback(
            report_id=report.id,
            user_id=user.id,
            feedback_type="override_sif",
            previous_value={"sif_label": clf.sif_label, "sif_probability": clf.sif_probability},
            new_value={"sif_label": body.final_sif_label, "override_reason": body.reason},
            comment=f"{body.reason}: {body.notes or ''}".strip(),
        )
    )

    # Create immutable AnalystDecision separating human decision from AI prediction
    db.add(
        AnalystDecision(
            report_id=report.id,
            analyst_id=user.id,
            analyst_label=body.final_sif_label,
            review_action="OVERRIDDEN",
            analyst_comment=body.reason,
            ai_sif_label_at_time=clf.sif_label,
            ai_sif_probability_at_time=clf.sif_probability,
        )
    )

    try:
        transition_report_lifecycle(
            db, report, "OVERRIDDEN", user.id, reason=body.reason, notes=body.notes
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    db.commit()
    db.refresh(report)
    return _build_report_detail(report, db)


@router.post("/reports/{report_id}/lsr-review", response_model=ReportDetail)
def review_report_lsr(
    report_id: str,
    body: LsrReviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "analyst", "site_manager")),
):
    """Analyst reviews/adjusts Life-Saving Rules tags while preserving original AI tags."""
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # Add/update analyst tags with source='analyst'
    # First remove prior analyst tags for idempotence
    db.query(LsrTag).filter(LsrTag.report_id == report.id, LsrTag.source == "analyst").delete()

    for r_id in body.selected_rule_ids:
        rule = get_rule_by_id(r_id) or get_rule_by_name(r_id)
        rid = rule.id if rule else None
        rname = rule.name if rule else r_id
        db.add(
            LsrTag(
                report_id=report.id,
                lsr_category=rname,
                rule_id=rid,
                rule_name=rname,
                confidence=1.0,
                source="analyst",
                evidence=[{"text": body.reason or "Analyst verified rule", "type": "analyst"}],
            )
        )

    db.add(
        AnalystFeedback(
            report_id=report.id,
            user_id=user.id,
            feedback_type="adjust_lsr",
            previous_value={"lsr_tags": [t.lsr_category for t in report.lsr_tags]},
            new_value={"selected_rules": body.selected_rule_ids},
            comment=body.reason,
        )
    )

    write_audit(
        db,
        action_type="lsr_review",
        entity_type="report",
        entity_id=report.id,
        user_id=user.id,
        after={"selected_rules": body.selected_rule_ids, "reason": body.reason},
    )

    db.commit()
    db.refresh(report)
    return _build_report_detail(report, db)


@router.post("/reports/{report_id}/precursor-review", response_model=ReportDetail)
def review_report_precursors(
    report_id: str,
    body: PrecursorReviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "analyst", "site_manager")),
):
    """Analyst corrects precursor activity or barrier failure without altering raw AI extractions."""
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    orig_triple = db.query(PrecursorTriple).filter(PrecursorTriple.report_id == report.id).first()

    db.add(
        PrecursorFeedback(
            report_id=report.id,
            user_id=user.id,
            original_activity=orig_triple.activity if orig_triple else "None",
            corrected_activity=body.activity,
            original_barrier_failure=orig_triple.barrier_failure if orig_triple else "None",
            corrected_barrier_failure=body.barrier_failure,
            original_location=orig_triple.location_asset if orig_triple else "",
            corrected_location=body.location_asset,
            comment=body.comment,
        )
    )

    write_audit(
        db,
        action_type="precursor_review",
        entity_type="report",
        entity_id=report.id,
        user_id=user.id,
        after={"activity": body.activity, "barrier_failure": body.barrier_failure, "comment": body.comment},
    )

    db.commit()
    db.refresh(report)
    return _build_report_detail(report, db)


@router.post("/reports/{report_id}/priority-review", response_model=ReportDetail)
def review_report_priority(
    report_id: str,
    body: PriorityAdjustmentIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "analyst", "site_manager")),
):
    """Analyst adjusts intervention priority tier with mandatory justification."""
    if not (body.reason or "").strip():
        raise HTTPException(status_code=400, detail="Reason is required to adjust priority tier")

    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    old_priority = report.final_priority
    report.final_priority = body.priority_tier.upper()

    latest_review = (
        db.query(ReportReview)
        .filter(ReportReview.report_id == report.id)
        .order_by(ReportReview.created_at.desc())
        .first()
    )
    if latest_review:
        latest_review.final_priority = report.final_priority
        latest_review.priority_reason = body.reason.strip()

    write_audit(
        db,
        action_type="priority_adjustment",
        entity_type="report",
        entity_id=report.id,
        user_id=user.id,
        before={"priority": old_priority},
        after={"priority": report.final_priority, "reason": body.reason},
    )

    db.commit()
    db.refresh(report)
    return _build_report_detail(report, db)


@router.post("/reports/{report_id}/resolve", response_model=ReportDetail)
def resolve_report_case(
    report_id: str,
    body: CaseResolutionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "analyst", "site_manager")),
):
    """Marks case as resolved with mandatory resolution evidence notes."""
    if not (body.resolution_notes or "").strip():
        raise HTTPException(status_code=400, detail="Resolution notes and evidence are mandatory")

    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    try:
        transition_report_lifecycle(
            db,
            report,
            "RESOLVED",
            user.id,
            reason="Case resolution",
            notes=body.resolution_notes.strip(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    db.commit()
    db.refresh(report)
    return _build_report_detail(report, db)


@router.post("/reports/{report_id}/reopen", response_model=ReportDetail)
def reopen_report_case(
    report_id: str,
    body: CaseReopenIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "analyst", "site_manager")),
):
    """Reopens a resolved or closed case when new safety evidence arrives."""
    if not (body.reason or "").strip():
        raise HTTPException(status_code=400, detail="Reason is required to reopen case")

    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    try:
        transition_report_lifecycle(
            db,
            report,
            "REOPENED",
            user.id,
            reason=body.reason.strip(),
            notes=f"Reopened by {user.username}: {body.reason}",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    db.commit()
    db.refresh(report)
    return _build_report_detail(report, db)


@router.get("/reports/{report_id}/timeline", response_model=list[TimelineEventOut])
def get_report_timeline(
    report_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns full chronological audit timeline of the safety report from ingestion to resolution."""
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    allowed = scoped_site_ids(user)
    if allowed is not None and report.site_id not in allowed:
        raise HTTPException(status_code=403, detail="Outside site scope")

    events: list[TimelineEventOut] = []

    # 1. Ingestion event
    events.append(
        TimelineEventOut(
            id=f"ingest-{report.id}",
            timestamp=report.ingested_at or report.reported_at,
            event_type="INGESTION",
            actor="System",
            title="Report Ingested",
            description=f"Received report {report.source_report_id} from {report.site.name if report.site else 'Site'}",
            badge_type="info",
        )
    )

    # 2. AI Analysis event
    clf = report.classification
    if clf:
        sif_text = "SIF-Potential Flagged" if clf.sif_label else "Classified as Non-SIF"
        prob_pct = int(clf.sif_probability * 100)
        events.append(
            TimelineEventOut(
                id=f"ai-{clf.id}",
                timestamp=clf.classified_at,
                event_type="AI_ANALYSIS",
                actor=f"AI Model ({clf.model_version})",
                title="AI Safety Analysis Completed",
                description=f"{sif_text} (Probability: {prob_pct}%)",
                badge_type="warning" if clf.sif_label else "success",
            )
        )

    # 3. Reviews
    for rev in report.reviews:
        events.append(
            TimelineEventOut(
                id=f"rev-{rev.id}",
                timestamp=rev.created_at,
                event_type="ANALYST_REVIEW",
                actor=rev.user.username if rev.user else "HSE Analyst",
                title=f"Analyst Decision: {rev.decision}",
                description=f"{rev.reason}. {rev.notes or ''}".strip(),
                badge_type="success" if rev.decision == "CONFIRMED" else "danger" if rev.decision == "OVERRIDDEN" else "warning",
            )
        )

    # 4. Corrective Action events
    for rec in report.recommendations:
        events.append(
            TimelineEventOut(
                id=f"rec-init-{rec.id}",
                timestamp=rec.created_at,
                event_type="RECOMMENDATION_GENERATED",
                actor="AI Recommender",
                title="Corrective Action Recommended",
                description=f"[{rec.category}] {rec.title}",
                badge_type="info",
            )
        )
        for fb in rec.feedback_records:
            events.append(
                TimelineEventOut(
                    id=f"rec-fb-{fb.id}",
                    timestamp=fb.created_at,
                    event_type="ACTION_STATE_CHANGE",
                    actor=fb.user.username if fb.user else "HSE Analyst",
                    title=f"Action {fb.decision}",
                    description=fb.reason or fb.edited_text or "Status updated",
                    badge_type="success" if fb.decision in ("ACCEPTED", "RESOLVED") else "warning",
                )
            )

    # 5. Audit Log transitions
    audit_rows = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "report", AuditLog.entity_id == report.id)
        .all()
    )
    for a in audit_rows:
        if a.action_type == "lifecycle_transition":
            after_val = a.after_value or {}
            target = after_val.get("lifecycle_status", "UNKNOWN")
            events.append(
                TimelineEventOut(
                    id=f"audit-{a.id}",
                    timestamp=a.created_at,
                    event_type="STATUS_CHANGE",
                    actor="HSE Analyst",
                    title=f"Lifecycle Transition: {target}",
                    description=after_val.get("notes") or after_val.get("reason") or f"Case moved to {target}",
                    badge_type="info",
                )
            )

    # Sort chronologically
    events.sort(key=lambda e: e.timestamp)
    return events


@router.get("/reports/{report_id}/classification", response_model=SifClassificationOut)
def get_classification(report_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    allowed = scoped_site_ids(user)
    if allowed is not None and report.site_id not in allowed:
        raise HTTPException(status_code=403, detail="Outside site scope")
    clf = report.classification
    if not clf:
        raise HTTPException(status_code=404, detail="Classification not found")
    return SifClassificationOut(
        report_id=report.id,
        sif_probability=clf.sif_probability,
        sif_label=clf.sif_label,
        model_version=clf.model_version,
        contributing_phrases=[PhraseWeight(**p) for p in clf.contributing_phrases or []],
        classified_at=clf.classified_at,
    )


@router.get("/reports/{report_id}/tags", response_model=list[LsrTagOut])
def get_tags(report_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    allowed = scoped_site_ids(user)
    if allowed is not None and report.site_id not in allowed:
        raise HTTPException(status_code=403, detail="Outside site scope")
    return [_to_lsr_tag_out(t) for t in report.lsr_tags]


@router.get("/lsr-rules", response_model=list[LsrRuleMetadataOut])
def get_canonical_rules(user: User = Depends(get_current_user)):
    """Returns the canonical 12 IOGP Life-Saving Rules metadata."""
    return get_canonical_rule_metadata()

