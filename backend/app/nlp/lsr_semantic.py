"""Semantic Life-Saving Rule (LSR) matcher and paraphrase analyzer.

Architecture:
  Report Text
    ↓ Sentence Splitting & Uniform Preprocessing
  Dense Embedding Extraction (all-MiniLM-L6-v2, 384 dimensions)
    ↓
  Cosine Similarity against Pre-computed Canonical Rule Vectors
    (Rule Descriptions + Canonical Indicator Exemplars)
    ↓
  Semantic Similarity Scores, Best Matching Snippet, & Paraphrase Evidence

Guarantees:
1. 100% Local / Offline execution — zero external API calls.
2. Canonical taxonomy strictly enforced: only the 12 official IOGP LSR categories.
3. Returns structured semantic evidence for explainability.
4. Graceful fallback if embedding service is unavailable.
"""

from __future__ import annotations

import logging
import re
from typing import Any
import numpy as np

from app.nlp.lsr import LsrRuleConfig, load_canonical_lsr_rules
from app.nlp.preprocess import preprocess

logger = logging.getLogger(__name__)

# Minimum cosine similarity to consider a sentence semantically related to a rule
SEMANTIC_PARAPHRASE_THRESHOLD = 0.52
# Minimum cosine similarity to confirm an isolated keyword match without cross-signals
SEMANTIC_KEYWORD_CONFIRMATION_THRESHOLD = 0.48

_CANONICAL_RULE_EMBEDDINGS: dict[str, dict[str, Any]] | None = None
_DENSE_MATCHER_UNAVAILABLE = False

# A conservative local semantic fallback.  Each entry is a set of concepts that
# must co-occur for a paraphrase to be considered.  This is deliberately not a
# second keyword classifier: a lone term never produces a match.  It keeps LSR
# detection available in small/offline deployments where sentence-transformers
# is not installed, while the embedding model remains the preferred matcher.
_CONCEPT_PROFILES: dict[str, tuple[tuple[str, ...], ...]] = {
    "LSR01": (("bypass", "override", "disable", "defeat", "inhibit", "jumper"), ("interlock", "trip", "alarm", "guard", "limit switch", "safety control")),
    "LSR02": (("enter", "entry", "access", "ingress", "manway"), ("atmosphere", "atmospheric", "air", "gas", "vapour", "oxygen", "h2s"), ("test", "verify", "verified", "monitor", "sample", "check")),
    "LSR03": (("driver", "driving", "vehicle", "truck", "car", "journey"), ("speed", "seat belt", "restraint", "distraction", "phone", "revers")),
    "LSR04": (("isolate", "lockout", "tagout", "loto", "depressurize", "vent", "bleed", "zero energy"), ("energy", "pressure", "electrical", "live", "hydraulic", "valve", "panel")),
    "LSR05": (("weld", "grind", "torch", "cut", "spark", "hot work"), ("flammable", "combustible", "vapour", "ignition", "fire watch", "gas test", "hydrocarbon")),
    "LSR06": (("under", "line of fire", "drop zone", "pinch", "struck", "crush", "trajectory", "whip"), ("load", "object", "hose", "pressure", "moving", "release", "debris")),
    "LSR07": (("crane", "hoist", "rigging", "sling", "lift", "lifting", "forklift"), ("load", "rated", "capacity", "overload", "suspended", "shackle", "tag line")),
    "LSR08": (("change", "modify", "alter", "deviation", "workaround"), ("approval", "review", "moc", "authorize", "document", "engineering")),
    "LSR09": (("fatigue", "tired", "insomnia", "sleep", "exhaust", "disorient", "impair", "alcohol", "medication"), ("duty", "work", "shift", "operate", "worker", "operator")),
    "LSR10": (("permit", "ptw", "authorization", "clearance", "jsa", "toolbox"), ("without", "missing", "expired", "valid", "before", "commence", "start", "work")),
    "LSR11": (("height", "scaffold", "ladder", "platform", "roof", "elevated", "catwalk"), ("harness", "lanyard", "fall arrest", "anchor", "fall", "edge protection")),
    "LSR12": (("ppe", "helmet", "glove", "goggle", "respirator", "coverall", "eye shield", "boot"), ("without", "missing", "no ", "not worn", "protect", "apparel")),
}


