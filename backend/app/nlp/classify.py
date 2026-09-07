from __future__ import annotations

from functools import lru_cache
import re
from typing import Any

from app.nlp.features import extract_features
from app.nlp.labeling import apply_labeling_functions
from app.nlp.lsr import (
    get_canonical_rule_names,
    get_rule_by_id,
    get_rule_by_name,
    load_canonical_lsr_rules,
    LsrRuleConfig,
)
from app.nlp.model import predict_sif_probability

# Minimum confidence threshold for tagging an LSR (configurable)
DEFAULT_LSR_CONFIDENCE_THRESHOLD = 0.50


@lru_cache(maxsize=1)
def _get_lsr_display_mapping() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for r in load_canonical_lsr_rules():
        mapping[r.name.lower().replace(" ", "_").replace("-", "_")] = r.name
        mapping[r.id.lower()] = r.name
        mapping[r.short_name.lower().replace(" ", "_")] = r.name
    return mapping


class _LsrDisplayProxy(dict):
    """Backwards-compatible dict proxy for legacy LSR_DISPLAY lookups."""
    def get(self, key: str, default: Any = None) -> Any:
        return _get_lsr_display_mapping().get(str(key).lower(), default or key)

    def __getitem__(self, key: str) -> Any:
        res = _get_lsr_display_mapping().get(str(key).lower())
        if res is None:
            return key
        return res


LSR_DISPLAY = _LsrDisplayProxy()


def load_lsr_rules() -> dict[str, list[str]]:
    """Backward-compatible helper returning legacy rule phrase map."""
    rules = load_canonical_lsr_rules()
    return {r.name.lower().replace(" ", "_").replace("-", "_"): r.phrases for r in rules}


def tag_life_saving_rules(
    text: str,
    threshold: float = DEFAULT_LSR_CONFIDENCE_THRESHOLD,
) -> list[dict[str, Any]]:
    """Classifies report text against the 12 canonical IOGP Life-Saving Rules.

    Uses deterministic text matching (phrases, keywords) combined with
    structured safety cross-signals (energy types, exposure/proximity, barrier failures).
    Supports multi-rule detection and returns structured evidence per rule.
    """
    canonical_rules = load_canonical_lsr_rules()
    lowered = text.lower()
    features = extract_features(text)
    tags: list[dict[str, Any]] = []

    for rule in canonical_rules:
        evidence: list[dict[str, str]] = []
        phrase_hits: list[str] = []
        kw_hits: list[str] = []

        # 1. Multi-word phrase matching
        for phrase in rule.phrases:
            p_lower = phrase.lower()
            if p_lower in lowered:
                phrase_hits.append(phrase)
                evidence.append({"text": phrase, "type": "phrase"})

        # 2. Single keyword matching with word boundaries
        for kw in rule.keywords:
            kw_lower = kw.lower()
            # Avoid duplicating phrase matches
            if any(kw_lower in p.lower() for p in phrase_hits):
                continue
            if re.search(r"\b" + re.escape(kw_lower) + r"\b", lowered):
                kw_hits.append(kw)
                evidence.append({"text": kw, "type": "keyword"})

        # 3. Cross-signal matching: Energy types
        matched_energies: list[str] = []
        for eng in features.energy_types:
            if eng.lower() in [re.lower() for re in rule.related_energy_types]:
                matched_energies.append(eng)
                evidence.append({"text": f"Energy hazard detected: {eng}", "type": "energy"})

        # 4. Cross-signal matching: Barrier failures
        matched_barriers: list[str] = []
        for bar in features.barrier_failures:
            bar_lower = bar.lower()
            for r_bar in rule.related_barrier_types:
                if r_bar.lower() in bar_lower or bar_lower in r_bar.lower():
                    matched_barriers.append(bar)
                    evidence.append({"text": f"Barrier failure detected: {bar}", "type": "barrier"})
                    break

        # 5. Cross-signal matching: Proximity / Exposure
        matched_exposures: list[str] = []
        for prox in features.proximity_hits:
            prox_lower = prox.lower()
            for r_exp in rule.related_exposure_types:
                if r_exp.lower() in prox_lower or prox_lower in r_exp.lower():
                    matched_exposures.append(prox)
                    evidence.append({"text": f"Exposure detected: {prox}", "type": "exposure"})
                    break

        # 6. Calculate deterministic confidence
        confidence = 0.0
        source = "rule"

        if phrase_hits:
            # Strong direct phrase match
            confidence = 0.62 + min(0.22, 0.07 * len(phrase_hits))
        elif kw_hits:
            # Moderate direct keyword match
            confidence = 0.48 + min(0.16, 0.05 * len(kw_hits))
        elif (matched_energies and matched_barriers) or (matched_energies and matched_exposures):
            # Purely implied via energy + barrier / exposure correlation
            confidence = 0.58
            source = "model"

        # Apply cross-signal boosts when direct evidence exists
        if confidence > 0.0 and source == "rule":
            boost = 0.0
            if matched_energies:
                boost += 0.06
            if matched_barriers:
                boost += 0.06
            if matched_exposures:
                boost += 0.05
            confidence = min(0.98, confidence + boost)

        # 7. Check threshold
        if confidence >= threshold and evidence:
            tags.append(
                {
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "lsr_category": rule.name,
                    "confidence": round(confidence, 3),
                    "source": source,
                    "evidence": evidence,
                    "matched_phrases": phrase_hits[:5],
                }
            )

    # Sort descending by confidence, then rule_id
    tags.sort(key=lambda t: (-t["confidence"], t["rule_id"]))
    return tags


def classify_sif(text: str, threshold: float = 0.45) -> dict:
    features = extract_features(text)
    weak = apply_labeling_functions(text)

    # Get ML prediction
    score, model_version = predict_sif_probability(text)

    phrases = []
    for span in features.contributing_spans:
        weight = 0.7
        if any(k in span.lower() for k in ("not isolated", "bypass", "dropped", "h2s", "hydrogen", "no permit")):
            weight = 0.92
        phrases.append({"phrase": span, "weight": weight})
    phrases.sort(key=lambda p: p["weight"], reverse=True)

    return {
        "sif_probability": round(score, 3),
        "sif_label": score >= threshold,
        "model_version": model_version,
        "contributing_phrases": phrases[:8],
        "features": features.as_dict(),
        "weak_supervision": weak,
    }
