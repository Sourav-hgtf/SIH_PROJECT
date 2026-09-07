"""Human-in-the-Loop SIF Labelling Workflow, Consensus Policy, and Inter-Rater Agreement Service.

Enforces:
1. Label states: SIF, NON_SIF, UNCERTAIN, UNLABELED
2. Full immutable review history (versioned label reviews, never overwritten)
3. Multi-reviewer consensus validation (e.g., 2 agreeing independent reviewers = gold validated_label)
4. Senior HSE arbitration upon reviewer disagreement
5. Inter-rater reliability calculation using Cohen's Kappa
6. Strict audit logging and separation of heuristic AI predictions from human ground truth.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import logging
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.models import (
    AnalystFeedback,
    AuditLog,
    LabelReview,
    Report,
    User,
    utcnow,
)

logger = logging.getLogger(__name__)

LabelType = Literal["SIF", "NON_SIF", "UNCERTAIN"]
VALID_LABELS = {"SIF", "NON_SIF", "UNCERTAIN"}
AUTHORIZED_ROLES = {"admin", "analyst", "site_manager", "leadership"}


def calculate_cohens_kappa(
    rater1: list[str],
    rater2: list[str],
    categories: list[str] | None = None,
) -> dict[str, Any]:
    """Computes Cohen's Kappa coefficient (inter-rater agreement above chance).

    κ = (P_o - P_e) / (1 - P_e)
    """
    if len(rater1) != len(rater2) or len(rater1) == 0:
        return {
            "cohens_kappa": 1.0 if len(rater1) == 0 else 0.0,
            "observed_agreement": 1.0 if len(rater1) == 0 else 0.0,
            "expected_agreement": 0.0,
            "sample_size": len(rater1),
            "interpretation": "Insufficient pairs for Kappa calculation",
        }

    n = len(rater1)
    cats = categories or sorted(list(set(rater1 + rater2)))
    if not cats:
        cats = ["NON_SIF", "SIF"]

    # 1. Observed agreement P_o
    agreed = sum(1 for a, b in zip(rater1, rater2) if a == b)
    p_o = agreed / n

    # 2. Expected chance agreement P_e
    c1 = Counter(rater1)
    c2 = Counter(rater2)
    p_e = sum((c1[c] / n) * (c2[c] / n) for c in cats)

    # 3. Kappa
    if p_e >= 1.0 or (1.0 - p_e) == 0:
        kappa = 1.0 if p_o == 1.0 else 0.0
    else:
        kappa = (p_o - p_e) / (1.0 - p_e)
    kappa = round(max(-1.0, min(1.0, kappa)), 4)

    # 4. Interpretation scale (Landis & Koch, 1977)
    if kappa >= 0.81:
        interp = "Almost Perfect Agreement"
    elif kappa >= 0.61:
        interp = "Substantial Agreement"
    elif kappa >= 0.41:
        interp = "Moderate Agreement"
    elif kappa >= 0.21:
        interp = "Fair Agreement"
    elif kappa >= 0.0:
        interp = "Slight Agreement"
    else:
        interp = "Poor / Systematic Disagreement"

    return {
        "cohens_kappa": kappa,
        "observed_agreement": round(p_o, 4),
        "expected_agreement": round(p_e, 4),
        "sample_size": n,
        "interpretation": interp,
    }


def record_label_review(
    db: Session,
    report_id: str,
    reviewer_id: str,
    label: str,
    reason: str,
    notes: str | None = None,
    reviewer_role: str | None = None,
) -> tuple[Report, LabelReview]:
    """Records an immutable human review and evaluates the validation consensus policy."""
    lbl = label.strip().upper()
    if lbl not in VALID_LABELS:
        raise ValueError(f"Invalid label '{label}'. Allowed: {sorted(list(VALID_LABELS))}")

    if not reason or not reason.strip():
        raise ValueError("A documented reason is mandatory to submit a SIF label review.")

    report = db.get(Report, report_id)
    if not report:
        raise ValueError(f"Report with ID '{report_id}' not found.")

    user = db.get(User, reviewer_id)
    role = (reviewer_role or (user.role if user else "analyst")).lower()
    if role not in AUTHORIZED_ROLES:
        raise PermissionError(f"User role '{role}' is not authorized to submit SIF reviews.")

    # 1. Determine next review version for this report
    last_review = (
        db.query(LabelReview)
        .filter(LabelReview.report_id == report_id)
        .order_by(LabelReview.review_version.desc())
        .first()
    )
    next_version = (last_review.review_version + 1) if last_review else 1

    # 2. Create immutable LabelReview entity
    review = LabelReview(
        report_id=report.id,
        reviewer_id=reviewer_id,
        label=lbl,
        reason=reason.strip(),
        notes=notes.strip() if notes else None,
        review_version=next_version,
        reviewer_role=role,
        created_at=utcnow(),
    )
    db.add(review)
    db.flush()

    # 3. Evaluate Validation Consensus Policy
    # Fetch all historical reviews for this report, latest per unique reviewer
    all_reviews = (
        db.query(LabelReview)
        .filter(LabelReview.report_id == report_id)
        .order_by(LabelReview.created_at.desc())
        .all()
    )
    reviewer_latest: dict[str, LabelReview] = {}
    for r in all_reviews:
        if r.reviewer_id not in reviewer_latest:
            reviewer_latest[r.reviewer_id] = r

    unique_reviews = list(reviewer_latest.values())
    unique_labels = {r.label for r in unique_reviews}

    before_state = {
        "human_label": report.human_label,
        "validated_label": report.validated_label,
        "label_source": report.label_source,
        "validation_status": report.validation_status,
        "final_sif_label": report.final_sif_label,
    }

    report.human_label = lbl

    # Multi-Reviewer Consensus Logic
    is_senior = role in ("leadership", "admin")

    if len(unique_reviews) >= 2:
        if len(unique_labels) == 1:
            # All independent reviewers agree -> Gold consensus validated label
            consensus = unique_reviews[0].label
            report.validated_label = consensus
            report.validation_status = "VALIDATED"
            report.label_source = "CONSENSUS_VALIDATED"
            report.final_sif_label = True if consensus == "SIF" else (False if consensus == "NON_SIF" else None)
        else:
            # Reviewers disagree
            if is_senior:
                # Senior HSE review adjudicates the conflict
                report.validated_label = lbl
                report.validation_status = "VALIDATED"
                report.label_source = "SENIOR_HSE_OVERRIDE"
                report.final_sif_label = True if lbl == "SIF" else (False if lbl == "NON_SIF" else None)
            else:
                report.validated_label = None  # Disagreement cannot be gold label
                report.validation_status = "DISAGREEMENT"
                report.label_source = "DISAGREEMENT"
                report.final_sif_label = None
    else:
        # Single reviewer
        if is_senior:
            # Senior HSE review can be validated immediately
            report.validated_label = lbl
            report.validation_status = "VALIDATED"
            report.label_source = "SENIOR_HSE_OVERRIDE"
            report.final_sif_label = True if lbl == "SIF" else (False if lbl == "NON_SIF" else None)
        else:
            report.validated_label = None
            report.validation_status = "PENDING_CONSENSUS"
            report.label_source = "HUMAN_REVIEW"
            report.final_sif_label = True if lbl == "SIF" else (False if lbl == "NON_SIF" else None)

    # Lifecycle status update
    if report.validation_status == "VALIDATED":
        report.lifecycle_status = "CONFIRMED" if report.validated_label == "SIF" else "RESOLVED"
    elif report.validation_status == "DISAGREEMENT":
        report.lifecycle_status = "HSE_REVIEW"
    else:
        report.lifecycle_status = "HSE_REVIEW"

    # 4. Write immutable Audit Log entry
    after_state = {
        "human_label": report.human_label,
        "validated_label": report.validated_label,
        "label_source": report.label_source,
        "validation_status": report.validation_status,
        "final_sif_label": report.final_sif_label,
        "review_version": review.review_version,
        "reason": reason,
    }
    db.add(
        AuditLog(
            user_id=reviewer_id,
            action_type="label_review_submitted",
            entity_type="report",
            entity_id=report.id,
            before_value=before_state,
            after_value=after_state,
        )
    )

    # 5. Maintain AnalystFeedback for retraining compatibility
    db.add(
        AnalystFeedback(
            report_id=report.id,
            user_id=reviewer_id,
            feedback_type="label_review",
            previous_value=before_state,
            new_value={"label": lbl, "validated_label": report.validated_label},
            comment=f"{reason}: {notes or ''}".strip(),
        )
    )

    db.commit()
    db.refresh(report)
    db.refresh(review)
    return report, review


def get_report_label_history(db: Session, report_id: str) -> dict[str, Any]:
    """Fetches full review history and consensus metrics for a specific report."""
    report = db.get(Report, report_id)
    if not report:
        raise ValueError(f"Report '{report_id}' not found.")

    reviews = (
        db.query(LabelReview)
        .filter(LabelReview.report_id == report_id)
        .order_by(LabelReview.review_version.asc())
        .all()
    )

    history = []
    unique_reviewers = set()
    labels = []
    for r in reviews:
        unique_reviewers.add(r.reviewer_id)
        labels.append(r.label)
        history.append({
            "id": r.id,
            "reviewer_id": r.reviewer_id,
            "reviewer_username": r.reviewer.username if r.reviewer else "Unknown",
            "reviewer_role": r.reviewer_role,
            "label": r.label,
            "reason": r.reason,
            "notes": r.notes,
            "review_version": r.review_version,
            "created_at": r.created_at.isoformat(),
        })

    return {
        "report_id": report.id,
        "predicted_sif": report.predicted_sif,
        "human_label": report.human_label,
        "validated_label": report.validated_label,
        "label_source": report.label_source,
        "validation_status": report.validation_status,
        "total_reviews": len(reviews),
        "unique_reviewers_count": len(unique_reviewers),
        "distinct_labels": sorted(list(set(labels))),
        "is_consensus_validated": report.validation_status == "VALIDATED",
        "has_disagreement": report.validation_status == "DISAGREEMENT",
        "reviews": history,
    }


def get_reviewer_agreement_summary(db: Session) -> dict[str, Any]:
    """Calculates overall inter-rater reliability (Cohen's Kappa) across multi-reviewed incidents."""
    # Group label reviews by report_id
    all_reviews = db.query(LabelReview).order_by(LabelReview.report_id, LabelReview.created_at.asc()).all()
    reviews_by_report: dict[str, list[LabelReview]] = {}
    for r in all_reviews:
        reviews_by_report.setdefault(r.report_id, []).append(r)

    multi_reviewed = {rid: revs for rid, revs in reviews_by_report.items() if len({x.reviewer_id for x in revs}) >= 2}

    rater1_pairs = []
    rater2_pairs = []
    agreed_count = 0
    disagreed_count = 0

    for rid, revs in multi_reviewed.items():
        # Get latest review for first two distinct reviewers
        rev_by_user = {}
        for r in revs:
            rev_by_user[r.reviewer_id] = r
        first_two = list(rev_by_user.values())[:2]
        if len(first_two) == 2:
            l1, l2 = first_two[0].label, first_two[1].label
            rater1_pairs.append(l1)
            rater2_pairs.append(l2)
            if l1 == l2:
                agreed_count += 1
            else:
                disagreed_count += 1

    kappa_result = calculate_cohens_kappa(rater1_pairs, rater2_pairs, categories=["NON_SIF", "SIF", "UNCERTAIN"])

    return {
        "multi_reviewed_reports": len(multi_reviewed),
        "total_comparison_pairs": len(rater1_pairs),
        "consensus_agreements": agreed_count,
        "disagreements": disagreed_count,
        **kappa_result,
    }
