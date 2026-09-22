"""Negation scope detection for safety concepts.

The classifier and rule extractors should not see an asserted hazard when the
report explicitly says that the hazardous event did *not* happen.  This module
uses the installed spaCy dependency parser when available and retains a
deterministic clause-level fallback for local/test environments where the
language model is unavailable.

It intentionally does not suppress safety-control failures such as ``LOTO was
not applied`` or ``no gas test was performed``: those are positive risk
signals, not denials of a hazard or exposure.
"""
from __future__ import annotations

import importlib
import re
from dataclasses import dataclass
from functools import lru_cache

# These are asserted events/exposures whose negation means they must not be
# passed to lexical ML, LSR matching, or precursor extraction.  Barrier-control
# phrases are deliberately excluded; "not isolated" remains safety evidence.
_HAZARD_EVENT_RE = re.compile(
    r"\b(?:"
    r"expos(?:ed|ure)|contact(?:ed)?|inhal(?:ed|ation)|released?|leak(?:ed|age)?|"
    r"spill(?:ed)?|ignit(?:ed|ion)|explod(?:ed|e|ion)|fire|burn(?:ed|ing)?|"
    r"lift(?:ed|ing)?|hoist(?:ed|ing)?|rigg(?:ed|ing)|crane(?:d)?|"
    r"enter(?:ed|ing)?|confined\s+space\s+entry|work(?:ed|ing)?\s+at\s+height|"
    r"fall(?:en|ing)?|dropped?|struck|collision|driv(?:e|en|ing)|"
    r"arc\s+flash|energiz(?:ed|ing)|electrocut(?:ed|ion)"
    r")\b",
    re.IGNORECASE,
)
_NEGATION_RE = re.compile(r"\b(?:no|not|never|neither|nor|without)\b", re.IGNORECASE)
_CLAUSE_SPLIT_RE = re.compile(r"(?<=[,;])|\b(?:but|however|although|whereas)\b", re.IGNORECASE)
_PROTECTED_CONTROL_RE = re.compile(
    r"\b(?:no|without)\s+(?:a\s+)?(?:permit|ptw|harness|gas\s+test|"
    r"isolation|fire\s+watch|attendant|lifeline)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NegationResult:
    """The cleaned model text plus non-sensitive, user-visible scope evidence."""

    text: str
    negated_phrases: list[str]
    method: str


@lru_cache(maxsize=1)
def _load_dependency_parser():
    """Load spaCy with parser enabled; return None when a local fallback is needed."""
    try:
        spacy = importlib.import_module("spacy")
        return spacy.load("en_core_web_sm", disable=["ner", "lemmatizer", "attribute_ruler"])
    except Exception:  # The fallback below is intentionally deterministic.
        return None


def _is_dependency_negated(sentence: str) -> bool:
    """Return whether parser dependencies connect a negator to a hazard event."""
    nlp = _load_dependency_parser()
    if nlp is None:
        return False
    doc = nlp(sentence)
    if _PROTECTED_CONTROL_RE.search(sentence):
        return False
    targets = [token for token in doc if _HAZARD_EVENT_RE.fullmatch(token.text)]
    if not targets:
        return False
    for token in doc:
        # ``not`` normally has dep=neg; ``no worker was exposed`` represents
        # negation as a determiner on the subject, so retain both forms.
        if token.lower_ not in {"no", "not", "never", "neither", "nor"}:
            continue
        head = token.head
        if token.lower_ in {"not", "never", "neither", "nor"}:
            # ``lift was not performed``: lift is a subject of the negated
            # predicate; ``workers were not exposed``: exposed is that head.
            if any(target == head or target.head == head for target in targets):
                return True
        elif token.lower_ == "no":
            # ``no worker was exposed`` has a negated subject; ``no exposure
            # occurred`` has a negated event noun. Do not treat any other
            # sibling of the sentence root as scoped by this determiner.
            predicate = head.head
            if any(target == head or target == predicate for target in targets):
                return True
    return False


def _is_regex_negated(clause: str) -> bool:
    """Conservative fallback: negator must occur close before an event target."""
    for target in _HAZARD_EVENT_RE.finditer(clause):
        prefix = clause[max(0, target.start() - 48):target.start()]
        # A bounded prefix avoids treating an unrelated earlier sentence/claim
        # as a negation scope.  "without" is only accepted for exposure/event
        # wording; it is not used to mask "without a permit/harness" controls.
        if _NEGATION_RE.search(prefix):
            if _PROTECTED_CONTROL_RE.search(prefix):
                continue
            # ``fire`` is also a hazard token, but in "no fire watch" it is
            # part of a missing-control phrase and must remain evidence.
            if any(match.start() <= target.start() < match.end() for match in _PROTECTED_CONTROL_RE.finditer(clause)):
                continue
            return True
    return False


def suppress_negated_hazard_phrases(text: str) -> NegationResult:
    """Remove negated hazard/exposure clauses before downstream NLP.

    Complete clauses are removed rather than merely deleting the negation word;
    leaving ``H2S`` or ``lifting`` behind would still trigger keyword features.
    """
    if not text or not _HAZARD_EVENT_RE.search(text) or not _NEGATION_RE.search(text):
        return NegationResult(text=text, negated_phrases=[], method="none")

    retained: list[str] = []
    suppressed: list[str] = []
    parser_available = _load_dependency_parser() is not None
    # Preserve sentence separators for readability and to prevent adjoining
    # tokens from becoming a new n-gram after removal.
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if not sentence:
            continue
        clauses = [part for part in _CLAUSE_SPLIT_RE.split(sentence) if part]
        for clause in clauses:
            has_target = bool(_HAZARD_EVENT_RE.search(clause))
            is_negated = _is_regex_negated(clause) or (
                parser_available and _is_dependency_negated(clause)
            )
            if has_target and is_negated:
                evidence = " ".join(clause.split()).strip(" ,;")
                if evidence:
                    suppressed.append(evidence)
            else:
                retained.append(clause)

    cleaned = re.sub(r"\s+", " ", " ".join(retained)).strip()
    return NegationResult(
        text=cleaned,
        negated_phrases=suppressed,
        method="spacy_dependency+regex_fallback" if parser_available else "regex_fallback",
    )
