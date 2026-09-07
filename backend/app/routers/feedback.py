from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_roles
from app.database import get_db
from app.models import AnalystFeedback, LsrTag, Report, SifClassification, User
from app.schemas import FeedbackCreate, FeedbackRecord
from app.services import write_audit

router = APIRouter(tags=["Feedback"])


@router.post("/feedback", response_model=FeedbackRecord, status_code=status.HTTP_201_CREATED)
def submit_feedback(
    body: FeedbackCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("analyst", "site_manager")),
):
    report = db.get(Report, body.report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if body.feedback_type in ("override_sif", "adjust_lsr") and not (body.comment or "").strip():
        raise HTTPException(status_code=400, detail="Comment is required for overrides")

    clf = report.classification
    previous = {
        "sif_label": clf.sif_label if clf else None,
        "sif_probability": clf.sif_probability if clf else None,
        "lsr_tags": [t.lsr_category for t in report.lsr_tags],
    }
    new_value = body.new_value or {}

    if body.feedback_type in ("confirm_sif", "override_sif") and clf:
        if body.feedback_type == "override_sif":
            desired = new_value.get("sif_label")
            if desired is None:
                desired = not clf.sif_label
            clf.sif_label = bool(desired)
            clf.sif_probability = 1.0 if clf.sif_label else 0.05
            clf.model_version = f"{clf.model_version}+analyst"

    if body.feedback_type == "adjust_lsr" and "lsr_categories" in new_value:
        from app.nlp.lsr import get_rule_by_id, get_rule_by_name

        db.query(LsrTag).filter(LsrTag.report_id == report.id).delete()
        for cat in new_value["lsr_categories"]:
            rule = get_rule_by_name(str(cat)) or get_rule_by_id(str(cat))
            rid = rule.id if rule else None
            rname = rule.name if rule else str(cat)
            db.add(
                LsrTag(
                    report_id=report.id,
                    lsr_category=rname,
                    rule_id=rid,
                    rule_name=rname,
                    confidence=1.0,
                    source="analyst",
                    evidence=[{"text": "Analyst confirmed/adjusted rule", "type": "analyst"}],
                )
            )

    record = AnalystFeedback(
        report_id=report.id,
        user_id=user.id,
        feedback_type=body.feedback_type,
        previous_value=previous,
        new_value=new_value or {"confirmed": True},
        comment=body.comment,
    )
    db.add(record)
    write_audit(
        db,
        action_type=body.feedback_type,
        entity_type="report",
        entity_id=report.id,
        user_id=user.id,
        before=previous,
        after=new_value,
    )
    db.commit()
    db.refresh(record)
    return FeedbackRecord(
        id=record.id,
        report_id=record.report_id,
        user_id=record.user_id,
        feedback_type=record.feedback_type,  # type: ignore[arg-type]
        new_value=record.new_value,
        comment=record.comment,
        created_at=record.created_at,
    )
