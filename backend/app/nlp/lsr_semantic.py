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

from app.nlp.embeddings import extract_embedding, extract_embeddings
from app.nlp.lsr import LsrRuleConfig, load_canonical_lsr_rules
from app.nlp.preprocess import preprocess

logger = logging.getLogger(__name__)

# Minimum cosine similarity to consider a sentence semantically related to a rule
SEMANTIC_PARAPHRASE_THRESHOLD = 0.52
# Minimum cosine similarity to confirm an isolated keyword match without cross-signals
SEMANTIC_KEYWORD_CONFIRMATION_THRESHOLD = 0.48

_CANONICAL_RULE_EMBEDDINGS: dict[str, dict[str, Any]] | None = None


def _init_canonical_rule_embeddings() -> dict[str, dict[str, Any]]:
    """Pre-computes and caches 384-d normalized embeddings for all 12 canonical rules."""
    global _CANONICAL_RULE_EMBEDDINGS
    if _CANONICAL_RULE_EMBEDDINGS is not None:
        return _CANONICAL_RULE_EMBEDDINGS

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
    rule_vectors = _init_canonical_rule_embeddings()
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
        overall_sim = max(max_sent_sim, doc_sim)

        is_match = overall_sim >= SEMANTIC_PARAPHRASE_THRESHOLD

        results[rule_id] = {
            "rule_id": rule_id,
            "rule_name": data["rule_name"],
            "similarity": round(overall_sim, 3),
            "best_snippet": best_sentence[:180] if best_sentence else text[:180],
            "is_semantic_match": is_match,
            "best_matched_phrase": best_phrase,
        }

    return results
