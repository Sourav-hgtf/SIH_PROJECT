"""Central three-way SIF decision policy shared by serving and persistence."""
from __future__ import annotations

from typing import Literal

from app.config import settings

SifClassificationState = Literal["SIF_LIKELY", "UNCERTAIN", "NON_SIF"]


def state_for_probability(probability: float) -> SifClassificationState:
    """Map a calibrated probability to the operational SIF decision band."""
    score = max(0.0, min(1.0, float(probability)))
    if score >= settings.sif_likely_threshold:
        return "SIF_LIKELY"
    if score >= settings.sif_uncertain_lower_threshold:
        return "UNCERTAIN"
    return "NON_SIF"


def requires_analyst_review(state: SifClassificationState) -> bool:
    return state == "UNCERTAIN"
