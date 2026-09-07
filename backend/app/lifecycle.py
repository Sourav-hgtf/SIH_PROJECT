"""Centralized State Machine & Governance Rules for HSE Report Lifecycle."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.orm import Session

from app.models import AuditLog, Report, utcnow

logger = logging.getLogger(__name__)

LifecycleStatus = Literal[
    "INGESTED",
    "AI_ANALYZED",
    "HSE_REVIEW",
    "CONFIRMED",
    "OVERRIDDEN",
    "ACTION_ASSIGNED",
    "IN_PROGRESS",
    "RESOLVED",
    "REOPENED",
    "REJECTED",
]

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "INGESTED": {"AI_ANALYZED"},
    "AI_ANALYZED": {"HSE_REVIEW", "CONFIRMED", "OVERRIDDEN", "REJECTED"},
    "HSE_REVIEW": {"CONFIRMED", "OVERRIDDEN", "REJECTED"},
    "CONFIRMED": {"ACTION_ASSIGNED", "IN_PROGRESS", "RESOLVED", "HSE_REVIEW", "REOPENED"},
    "OVERRIDDEN": {"ACTION_ASSIGNED", "RESOLVED", "HSE_REVIEW", "REOPENED"},
    "ACTION_ASSIGNED": {"IN_PROGRESS", "RESOLVED", "REOPENED", "HSE_REVIEW"},
    "IN_PROGRESS": {"RESOLVED", "REOPENED", "ACTION_ASSIGNED"},
    "RESOLVED": {"REOPENED"},
    "REOPENED": {"HSE_REVIEW", "CONFIRMED", "OVERRIDDEN", "ACTION_ASSIGNED", "RESOLVED"},
    "REJECTED": {"REOPENED", "HSE_REVIEW"},
}


def is_valid_transition(current_status: str, target_status: str) -> bool:
    """Check if transitioning from current_status to target_status is allowed."""
    if current_status == target_status:
        return True
    allowed = ALLOWED_TRANSITIONS.get(current_status, set())
    return target_status in allowed


def transition_report_lifecycle(
    db: Session,
    report: Report,
    target_status: str,
    user_id: str | None = None,
    reason: str | None = None,
    notes: str | None = None,
) -> Report:
    """Executes a lifecycle transition on a Report with validation and immutable audit logging."""
    current = report.lifecycle_status or "AI_ANALYZED"
    if not is_valid_transition(current, target_status):
        raise ValueError(
            f"Invalid lifecycle transition from '{current}' to '{target_status}'. "
            f"Allowed next states: {sorted(list(ALLOWED_TRANSITIONS.get(current, set())))}"
        )

    before_state = {
        "lifecycle_status": current,
        "final_sif_label": report.final_sif_label,
        "final_priority": report.final_priority,
    }

    report.lifecycle_status = target_status

    if target_status == "RESOLVED":
        report.resolved_at = utcnow()
        if notes or reason:
            report.resolution_notes = notes or reason
    elif target_status == "REOPENED":
        report.resolved_at = None

    after_state = {
        "lifecycle_status": target_status,
        "final_sif_label": report.final_sif_label,
        "final_priority": report.final_priority,
        "reason": reason,
        "notes": notes,
    }

    db.add(
        AuditLog(
            user_id=user_id,
            action_type="lifecycle_transition",
            entity_type="report",
            entity_id=report.id,
            before_value=before_state,
            after_value=after_state,
        )
    )

    logger.info(f"Report {report.id} transitioned {current} -> {target_status} by user {user_id}")
    return report
