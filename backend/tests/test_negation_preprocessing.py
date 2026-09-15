"""Regression tests for negated hazard/exposure preprocessing."""

from app.config import settings
from app.nlp.negation import suppress_negated_hazard_phrases
from app.nlp.pipeline import process_report_text
from app.nlp.precursors import extract_precursor
from app.nlp.preprocess import preprocess


def test_negated_exposure_is_removed_before_downstream_nlp():
    result = preprocess("No worker was exposed to H2S during the inspection.")

    assert result["processed_text"] == ""
    assert result["negated_phrases"] == ["No worker was exposed to Hydrogen Sulfide during the inspection."]
    assert result["negation_detection_enabled"] is True


def test_negated_activity_scope_keeps_a_separate_asserted_hazard():
    result = suppress_negated_hazard_phrases(
        "The lift was not performed, but workers were near a live electrical panel."
    )

    assert "lift" not in result.text.lower()
    assert "live electrical panel" in result.text.lower()
    assert result.negated_phrases == ["The lift was not performed"]


def test_control_failures_are_not_mistaken_for_negated_hazards():
    result = preprocess("No gas test was performed before confined space entry.")

    assert "gas test" in result["processed_text"].lower()
    assert "confined space entry" in result["processed_text"].lower()
    assert result["negated_phrases"] == []


def test_public_precursor_entrypoint_applies_the_shared_boundary():
    record = extract_precursor("The lift was not performed.")

    assert record.activity is None
    assert record.hazard_exposure is None


def test_pipeline_passes_the_same_negation_cleaned_text_to_all_consumers(monkeypatch):
    seen: list[str] = []

    def capture(text, *args, **kwargs):
        seen.append(text)
        return {} if len(seen) == 1 else []

    monkeypatch.setattr("app.nlp.pipeline.classify_sif", capture)
    monkeypatch.setattr("app.nlp.pipeline.tag_life_saving_rules", capture)
    monkeypatch.setattr("app.nlp.pipeline.extract_precursor", lambda text, **kwargs: (seen.append(text), None)[1])

    process_report_text("No worker was exposed to H2S.")

    assert seen == ["", "", ""]


def test_negation_detection_can_be_disabled(monkeypatch):
    monkeypatch.setattr(settings, "negation_detection_enabled", False)

    result = preprocess("No worker was exposed to H2S.")

    assert "Hydrogen Sulfide" in result["processed_text"]
    assert result["negated_phrases"] == []
    assert result["negation_detection_method"] == "disabled"
