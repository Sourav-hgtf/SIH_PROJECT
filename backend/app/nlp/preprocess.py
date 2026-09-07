from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

DATA_DIR = Path(__file__).resolve().parent
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
        pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(key)}(?![A-Za-z0-9])", re.IGNORECASE)
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


PII_PATTERNS = [
    (re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+(?: [A-Z][a-z]+)?\b"), "[PERSON]"),
    (re.compile(r"\bEMP[- ]?\d{3,8}\b", re.IGNORECASE), "[ID]"),
    (re.compile(r"\b(?:OIL|EMP)ID[:\s-]*\d{4,10}\b", re.IGNORECASE), "[ID]"),
    (re.compile(r"\b\d{10}\b"), "[PHONE]"),
    (re.compile(r"\+91[-\s]?\d{10}\b"), "[PHONE]"),
    (re.compile(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b"), "[PHONE]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
]


def redact_pii(text: str) -> tuple[str, int]:
    redacted = text
    count = 0
    for pattern, token in PII_PATTERNS:
        redacted, n = pattern.subn(token, redacted)
        count += n
    return redacted, count


def preprocess(raw_text: str) -> dict:
    redacted, pii_count = redact_pii(raw_text)
    spelled = correct_spelling(redacted)
    expanded = expand_abbreviations(spelled)
    return {
        "raw_text_redacted": redacted,
        "processed_text": expanded,
        "pii_replacements": pii_count,
    }
