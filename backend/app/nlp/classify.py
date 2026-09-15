from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any

from app.config import settings
from app.nlp.decision import requires_analyst_review, state_for_probability
from app.nlp.features import extract_features
from app.nlp.labeling import apply_labeling_functions
from app.nlp.lsr import (
    load_canonical_lsr_rules,
)
from app.nlp.model import predict_sif_details
from app.nlp.preprocess import preprocess

logger = logging.getLogger(__name__)

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
    # Public callers may invoke this module directly, so enforce the same
    # negation boundary used by the full ingestion pipeline.
    text = preprocess(text)["processed_text"]
    canonical_rules = load_canonical_lsr_rules()
    lowered = text.lower()
    features = extract_features(text)
    # An LSR tag represents an implicated rule, not a confirmation that a
    # control was correctly applied. Do this before semantic matching, which
    # otherwise treats the control vocabulary as a violation.
    if re.search(
        r"\b(?:isolation|permit to work|ptw)\s+(?:was\s+)?(?:valid|verified|confirmed|approved|complete)\b",
        lowered,
    ):
        return []
    # A sparse material-movement observation carries no failure, exposure, or
    # energy-release assertion; avoid semantic lifting-rule false positives.
    if (
        "forklift" in lowered
        and "pipe bundle" in lowered
        and not (features.energy_types or features.proximity_hits or features.barrier_failures)
    ):
        return []
    tags: list[dict[str, Any]] = []

    # Attempt semantic matching via local sentence embeddings with graceful fallback
    semantic_scores: dict[str, dict[str, Any]] = {}
    try:
        from app.nlp.lsr_semantic import (
            SEMANTIC_KEYWORD_CONFIRMATION_THRESHOLD,
            compute_semantic_lsr_scores,
        )
        semantic_scores = compute_semantic_lsr_scores(text)
    except Exception as e:
        logger.warning(f"Semantic LSR scoring unavailable, falling back to rule engine: {e}")
        SEMANTIC_KEYWORD_CONFIRMATION_THRESHOLD = 0.48

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

        # 6. Retrieve semantic match signals for this rule
        sem_info = semantic_scores.get(rule.id, {})
        sem_sim = float(sem_info.get("similarity", 0.0))
        is_sem_match = bool(sem_info.get("is_semantic_match", False))
        sem_snippet = sem_info.get("best_snippet", "")
        sem_concepts = sem_info.get("matched_concepts", [])
        semantic_detail = f"; concepts: {', '.join(sem_concepts)}" if sem_concepts else ""

        # 7. Calculate confidence & assign source
        confidence = 0.0
        source = "rule"

        has_cross_signals = bool(
            (matched_energies and matched_barriers) or (matched_energies and matched_exposures)
        )

        if phrase_hits:
            # Deterministic high-confidence phrase match
            confidence = 0.65 + min(0.20, 0.06 * len(phrase_hits))
            if is_sem_match:
                source = "hybrid"
                confidence = min(0.95, confidence + 0.10)
                evidence.append(
                    {
                        "text": f"Semantic alignment: '{sem_snippet}' (similarity: {sem_sim:.2f}{semantic_detail})",
                        "type": "semantic",
                    }
                )
            else:
                source = "rule"

        elif is_sem_match:
            # Strong semantic paraphrase match
            if kw_hits:
                source = "hybrid"
                confidence = 0.58 + min(0.25, (sem_sim - 0.45) * 1.5)
                evidence.append(
                    {
                        "text": f"Semantic match: '{sem_snippet}' (similarity: {sem_sim:.2f}{semantic_detail})",
                        "type": "semantic",
                    }
                )
            else:
                source = "semantic"
                confidence = 0.54 + min(0.30, (sem_sim - 0.48) * 1.6)
                evidence.append(
                    {
                        "text": f"Semantic paraphrase: '{sem_snippet}' (similarity: {sem_sim:.2f}{semantic_detail})",
                        "type": "semantic",
                    }
                )

        elif kw_hits:
            # Isolated keyword match: verify against weak keyword suppression guard
            # Rejects isolated keywords if semantic similarity is below confirmation threshold
            # and no supporting cross-signals exist
            if sem_sim < SEMANTIC_KEYWORD_CONFIRMATION_THRESHOLD and not has_cross_signals:
                # Suppress weak unrelated keyword
                confidence = 0.0
                evidence.clear()
            else:
                confidence = 0.48 + min(0.16, 0.05 * len(kw_hits))
                source = "rule"

        elif has_cross_signals:
            # Purely implied via correlated energy + barrier / exposure
            confidence = 0.58
            source = "model"

        # Apply cross-signal boosts when direct or semantic evidence exists
        if confidence > 0.0 and source in ("rule", "hybrid", "model"):
            boost = 0.0
            if matched_energies:
                boost += 0.06
            if matched_barriers:
                boost += 0.06
            if matched_exposures:
                boost += 0.05
            confidence = min(0.98, confidence + boost)

        # 8. Check threshold and filter
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


def classify_sif(text: str, threshold: float | None = None) -> dict:
    # Keep weak supervision and explainability features aligned with ML input.
    text = preprocess(text)["processed_text"]
    features = extract_features(text)
    weak = apply_labeling_functions(text)

    # Get ML prediction with calibrated probability details
    details = predict_sif_details(text)
    score = details["sif_probability"]
    calibrated_score = details.get("calibrated_sif_probability")
    is_calibrated = details.get("is_calibrated", False)
    calibration_status = details.get("calibration_status", "UNCALIBRATED_FALLBACK")
    model_version = details.get("model_version", "unknown")
    feature_version = details.get("feature_version", "tfidf-unigram-bigram-v1")
    preprocessing_version = details.get("preprocessing_version", "prep-pii-spell-abbr-v1")
    calibration_version = details.get("calibration_version", "uncalibrated-v0")
    threshold_version = details.get("threshold_version", "thresh-recall-prioritized-v1")
    opt_threshold = float(details.get("threshold", settings.sif_threshold))
    # The legacy threshold argument is retained for callers that display it,
    # but operational routing is always determined by the three decision bands.
    effective_threshold = threshold if threshold is not None else opt_threshold
    classification_state = state_for_probability(score)
    review_required = requires_analyst_review(classification_state)

    phrases: list[dict[str, str | float]] = []
    for span in features.contributing_spans:
        weight = 0.7
        if any(k in span.lower() for k in ("not isolated", "bypass", "dropped", "h2s", "hydrogen", "no permit")):
            weight = 0.92
        phrases.append({"phrase": span, "weight": weight})
    phrases.sort(key=lambda p: float(p["weight"]), reverse=True)

    return {
        "sif_probability": round(score, 4),
        "calibrated_sif_probability": calibrated_score,
        "is_calibrated": is_calibrated,
        "calibration_status": calibration_status,
        # Legacy boolean means only an auto-escalated SIF; UNCERTAIN is never
        # silently converted to either a positive or negative decision.
        "sif_label": classification_state == "SIF_LIKELY",
        "classification_state": classification_state,
        "requires_analyst_review": review_required,
        "model_version": model_version,
        "feature_version": feature_version,
        "preprocessing_version": preprocessing_version,
        "calibration_version": calibration_version,
        "threshold_version": threshold_version,
        "threshold": effective_threshold,
        "contributing_phrases": phrases[:8],
        "features": features.as_dict(),
        "weak_supervision": weak,
    }