def _concept_matches(text: str, concepts: tuple[str, ...]) -> list[str]:
    """Return concepts found using word boundaries, including safe prefix forms."""
    matches: list[str] = []
    for concept in concepts:
        # Terms ending in a stem (e.g. ``revers``) intentionally match common
        # inflections such as reversing, but still require a word boundary.
        pattern = r"\b" + re.escape(concept) + (r"\w*\b" if concept.endswith(("s", "e", "t", "d", "r")) and " " not in concept else r"\b")
        if re.search(pattern, text, flags=re.IGNORECASE):
            matches.append(concept)
    return matches


def _conceptual_semantic_scores(text: str) -> dict[str, dict[str, Any]]:
    """Score only multi-concept, rule-specific paraphrases without embeddings."""
    normalized = " ".join(preprocess(text)["processed_text"].lower().split())
    sentences = _split_into_sentences(normalized) or [normalized]
    results: dict[str, dict[str, Any]] = {}
    for rule in load_canonical_lsr_rules():
        profile = _CONCEPT_PROFILES[rule.id]
        best_score, best_sentence, best_hits = 0.0, "", []
        for sentence in sentences:
            hits = [hit for group in profile for hit in _concept_matches(sentence, group)]
            covered = sum(bool(_concept_matches(sentence, group)) for group in profile)
            # Two independent concepts are the minimum; three-concept profiles
            # require all three to prevent broad terms such as "atmosphere" or
            # "permit" from generating unrelated LSRs.
            required = len(profile) if len(profile) == 3 else 2
            if covered >= required:
                score = 0.54 + 0.12 * (covered / len(profile)) + min(0.12, 0.02 * len(hits))
                if score > best_score:
                    best_score, best_sentence, best_hits = score, sentence, hits
        results[rule.id] = {
            "rule_id": rule.id,
            "rule_name": rule.name,
            "similarity": round(best_score, 3),
            "best_snippet": best_sentence[:180],
            "is_semantic_match": best_score >= SEMANTIC_PARAPHRASE_THRESHOLD,
            "best_matched_phrase": None,
            "matched_concepts": best_hits,
            "matcher": "conceptual_fallback",
        }
    return results


def _init_canonical_rule_embeddings() -> dict[str, dict[str, Any]]:
    """Pre-computes and caches 384-d normalized embeddings for all 12 canonical rules."""
    global _CANONICAL_RULE_EMBEDDINGS
    if _CANONICAL_RULE_EMBEDDINGS is not None:
        return _CANONICAL_RULE_EMBEDDINGS

    # Import lazily: semantic LSR tagging must retain a useful local fallback
    # when optional sentence-transformer dependencies are not present.
    from app.nlp.embeddings import extract_embedding

    rules = load_canonical_lsr_rules()
    cache: dict[str, dict[str, Any]] = {}

    for rule in rules:
        # 1. Primary rule intent text (name + description)
        intent_text = f"{rule.name}: {rule.description}"
        intent_vec = extract_embedding(intent_text)

        # 2. Canonical exemplar phrases (top representative phrases)
        phrase_vecs = []
        for p in rule.phrases[:10]:
            phrase_vecs.append(extract_embedding(p))

        cache[rule.id] = {
            "rule_id": rule.id,
            "rule_name": rule.name,
            "intent_vector": intent_vec,
            "phrase_vectors": phrase_vecs,
            "phrases": rule.phrases[:10],
        }

    _CANONICAL_RULE_EMBEDDINGS = cache
    logger.info(f"Pre-computed canonical semantic embeddings for {len(cache)} LSR categories.")
    return _CANONICAL_RULE_EMBEDDINGS


