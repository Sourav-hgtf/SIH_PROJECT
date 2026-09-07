from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_user, require_roles, scoped_site_ids
from app.database import get_db
from app.models import PrecursorCluster, Recommendation, RecommendationFeedback, Report, User
from app.recommendations import (
    ExecutiveFocusAreaOut,
    RecommendationActionIn,
    RecommendationEditIn,
    RecommendationFeedbackOut,
    RecommendationOut,
    RecommendationRejectIn,
    generate_cluster_recommendations,
    generate_executive_focus_areas,
    generate_report_recommendations,
)
from app.services import write_audit

router = APIRouter(tags=["Recommendations"])


def _to_recommendation_out(r: Recommendation) -> RecommendationOut:
    history = [
        RecommendationFeedbackOut(
            id=fb.id,
            recommendation_id=fb.recommendation_id,
            user_id=fb.user_id,
            decision=fb.decision,
            original_text=fb.original_text,
            edited_text=fb.edited_text,
            reason=fb.reason,
            created_at=fb.created_at,
        )
        for fb in r.feedback_records
    ]
    return RecommendationOut(
        id=r.id,
        report_id=r.report_id,
        cluster_id=r.cluster_id,
        site_id=r.site_id,
        activity=r.activity,
        category=r.category,
        title=r.title,
        action=r.action,
        confidence=r.confidence,
        priority=r.priority,
        evidence=r.evidence or [],
        source_signals=r.source_signals or {},
        rationale=r.rationale or "",
        status=r.status,  # type: ignore[arg-type]
        version=r.version,
        assigned_owner=r.assigned_owner,
        due_date=r.due_date,
        resolution_notes=r.resolution_notes,
        created_at=r.created_at,
        updated_at=r.updated_at,
        feedback_history=history,
    )


