"""Snorkel-style labeling functions. Returns +1 (SIF), -1 (non-SIF), 0 (abstain)."""

from __future__ import annotations

import re

from app.nlp.features import extract_features

ROUTINE_NOISE = re.compile(
    r"\b(housekeeping|slippery floor|missing glove|hard hat not worn|trip hazard|poor housekeeping)\b",
    re.IGNORECASE,
)


def lf_high_energy(text: str) -> int:
    features = extract_features(text)
    high = {"electrical", "pressure", "chemical", "gravity", "thermal"}
    return 1 if set(features.energy_types) & high else 0


def lf_proximity_to_energy(text: str) -> int:
    features = extract_features(text)
    if features.energy_types and features.proximity_hits:
        return 1
    return 0


def lf_barrier_failure_with_energy(text: str) -> int:
    features = extract_features(text)
    if features.energy_types and features.barrier_failures:
        return 1
    return 0


def lf_height_or_dropped_object(text: str) -> int:
    if re.search(r"\b(fall from|no harness|dropped object|working at height|incomplete scaffold)\b", text, re.I):
        return 1
    return 0


def lf_confined_or_h2s(text: str) -> int:
    if re.search(r"\b(confined space|hydrogen sulfide|no gas test|toxic atmosphere)\b", text, re.I):
        return 1
    return 0


def lf_lifting_line_of_fire(text: str) -> int:
    if re.search(r"\b(suspended load|under the load|crane|sling failure|SWL exceeded)\b", text, re.I):
        return 1
    return 0


def lf_routine_low_energy(text: str) -> int:
    features = extract_features(text)
    if ROUTINE_NOISE.search(text) and not features.energy_types and not features.barrier_failures:
        return -1
    return 0


LABELING_FUNCTIONS = [
    lf_high_energy,
    lf_proximity_to_energy,
    lf_barrier_failure_with_energy,
    lf_height_or_dropped_object,
    lf_confined_or_h2s,
    lf_lifting_line_of_fire,
    lf_routine_low_energy,
]


def apply_labeling_functions(text: str) -> dict:
    votes = {fn.__name__: fn(text) for fn in LABELING_FUNCTIONS}
    positives = sum(1 for v in votes.values() if v == 1)
    negatives = sum(1 for v in votes.values() if v == -1)
    if positives == 0 and negatives == 0:
        label = 0
        confidence = 0.35
    elif positives > negatives:
        label = 1
        confidence = min(0.95, 0.5 + 0.1 * positives)
    elif negatives > positives:
        label = -1
        confidence = min(0.9, 0.55 + 0.1 * negatives)
    else:
        label = 0
        confidence = 0.5
    return {"votes": votes, "weak_label": label, "weak_confidence": confidence, "positive_votes": positives}
