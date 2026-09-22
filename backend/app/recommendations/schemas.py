"""Pydantic schemas for AI-assisted corrective action recommendations."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

RecommendationStatus = Literal[
    "PENDING_REVIEW",
    "ACCEPTED",
    "EDITED",
    "REJECTED",
    "IMPLEMENTED",
    "RESOLVED",
]


class RecommendationFeedbackOut(BaseModel):
    id: str
    recommendation_id: str
    user_id: str | None = None
    decision: str
    original_text: str
    edited_text: str | None = None
    reason: str | None = None
    created_at: datetime


class RecommendationOut(BaseModel):
    id: str
    report_id: str | None = None
    cluster_id: str | None = None
    site_id: str | None = None
    activity: str | None = None
    category: str
    title: str
    action: str
    confidence: float
    priority: str
    evidence: list[str] = Field(default_factory=list)
    source_signals: dict[str, Any] = Field(default_factory=dict)
    rationale: str
    status: RecommendationStatus = "PENDING_REVIEW"
    version: str = "recommendations-v1"
    assigned_owner: str | None = None
    due_date: datetime | None = None
    resolution_notes: str | None = None
    created_at: datetime
    updated_at: datetime
    feedback_history: list[RecommendationFeedbackOut] = Field(default_factory=list)


class RecommendationEditIn(BaseModel):
    edited_title: str | None = None
    edited_action: str
    reason: str | None = None


class RecommendationRejectIn(BaseModel):
    reason: str


class RecommendationActionIn(BaseModel):
    assigned_owner: str | None = None
    due_date: datetime | None = None
    resolution_notes: str | None = None


class ExecutiveFocusAreaOut(BaseModel):
    area_name: str
    priority_tier: str
    cluster_id: str | None = None
    site_count: int
    trend_status: str
    report_count: int
    sif_rate: float
    recommended_actions: list[str] = Field(default_factory=list)
    primary_barrier_failure: str