@router.get("/reports/{report_id}/recommendations", response_model=list[RecommendationOut])
def get_report_recommendations_endpoint(
    report_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns AI-generated and analyst-reviewed corrective action recommendations for a report."""
    report = (
        db.query(Report)
        .options(
            joinedload(Report.classification),
            joinedload(Report.lsr_tags),
            joinedload(Report.triples),
            joinedload(Report.recommendations).joinedload(Recommendation.feedback_records),
        )
        .filter(Report.id == report_id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    allowed = scoped_site_ids(user)
    if allowed is not None and report.site_id not in allowed:
        raise HTTPException(status_code=403, detail="Outside site scope")

    existing = (
        db.query(Recommendation)
        .options(joinedload(Recommendation.feedback_records))
        .filter(Recommendation.report_id == report_id)
        .order_by(Recommendation.confidence.desc())
        .all()
    )

    if existing:
        return [_to_recommendation_out(r) for r in existing]

    # Deterministically generate recommendations
    generated = generate_report_recommendations(report, db)
    saved_records: list[Recommendation] = []
    for gen in generated:
        rec = Recommendation(
            id=gen.id,
            report_id=report.id,
            site_id=report.site_id,
            activity=report.job_type,
            category=gen.category,
            title=gen.title,
            action=gen.action,
            confidence=gen.confidence,
            priority=gen.priority,
            evidence=gen.evidence,
            source_signals=gen.source_signals,
            rationale=gen.rationale,
            status="PENDING_REVIEW",
            version=gen.version,
        )
        db.add(rec)
        saved_records.append(rec)

    if saved_records:
        db.commit()
        for r in saved_records:
            db.refresh(r)

    return [_to_recommendation_out(r) for r in saved_records]


@router.post("/recommendations/{recommendation_id}/accept", response_model=RecommendationOut)
def accept_recommendation(
    recommendation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("analyst", "site_manager", "admin")),
):
    """HSE Analyst accepts the AI-recommended corrective action."""
    rec = (
        db.query(Recommendation)
        .options(joinedload(Recommendation.feedback_records))
        .filter(Recommendation.id == recommendation_id)
        .first()
    )
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    before = {"status": rec.status, "action": rec.action}
    rec.status = "ACCEPTED"

    feedback = RecommendationFeedback(
        recommendation_id=rec.id,
        user_id=user.id,
        decision="accept",
        original_text=rec.action,
        edited_text=None,
        reason=None,
    )
    db.add(feedback)
    write_audit(
        db,
        action_type="accept_recommendation",
        entity_type="recommendation",
        entity_id=rec.id,
        user_id=user.id,
        before=before,
        after={"status": "ACCEPTED"},
    )
    db.commit()
    db.refresh(rec)
    return _to_recommendation_out(rec)


@router.post("/recommendations/{recommendation_id}/edit", response_model=RecommendationOut)
def edit_recommendation(
    recommendation_id: str,
    body: RecommendationEditIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("analyst", "site_manager", "admin")),
):
    """HSE Analyst modifies the recommendation, preserving original text in audit history."""
    if not body.edited_action.strip():
        raise HTTPException(status_code=400, detail="Edited action cannot be empty")

    rec = (
        db.query(Recommendation)
        .options(joinedload(Recommendation.feedback_records))
        .filter(Recommendation.id == recommendation_id)
        .first()
    )
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    before = {"status": rec.status, "title": rec.title, "action": rec.action}
    original_action = rec.action

    if body.edited_title and body.edited_title.strip():
        rec.title = body.edited_title.strip()
    rec.action = body.edited_action.strip()
    rec.status = "EDITED"

    feedback = RecommendationFeedback(
        recommendation_id=rec.id,
        user_id=user.id,
        decision="edit",
        original_text=original_action,
        edited_text=rec.action,
        reason=body.reason,
    )
    db.add(feedback)
    write_audit(
        db,
        action_type="edit_recommendation",
        entity_type="recommendation",
        entity_id=rec.id,
        user_id=user.id,
        before=before,
        after={"status": "EDITED", "action": rec.action},
    )
    db.commit()
    db.refresh(rec)
    return _to_recommendation_out(rec)


@router.post("/recommendations/{recommendation_id}/reject", response_model=RecommendationOut)
def reject_recommendation(
    recommendation_id: str,
    body: RecommendationRejectIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("analyst", "site_manager", "admin")),
):
    """HSE Analyst rejects the recommendation with mandatory reason."""
    if not body.reason.strip():
        raise HTTPException(status_code=400, detail="Reason is required to reject a recommendation")

    rec = (
        db.query(Recommendation)
        .options(joinedload(Recommendation.feedback_records))
        .filter(Recommendation.id == recommendation_id)
        .first()
    )
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    before = {"status": rec.status}
    rec.status = "REJECTED"

    feedback = RecommendationFeedback(
        recommendation_id=rec.id,
        user_id=user.id,
        decision="reject",
        original_text=rec.action,
        edited_text=None,
        reason=body.reason.strip(),
    )
    db.add(feedback)
    write_audit(
        db,
        action_type="reject_recommendation",
        entity_type="recommendation",
        entity_id=rec.id,
        user_id=user.id,
        before=before,
        after={"status": "REJECTED", "reason": body.reason},
    )
    db.commit()
    db.refresh(rec)
    return _to_recommendation_out(rec)


@router.post("/recommendations/{recommendation_id}/implement", response_model=RecommendationOut)
def implement_recommendation(
    recommendation_id: str,
    body: RecommendationActionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("analyst", "site_manager", "admin")),
):
    """Transitions an accepted recommendation to IMPLEMENTED with owner and tracking details."""
    rec = (
        db.query(Recommendation)
        .options(joinedload(Recommendation.feedback_records))
        .filter(Recommendation.id == recommendation_id)
        .first()
    )
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    rec.status = "IMPLEMENTED"
    if body.assigned_owner:
        rec.assigned_owner = body.assigned_owner
    if body.due_date:
        rec.due_date = body.due_date
    if body.resolution_notes:
        rec.resolution_notes = body.resolution_notes

    feedback = RecommendationFeedback(
        recommendation_id=rec.id,
        user_id=user.id,
        decision="implement",
        original_text=rec.action,
        reason=body.resolution_notes,
    )
    db.add(feedback)
    write_audit(
        db,
        action_type="implement_recommendation",
        entity_type="recommendation",
        entity_id=rec.id,
        user_id=user.id,
        after={"status": "IMPLEMENTED", "owner": body.assigned_owner},
    )
    db.commit()
    db.refresh(rec)
    return _to_recommendation_out(rec)


@router.post("/recommendations/{recommendation_id}/resolve", response_model=RecommendationOut)
def resolve_recommendation(
    recommendation_id: str,
    body: RecommendationActionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("analyst", "site_manager", "admin")),
):
    """Transitions a recommendation to RESOLVED upon completion of verification."""
    rec = (
        db.query(Recommendation)
        .options(joinedload(Recommendation.feedback_records))
        .filter(Recommendation.id == recommendation_id)
        .first()
    )
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    rec.status = "RESOLVED"
    if body.resolution_notes:
        rec.resolution_notes = body.resolution_notes

    feedback = RecommendationFeedback(
        recommendation_id=rec.id,
        user_id=user.id,
        decision="resolve",
        original_text=rec.action,
        reason=body.resolution_notes,
    )
    db.add(feedback)
    write_audit(
        db,
        action_type="resolve_recommendation",
        entity_type="recommendation",
        entity_id=rec.id,
        user_id=user.id,
        after={"status": "RESOLVED", "resolution_notes": body.resolution_notes},
    )
    db.commit()
    db.refresh(rec)
    return _to_recommendation_out(rec)


@router.get("/clusters/{cluster_id}/recommendations", response_model=list[RecommendationOut])
def get_cluster_recommendations_endpoint(
    cluster_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns cluster-level recommended interventions for recurring systemic patterns."""
    cluster = db.get(PrecursorCluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    existing = (
        db.query(Recommendation)
        .options(joinedload(Recommendation.feedback_records))
        .filter(Recommendation.cluster_id == cluster_id)
        .all()
    )
    if existing:
        return [_to_recommendation_out(r) for r in existing]

    generated = generate_cluster_recommendations(cluster, db)
    saved: list[Recommendation] = []
    for gen in generated:
        rec = Recommendation(
            id=gen.id,
            cluster_id=cluster.id,
            activity=cluster.representative_activity,
            category=gen.category,
            title=gen.title,
            action=gen.action,
            confidence=gen.confidence,
            priority=gen.priority,
            evidence=gen.evidence,
            source_signals=gen.source_signals,
            rationale=gen.rationale,
            status="PENDING_REVIEW",
            version=gen.version,
        )
        db.add(rec)
        saved.append(rec)

    if saved:
        db.commit()
        for r in saved:
            db.refresh(r)

    return [_to_recommendation_out(r) for r in saved]


@router.get("/dashboard/recommended-focus-areas", response_model=list[ExecutiveFocusAreaOut])
def get_recommended_focus_areas(
    limit: int = Query(5, ge=1, le=10),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns executive-level strategic focus areas with multi-site impact and recommended actions."""
    return generate_executive_focus_areas(db, limit=limit)
