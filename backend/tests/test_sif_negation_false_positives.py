"""Build-blocking false-positive regressions for SIF and LSR classification."""

import pytest

from app.config import settings
from app.nlp.classify import classify_sif, tag_life_saving_rules


@pytest.mark.parametrize(
    "report",
    [
        "No worker exposed",
        "No lift was performed",
        "No energy release occurred",
        "Isolation was verified before work",
        "PTW was valid and confirmed",
        "Forklift moving pipe bundles at night.",
    ],
)
def test_non_hazard_or_explicitly_negated_reports_never_become_sif_or_lsr_false_positives(report):
    """Neutral, completed-control, and negated reports must not trigger risk output."""
    classification = classify_sif(report)
    lsr_tags = tag_life_saving_rules(report)

    assert classification["sif_label"] is False, report
    assert classification["sif_probability"] < settings.sif_threshold, report
    assert lsr_tags == [], report
