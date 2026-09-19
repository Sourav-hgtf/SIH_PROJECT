"""Schemas for Intervention Priority Scoring.

These Pydantic models define the data structures for priority scores,
component breakdowns, tiering, and explanatory feedback.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

PriorityTier = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
SifClassificationState = Literal[
    "SIF_LIKELY", "UNCERTAIN", "NON_SIF", "LANGUAGE_UNSUPPORTED_NEEDS_REVIEW"
]


class PriorityComponent(BaseModel):
    """Detailed score and weight breakdown for a single priority factor."""
    name: str
    raw_value: Any
    score: float = Field(..., ge=0.0, le=1.0, description="Normalized score 0.0 to 1.0")
    weight: float = Field(..., ge=0.0, le=1.0, description="Weight configured in business_rules.yaml")
    weighted_score: float = Field(..., description="score * weight * 100")
    description: str = Field(..., description="Human-readable explanation of this factor's contribution")


class PriorityBreakdown(BaseModel):
    """Container for all 6 factor breakdowns."""
    sif_probability: PriorityComponent
    barrier_criticality: PriorityComponent
    recurrence: PriorityComponent
    trend: PriorityComponent
    exposure: PriorityComponent
    cross_site: PriorityComponent


class PriorityOut(BaseModel):
    """Public API output for an Intervention Priority Score."""
    score: float = Field(..., ge=0.0, le=100.0, description="Deterministic 0-100 Intervention Priority Score")
    tier: PriorityTier = Field(..., description="CRITICAL (>=70), HIGH (>=50), MEDIUM (>=30), LOW (<30)")
    version: str = Field(..., description="Business rules configuration version (e.g. priority-v1)")
    explanation_summary: str = Field(..., description="Natural language summary of why this score was assigned")
    action_recommendation: str = Field(..., description="HSE decision-support recommendation")
    classification_state: SifClassificationState = Field(..., description="Three-way SIF routing state")
    requires_analyst_review: bool = Field(..., description="True when an analyst decision is mandatory")
    evidence_sufficient: bool = Field(..., description="Whether enough report evidence supports unrestricted priority routing")
    evidence_signal_count: int = Field(..., ge=0, description="Independent asserted hazard/precursor signals")
    components: PriorityBreakdown


class PrioritySummaryRow(BaseModel):
    """Aggregated tier count for dashboard metrics."""
    tier: PriorityTier
    count: int
    percentage: float
