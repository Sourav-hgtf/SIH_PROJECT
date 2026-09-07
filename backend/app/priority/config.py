"""Pydantic-validated loader for the priority section of configs/business_rules.yaml.

This module is the ONLY place that reads the business_rules.yaml priority
block. All other modules import the typed config via load_priority_config().
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator
import yaml

logger = logging.getLogger(__name__)

# ── Path resolution ────────────────────────────────────────────────────────────
# Search order:
#   1. <workspace_root>/configs/business_rules.yaml
#   2. <backend_root>/configs/business_rules.yaml


def _find_config_path() -> Path:
    current = Path(__file__).resolve()
    candidates = [
        current.parents[3] / "configs" / "business_rules.yaml",  # workspace root
        current.parents[2] / "configs" / "business_rules.yaml",  # backend root
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    raise FileNotFoundError(
        f"business_rules.yaml not found in candidates: {candidates}"
    )


# ── Pydantic models ─────────────────────────────────────────────────────────────


class PriorityWeights(BaseModel):
    sif_probability: float = Field(..., ge=0.0, le=1.0)
    barrier_criticality: float = Field(..., ge=0.0, le=1.0)
    recurrence: float = Field(..., ge=0.0, le=1.0)
    trend: float = Field(..., ge=0.0, le=1.0)
    exposure: float = Field(..., ge=0.0, le=1.0)
    cross_site: float = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_sum(self) -> "PriorityWeights":
        total = (
            self.sif_probability
            + self.barrier_criticality
            + self.recurrence
            + self.trend
            + self.exposure
            + self.cross_site
        )
        if not (0.99 <= total <= 1.01):
            raise ValueError(
                f"Priority weights must sum to 1.0; got {total:.4f}. "
                f"Check configs/business_rules.yaml."
            )
        return self


class PriorityTiers(BaseModel):
    critical: float = Field(..., ge=0.0, le=100.0)
    high: float = Field(..., ge=0.0, le=100.0)
    medium: float = Field(..., ge=0.0, le=100.0)

    @model_validator(mode="after")
    def validate_order(self) -> "PriorityTiers":
        if not (self.critical > self.high > self.medium >= 0):
            raise ValueError(
                "Tier thresholds must satisfy: critical > high > medium >= 0"
            )
        return self


class TrendScores(BaseModel):
    growing: float = Field(..., ge=0.0, le=1.0)
    new: float = Field(..., ge=0.0, le=1.0)
    stable: float = Field(..., ge=0.0, le=1.0)
    shrinking: float = Field(..., ge=0.0, le=1.0)
    insufficient_data: float = Field(..., ge=0.0, le=1.0)


class CrossSiteConfig(BaseModel):
    enabled: bool = True
    max_sites: int = Field(..., ge=1)


class NormalizationConfig(BaseModel):
    recurrence_cap: int = Field(..., ge=1)
    exposure_cap: int = Field(..., ge=1)


class PriorityConfig(BaseModel):
    version: str
    weights: PriorityWeights
    tiers: PriorityTiers
    trend_scores: TrendScores
    cross_site: CrossSiteConfig
    normalization: NormalizationConfig
    barrier_criticality: dict[str, float]

    @field_validator("barrier_criticality")
    @classmethod
    def validate_barrier_criticality(cls, v: dict[str, float]) -> dict[str, float]:
        if not v:
            raise ValueError("barrier_criticality map must not be empty")
        for key, score in v.items():
            if not (0.0 <= score <= 1.0):
                raise ValueError(
                    f"Barrier criticality score for '{key}' must be in [0,1]; got {score}"
                )
        # Normalise keys to lowercase for case-insensitive matching
        return {k.lower(): float(s) for k, s in v.items()}


class _BusinessRulesFile(BaseModel):
    priority: PriorityConfig


# ── Public API ──────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def load_priority_config() -> PriorityConfig:
    """Load and validate the priority section of business_rules.yaml.

    Fails fast with ValueError / FileNotFoundError on invalid config.
    Result is cached for the lifetime of the process (appropriate for
    immutable config; restart to pick up config changes).
    """
    path = _find_config_path()
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict) or "priority" not in data:
        raise ValueError(
            f"business_rules.yaml at {path} must contain a 'priority' block"
        )
    config_file = _BusinessRulesFile(**data)
    logger.info(
        "Loaded priority config %s from %s", config_file.priority.version, path
    )
    return config_file.priority