def _split_into_sentences(text: str) -> list[str]:
    """Split text into individual sentences for fine-grained snippet matching."""
    if not text:
        return []
    # Split by period, semicolon, exclamation, question mark, or newline
    raw_sents = re.split(r"(?<=[.!?;\n])\s+", text)
    cleaned = [s.strip() for s in raw_sents if s and len(s.strip()) > 5]
    return cleaned if cleaned else [text.strip()]


def compute_semantic_lsr_scores(text: str) -> dict[str, dict[str, Any]]:
    """Computes semantic similarity scores for all 12 canonical rules on the input text.

    Returns mapping from rule_id -> {
        "similarity": float (0.0 to 1.0),
        "best_snippet": str,
        "is_semantic_match": bool,
        "best_matched_phrase": str | None,
    }
    """
    global _DENSE_MATCHER_UNAVAILABLE
    fallback = _conceptual_semantic_scores(text)
    if _DENSE_MATCHER_UNAVAILABLE:
        return fallback
    try:
        rule_vectors = _init_canonical_rule_embeddings()
        from app.nlp.embeddings import extract_embedding, extract_embeddings
    except Exception as exc:
        _DENSE_MATCHER_UNAVAILABLE = True
        logger.info("Dense LSR semantic matching unavailable; using conceptual fallback: %s", exc)
        return fallback
    sentences = _split_into_sentences(text)
    if not sentences:
        sentences = [text]

    # Batch extract embeddings for all sentences
    sent_embeddings = extract_embeddings(sentences)
    # Also extract embedding for full document text
    doc_embedding = extract_embedding(text)

    results: dict[str, dict[str, Any]] = {}

    for rule_id, data in rule_vectors.items():
        intent_vec = data["intent_vector"]
        phrase_vecs = data["phrase_vectors"]
        phrases = data["phrases"]

        max_sent_sim = 0.0
        best_sentence = ""
        best_phrase = None

        # Check sentence similarities against rule intent
        for i, s_vec in enumerate(sent_embeddings):
            sim = float(np.dot(s_vec, intent_vec))
            if sim > max_sent_sim:
                max_sent_sim = sim
                best_sentence = sentences[i]

        # Check sentence similarities against canonical phrase exemplars
        for i, s_vec in enumerate(sent_embeddings):
            for j, p_vec in enumerate(phrase_vecs):
                sim = float(np.dot(s_vec, p_vec))
                if sim > max_sent_sim:
                    max_sent_sim = sim
                    best_sentence = sentences[i]
                    best_phrase = phrases[j]

        # Document-level similarity
        doc_sim = float(np.dot(doc_embedding, intent_vec))
        # Dense similarity can contribute only when it agrees with the
        # conservative concept matcher.  This avoids assigning an LSR from a
        # vague embedding neighbourhood or a weak unrelated keyword.
        conceptual = fallback[rule_id]
        overall_sim = max(max_sent_sim, doc_sim)
        if conceptual["is_semantic_match"]:
            overall_sim = max(overall_sim, float(conceptual["similarity"]))
        else:
            overall_sim = min(overall_sim, SEMANTIC_PARAPHRASE_THRESHOLD - 0.001)

        is_match = overall_sim >= SEMANTIC_PARAPHRASE_THRESHOLD

        results[rule_id] = {
            "rule_id": rule_id,
            "rule_name": data["rule_name"],
            "similarity": round(overall_sim, 3),
            "best_snippet": (conceptual["best_snippet"] if conceptual["is_semantic_match"] else best_sentence[:180] if best_sentence else text[:180]),
            "is_semantic_match": is_match,
            "best_matched_phrase": best_phrase,
            "matched_concepts": conceptual["matched_concepts"],
            "matcher": "dense_plus_concepts",
        }

    return results
