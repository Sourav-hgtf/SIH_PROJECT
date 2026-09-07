"""Pydantic-validated loader for the recommendations section of configs/business_rules.yaml.

This module provides typed access to all centralized corrective action recommendation rules.
"""
from __future__ import annotations

from functools import lru_cache
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
import yaml

logger = logging.getLogger(__name__)


def _find_config_path() -> Path:
    current = Path(__file__).resolve()
    candidates = [
        current.parents[3] / "configs" / "business_rules.yaml",  # workspace root
        current.parents[2] / "configs" / "business_rules.yaml",  # backend root
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    raise FileNotFoundError(f"business_rules.yaml not found in candidates: {candidates}")


class ActionRuleConfig(BaseModel):
    category: str
    title: str
    action: str
    rationale: str
    base_confidence: float = Field(0.85, ge=0.0, le=1.0)


class RecommendationsRankingWeights(BaseModel):
    confidence_weight: float = Field(0.40, ge=0.0, le=1.0)
    barrier_criticality_weight: float = Field(0.30, ge=0.0, le=1.0)
    priority_boost_weight: float = Field(0.20, ge=0.0, le=1.0)
    cross_signal_weight: float = Field(0.10, ge=0.0, le=1.0)


class EvidenceMappingsConfig(BaseModel):
    barriers: dict[str, ActionRuleConfig] = Field(default_factory=dict)
    energy: dict[str, ActionRuleConfig] = Field(default_factory=dict)
    proximity: dict[str, ActionRuleConfig] = Field(default_factory=dict)
    lsr: dict[str, ActionRuleConfig] = Field(default_factory=dict)


class RecommendationsConfig(BaseModel):
    version: str = "recommendations-v1"
    max_recommendations_per_report: int = Field(3, ge=1, le=10)
    categories: list[str] = Field(default_factory=list)
    ranking_weights: RecommendationsRankingWeights = Field(default_factory=RecommendationsRankingWeights)
    evidence_mappings: EvidenceMappingsConfig = Field(default_factory=EvidenceMappingsConfig)
    cluster_rules: dict[str, ActionRuleConfig] = Field(default_factory=dict)


@lru_cache(maxsize=1)
def load_recommendations_config() -> RecommendationsConfig:
    """Loads and validates the recommendations section from business_rules.yaml."""
    config_path = _find_config_path()
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not raw or "recommendations" not in raw:
        raise KeyError(f"'recommendations' section missing from {config_path}")

    return RecommendationsConfig.model_validate(raw["recommendations"])
