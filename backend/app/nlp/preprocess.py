"""preprocess.py – text cleaning, spell-correction, abbreviation expansion, and PII redaction.

PII detection strategy (PERSON entities):
  1. Domain exclusion list – known job titles, chemical names, equipment phrases that
     are NOT person names.  Evaluated first, O(1) lookup.
  2. spaCy NER (en_core_web_sm) – labels a span PERSON only when the model has
     contextual evidence.  Runs fully offline; no external API calls.
  3. Graceful fallback – if spaCy is unavailable the module falls back to a
     regex + exclusion-list approach so the pipeline never breaks.

All other PII patterns (email, phone, employee IDs) are unchanged.
Redaction tokens ([PERSON], [PHONE], [EMAIL], [ID]) are unchanged.
The public API – redact_pii(text) -> (str, int) – is unchanged.
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Spell-correction map (unchanged)
# ---------------------------------------------------------------------------
SPELL_MAP = {
    "sefty": "safety",
    "saftey": "safety",
    "harnes": "harness",
    "scaffld": "scaffold",
    "scafolding": "scaffolding",
    "isolaton": "isolation",
    "electrial": "electrical",
    "presure": "pressure",
    "leakeage": "leakage",
    "permitt": "permit",
}

# ---------------------------------------------------------------------------
# Domain-specific exclusion list
# Phrases that look like Title-Case names but are NOT personal names.
# All entries stored lowercase for case-insensitive matching.
# ---------------------------------------------------------------------------
_EXCLUSION_PHRASES: frozenset[str] = frozenset({
    # Job roles / titles
    "safety officer", "safety manager", "safety supervisor",
    "hsse officer", "hsse manager",
    "production engineer", "production supervisor", "production operator",
    "mechanical engineer", "mechanical supervisor", "mechanical technician",
    "electrical engineer", "electrical supervisor", "electrical technician",
    "instrument engineer", "instrument technician",
    "process engineer", "process supervisor",
    "drilling engineer", "drilling supervisor",
    "wellsite supervisor", "rig supervisor", "rig manager",
    "operations supervisor", "operations manager",
    "shift supervisor", "shift operator",
    "control room", "permit issuer", "permit receiver",
    "fire watch", "rescue team", "response team",
    "crane operator", "forklift operator", "scaffold inspector",
    "area authority", "senior technician", "lead operator",
    "chief engineer", "project engineer", "site engineer",
    "construction supervisor", "maintenance supervisor", "maintenance technician",
    "instrument supervisor", "safety representative", "safety advisor",
    "asset manager", "plant manager", "field supervisor",
    "health officer", "environment officer", "risk officer",
    "quality inspector", "quality engineer",
    # Chemical / substance names
    "hydrogen sulfide", "hydrogen sulphide",
    "carbon monoxide", "carbon dioxide",
    "nitrogen oxide", "sulfur dioxide",
    "methane gas", "natural gas",
    "liquefied petroleum", "liquefied natural",
    # Equipment / systems
    "blowout preventer", "emergency shutdown",
    "wellhead pressure", "wellhead platform",
    "production platform", "production separator",
    "pressure relief", "pressure vessel", "pressure gauge",
    "electrical panel", "control panel", "junction box",
    "motor control", "check valve", "ball valve",
    "gate valve", "safety valve", "relief valve",
    "isolation valve", "diesel generator",
    "gas detector", "fire detector", "smoke detector",
    "heat detector", "sprinkler system", "deluge system",
    "foam system", "anchor chain", "mooring system",
    # Standards / documents
    "permit work", "work authorization", "toolbox talk",
    "risk assessment", "job safety", "management change",
    "root cause", "incident report", "near miss", "corrective action",
})

# Single-word exclusion tokens – if every word of a span is in this set,
# the span is not a person name.
_EXCLUSION_TOKENS: frozenset[str] = frozenset({
    "safety", "officer", "engineer", "supervisor", "manager", "technician",
    "operator", "inspector", "advisor", "representative", "hydrogen", "sulfide",
    "sulphide", "carbon", "methane", "nitrogen", "oxygen", "pressure", "electrical",
    "mechanical", "instrument", "drilling", "wellsite", "production", "operations",
    "maintenance", "construction", "project", "permit", "rescue", "response",
    "control", "monitor", "platform", "separator", "generator", "detector",
    "blowout", "preventer", "shutdown", "emergency", "chemical", "thermal",
    "kinetic", "gravity", "process", "wellhead", "offshore", "onshore",
    "facility", "terminal", "refinery", "pipeline", "compressor", "turbine",
    "exchanger", "reactor", "furnace", "distillation", "absorption", "storage",
    "hazardous", "flammable", "explosive", "toxic", "corrosive", "radioactive",
    "health", "environment", "quality", "site", "field", "plant", "asset",
    "senior", "junior", "lead", "chief", "assistant", "deputy",
})

# ---------------------------------------------------------------------------
# English articles and prepositions that can appear as the first word of a
# Title-Case phrase but are never the start of a personal name.
_LEADING_NON_NAME_WORDS: frozenset[str] = frozenset({
    "the", "a", "an", "this", "that", "these", "those",
    "in", "on", "at", "by", "of", "to", "for", "from", "with",
    "no", "not", "and", "or", "but", "if", "as",
})

# Fallback: original broad regex (used when spaCy is unavailable),
# but filtered through the exclusion list.
# ---------------------------------------------------------------------------
_FALLBACK_PERSON_RE = re.compile(
    r"\b[A-Z][a-z]+ [A-Z][a-z]+(?: [A-Z][a-z]+)?\b"
)


def _is_excluded(span: str) -> bool:
    """Return True if span is a known non-person phrase."""
    lower = span.lower()

    # Strip a leading article/preposition before checking the phrase list.
    # e.g. 'The Safety Officer' -> 'safety officer'
    words = lower.split()
    if words and words[0] in _LEADING_NON_NAME_WORDS:
        # If the first word is a non-name word, it cannot be the start of a
        # person's name.  Check the remainder of the phrase.
        remainder = " ".join(words[1:])
        if remainder in _EXCLUSION_PHRASES:
            return True
        if all(w in _EXCLUSION_TOKENS for w in words[1:]):
            return True
        # The phrase starts with an article but the remainder is NOT an
        # exclusion phrase (e.g. 'The Unknown Entity').  Treat first word
        # as non-name and fall through – returning True to suppress it.
        # Rationale: a sentence-initial 'The Foo Bar' is almost never a
        # person reference; real names are written without leading articles.
        return True

    if lower in _EXCLUSION_PHRASES:
        return True
    # If every individual word is an exclusion token, it's not a person
    if all(w in _EXCLUSION_TOKENS for w in words):
        return True
    return False


# ---------------------------------------------------------------------------
# spaCy loader with graceful fallback
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _load_spacy_nlp():
    """Load spaCy en_core_web_sm. Returns None if unavailable."""
    try:
        import importlib
        spacy = importlib.import_module("spacy")
        nlp = spacy.load(
            "en_core_web_sm",
            disable=["parser", "lemmatizer", "attribute_ruler"],
        )
        return nlp
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "spaCy unavailable – falling back to regex PERSON detection: %s", exc
        )
        return None


def _merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping/adjacent spans. Input need not be sorted."""
    if not spans:
        return []
    sorted_spans = sorted(spans)
    merged: list[tuple[int, int]] = [sorted_spans[0]]
    for start, end in sorted_spans[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _redact_persons(text: str) -> tuple[str, int]:
    """Detect and redact PERSON entities. Returns (redacted_text, count).

    Strategy: union of (a) spaCy NER PERSON entities and (b) Title-Case regex
    filtered through the domain exclusion list.  Using both maximises recall:
    en_core_web_sm has low recall on South Asian names, but the exclusion-filtered
    regex covers them while still suppressing job titles and chemical names.
    """
    nlp = _load_spacy_nlp()
    spans: list[tuple[int, int]] = []

    # --- (a) NER-based spans ---
    if nlp is not None:
        doc = nlp(text)
        for ent in doc.ents:
            if ent.label_ == "PERSON" and not _is_excluded(ent.text):
                spans.append((ent.start_char, ent.end_char))

    # --- (b) Regex-based spans filtered by exclusion list ---
    for m in _FALLBACK_PERSON_RE.finditer(text):
        if not _is_excluded(m.group(0)):
            spans.append((m.start(), m.end()))

    # Merge overlapping spans (e.g. NER "Rahul Verma" vs regex "Rahul Verma Singh")
    merged = _merge_spans(spans)

    if not merged:
        return text, 0

    # Replace right-to-left to preserve offsets
    result = text
    for start, end in sorted(merged, reverse=True):
        result = result[:start] + "[PERSON]" + result[end:]
    return result, len(merged)



# ---------------------------------------------------------------------------
# Non-PERSON PII patterns (unchanged from original)
# ---------------------------------------------------------------------------
_NON_PERSON_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bEMP[- ]?\d{3,8}\b", re.IGNORECASE), "[ID]"),
    (re.compile(r"\b(?:OIL|EMP)ID[:\s-]*\d{4,10}\b", re.IGNORECASE), "[ID]"),
    (re.compile(r"\b\d{10}\b"), "[PHONE]"),
    (re.compile(r"\+91[-\s]?\d{10}\b"), "[PHONE]"),
    (re.compile(r"\b\d{3}[-.\ ]\d{3}[-.\ ]\d{4}\b"), "[PHONE]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
]


def redact_pii(text: str) -> tuple[str, int]:
    """Redact PII from *text*.

    Returns ``(redacted_text, total_replacements_count)``.
    Signature and redaction tokens are backward-compatible with the original.
    """
    # 1. Person entities (NER + exclusion list, or fallback regex)
    redacted, count = _redact_persons(text)

    # 2. All other PII (email, phone, IDs)
    for pattern, token in _NON_PERSON_PATTERNS:
        redacted, n = pattern.subn(token, redacted)
        count += n

    return redacted, count


# ---------------------------------------------------------------------------
# Glossary / abbreviation expansion (unchanged)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def load_glossary() -> dict[str, str]:
    raw = yaml.safe_load((DATA_DIR / "abbreviations.yaml").read_text()) or {}
    return {str(k).upper(): str(v) for k, v in raw.items()}


def expand_abbreviations(text: str, glossary: dict[str, str] | None = None) -> str:
    glossary = glossary or load_glossary()
    # Longest keys first so "LO/TO" beats "LO"
    keys = sorted(glossary.keys(), key=len, reverse=True)
    result = text
    for key in keys:
        pattern = re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(key)}(?![A-Za-z0-9])", re.IGNORECASE
        )
        result = pattern.sub(glossary[key], result)
    return result


def correct_spelling(text: str) -> str:
    def repl(match: re.Match) -> str:
        word = match.group(0)
        fixed = SPELL_MAP.get(word.lower())
        if not fixed:
            return word
        if word.isupper():
            return fixed.upper()
        if word[0].isupper():
            return fixed.capitalize()
        return fixed

    return re.sub(r"[A-Za-z']+", repl, text)


def preprocess(raw_text: str) -> dict:
    """Full preprocessing pipeline. Output keys are backward-compatible."""
    redacted, pii_count = redact_pii(raw_text)
    spelled = correct_spelling(redacted)
    expanded = expand_abbreviations(spelled)
    return {
        "raw_text_redacted": redacted,
        "processed_text": expanded,
        "pii_replacements": pii_count,
    }

