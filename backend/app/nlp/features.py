from __future__ import annotations

import re
from dataclasses import dataclass, field

ENERGY_PATTERNS = {
    "electrical": [r"\blive electrical\b", r"\barc flash\b", r"\bhigh voltage\b", r"\benergized\b"],
    "pressure": [r"\bpressure\b", r"\bpressurised\b", r"\bpressurized\b", r"\bwellhead\b", r"\bWHP\b"],
    "gravity": [r"\bdropped object\b", r"\bfall from\b", r"\bsuspended load\b", r"\bworking at height\b"],
    "mechanical": [r"\bcrane\b", r"\brigging\b", r"\brotating equipment\b", r"\bpinch point\b"],
    "chemical": [r"\bhydrogen sulfide\b", r"\bH2S\b", r"\bhydrocarbon\b", r"\bflammable\b", r"\btoxic\b"],
    "thermal": [r"\bhot work\b", r"\bwelding\b", r"\bsteam\b", r"\bmolten\b"],
    "kinetic": [r"\bvehicle\b", r"\bcollision\b", r"\bstruck by\b", r"\bhose whip\b"],
}

PROXIMITY_PATTERNS = [
    r"\bline of fire\b",
    r"\bunder (the )?load\b",
    r"\bstanding under\b",
    r"\bclose proximity\b",
    r"\bwithin the drop zone\b",
    r"\bpath of travel\b",
    r"\bno exclusion zone\b",
    r"\bworkers nearby\b",
]

BARRIER_FAILURE_PATTERNS = [
    r"\bno (permit|Permit to Work)\b",
    r"\bwithout (a )?permit\b",
    r"\bpermit.{0,24}expired\b",
    r"\bpermit (expired|not issued|missing)\b",
    r"\bnot isolated\b",
    r"\block-out tag-out not\b",
    r"\bLOTO not\b",
    r"\bbypass(ed)?\b",
    r"\bmissing (harness|guard|attendant|fire watch|tag line)\b",
    r"\bno gas test\b",
    r"\binterlock defeated\b",
    r"\bwithout authorization\b",
    r"\bguard removed\b",
]


@dataclass
class FeatureSet:
    energy_types: list[str] = field(default_factory=list)
    proximity_hits: list[str] = field(default_factory=list)
    barrier_failures: list[str] = field(default_factory=list)
    contributing_spans: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "energy_types": self.energy_types,
            "proximity_hits": self.proximity_hits,
            "barrier_failures": self.barrier_failures,
            "energy_count": len(self.energy_types),
            "proximity_count": len(self.proximity_hits),
            "barrier_count": len(self.barrier_failures),
        }


def _find(patterns: list[str], text: str) -> list[str]:
    hits = []
    for pat in patterns:
        for match in re.finditer(pat, text, flags=re.IGNORECASE):
            hits.append(match.group(0))
    return hits


def extract_features(text: str) -> FeatureSet:
    energy_types = []
    spans: list[str] = []
    for name, patterns in ENERGY_PATTERNS.items():
        found = _find(patterns, text)
        if found:
            energy_types.append(name)
            spans.extend(found)
    proximity = _find(PROXIMITY_PATTERNS, text)
    barriers = _find(BARRIER_FAILURE_PATTERNS, text)
    spans.extend(proximity)
    spans.extend(barriers)
    # Unique while preserving order
    seen: set[str] = set()
    unique_spans = []
    for span in spans:
        key = span.lower()
        if key not in seen:
            seen.add(key)
            unique_spans.append(span)
    return FeatureSet(
        energy_types=energy_types,
        proximity_hits=proximity,
        barrier_failures=barriers,
        contributing_spans=unique_spans,
    )
