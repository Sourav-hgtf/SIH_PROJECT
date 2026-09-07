"""Canonical Life-Saving Rules (LSR) Configuration Loader and Validator.

Standardizes on the 12 IOGP Life-Saving Rules used as the safety taxonomy
for the HSSE/SIF Sentinel prototype.
"""

from __future__ import annotations

from functools import lru_cache
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator
import yaml

logger = logging.getLogger(__name__)

# Expected canonical rule IDs in order
CANONICAL_LSR_COUNT = 12


class LsrRuleConfig(BaseModel):
    id: str = Field(..., description="Unique rule ID, e.g. LSR01 to LSR12")
    name: str = Field(..., description="Full canonical rule name")
    short_name: str = Field(..., description="Short canonical display name")
    description: str = Field(..., description="Safety intent and requirement")
    keywords: list[str] = Field(default_factory=list, description="Single token triggers")
    phrases: list[str] = Field(default_factory=list, description="Multi-token indicator phrases")
    related_energy_types: list[str] = Field(default_factory=list, description="Correlated energy hazard types")
    related_exposure_types: list[str] = Field(default_factory=list, description="Correlated exposure/proximity types")
    related_barrier_types: list[str] = Field(default_factory=list, description="Correlated safety barrier types")

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        v = v.strip().upper()
        if not v.startswith("LSR"):
            raise ValueError(f"Rule ID must start with 'LSR', got: {v}")
        return v

    @field_validator("name", "short_name", "description")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Field cannot be empty or whitespace only")
        return v

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, v: list[str]) -> list[str]:
        cleaned = [k.strip().lower() for k in v if k and k.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError(f"Duplicate keywords found in rule keywords list: {v}")
        return cleaned

    @field_validator("phrases")
    @classmethod
    def validate_phrases(cls, v: list[str]) -> list[str]:
        cleaned = [p.strip().lower() for p in v if p and p.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError(f"Duplicate phrases found in rule phrases list: {v}")
        return cleaned


class LsrConfigFile(BaseModel):
    rules: list[LsrRuleConfig]

    @model_validator(mode="after")
    def validate_canonical_rules(self) -> LsrConfigFile:
        if len(self.rules) != CANONICAL_LSR_COUNT:
            raise ValueError(
                f"Canonical LSR configuration must contain exactly {CANONICAL_LSR_COUNT} rules, found {len(self.rules)}"
            )

        ids = [r.id for r in self.rules]
        if len(set(ids)) != CANONICAL_LSR_COUNT:
            raise ValueError(f"Duplicate rule IDs detected: {ids}")

        names = [r.name.lower() for r in self.rules]
        if len(set(names)) != CANONICAL_LSR_COUNT:
            raise ValueError(f"Duplicate rule names detected: {[r.name for r in self.rules]}")

        short_names = [r.short_name.lower() for r in self.rules]
        if len(set(short_names)) != CANONICAL_LSR_COUNT:
            raise ValueError(f"Duplicate short names detected: {[r.short_name for r in self.rules]}")

        return self


def find_canonical_lsr_config_path() -> Path:
    """Locates the canonical lsr_rules.yaml file in configs/ or backend/app/nlp/."""
    current_file = Path(__file__).resolve()
    # Search candidates:
    # 1. <workspace_root>/configs/lsr_rules.yaml
    # 2. <backend_root>/configs/lsr_rules.yaml
    # 3. backend/app/nlp/lsr_rules.yaml
    candidates = [
        current_file.parents[3] / "configs" / "lsr_rules.yaml",
        current_file.parents[2] / "configs" / "lsr_rules.yaml",
        current_file.parent / "lsr_rules.yaml",
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    raise FileNotFoundError(f"Canonical LSR configuration not found in candidates: {candidates}")


@lru_cache(maxsize=1)
def load_canonical_lsr_rules() -> list[LsrRuleConfig]:
    """Loads and validates the canonical 12 Life-Saving Rules.
    Fails fast with ValueError / FileNotFoundError if invalid.
    """
    path = find_canonical_lsr_config_path()
    raw_content = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw_content)

    if not isinstance(data, dict) or "rules" not in data:
        raise ValueError(f"Invalid LSR YAML structure at {path}. Root must contain 'rules' list.")

    config = LsrConfigFile(**data)
    # Sort by ID order: LSR01 to LSR12
    return sorted(config.rules, key=lambda r: r.id)


@lru_cache(maxsize=1)
def get_rule_id_map() -> dict[str, LsrRuleConfig]:
    """Mapping from rule ID (e.g. 'LSR01') to LsrRuleConfig."""
    return {r.id: r for r in load_canonical_lsr_rules()}


@lru_cache(maxsize=1)
def get_rule_name_map() -> dict[str, LsrRuleConfig]:
    """Mapping from canonical name (case-insensitive) and aliases to LsrRuleConfig."""
    mapping: dict[str, LsrRuleConfig] = {}
    for r in load_canonical_lsr_rules():
        mapping[r.name.lower()] = r
        mapping[r.short_name.lower()] = r
        mapping[r.id.lower()] = r
        # Legacy snake_case key matching
        snake = r.name.lower().replace(" ", "_").replace("-", "_")
        mapping[snake] = r
    return mapping


def get_rule_by_id(rule_id: str) -> LsrRuleConfig | None:
    return get_rule_id_map().get(rule_id.strip().upper())


def get_rule_by_name(name_or_alias: str) -> LsrRuleConfig | None:
    return get_rule_name_map().get(name_or_alias.strip().lower())


def get_canonical_rule_names() -> list[str]:
    """Returns canonical names of all 12 rules in canonical order (LSR01 to LSR12)."""
    return [r.name for r in load_canonical_lsr_rules()]


def get_canonical_rule_metadata() -> list[dict[str, Any]]:
    """Returns list of rule metadata for API exposure."""
    return [
        {
            "rule_id": r.id,
            "name": r.name,
            "short_name": r.short_name,
            "description": r.description,
            "related_energy_types": r.related_energy_types,
            "related_exposure_types": r.related_exposure_types,
            "related_barrier_types": r.related_barrier_types,
        }
        for r in load_canonical_lsr_rules()
    ]
