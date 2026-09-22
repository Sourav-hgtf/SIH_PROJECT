"""Phase 6 contract tests for evidence-backed SIF precursor extraction."""

from app.nlp.pipeline import process_report_text
from app.nlp.precursors import EXTRACTION_VERSION, extract_precursor


def test_explicit_precursor_has_all_supported_dimensions_and_evidence():
    record = extract_precursor(
        "Technician dismantled the pressurized line without confirming isolation at the wellhead."
    )

    assert record.activity == "Line dismantling / piping break"
    assert record.location == "wellhead"
    assert record.barrier_failure == "Isolation not verified"
    assert record.hazard_exposure == "Stored / pressurized energy"
    assert record.relevant_lsr_id == "LSR04"
    assert record.evidence_phrase == "without confirming isolation"
    assert record.evidence["activity"] == "dismantled the pressurized line"
    assert record.evidence["barrier_failure"] == "without confirming isolation"
    assert record.field_methods["barrier_failure"] == "rule"
    assert record.field_confidence["barrier_failure"] >= 0.9


def test_indirect_precursor_uses_conservative_semantic_pattern():
    record = extract_precursor(
        "Technician broke open the process pipe before proving it was isolated."
    )

    assert record.activity == "Line dismantling / piping break"
    assert record.barrier_failure == "Isolation not verified"
    assert record.hazard_exposure is None
    assert record.location is None
    assert record.field_methods["activity"] == "semantic_pattern"
    assert record.field_methods["barrier_failure"] == "semantic_pattern"
    assert "before proving it was isolated" in (record.evidence["barrier_failure"] or "")


def test_missing_location_is_never_invented_and_raw_text_is_preserved():
    report = "Technician dismantled the pressurized line without confirming isolation."
    result = process_report_text(report)
    record = result["precursor"]

    assert result["raw_text_redacted"] == report
    assert record.location is None
    assert record.evidence["location"] is None
    assert record.field_confidence["location"] == 0.0


def test_multiple_barriers_are_preserved():
    record = extract_precursor(
        "Crane lift proceeded with a damaged sling and no fire watch."
    )

    assert record.barrier_failure == "No fire watch"
    assert "Lifting barrier failed" in record.secondary_barriers
    assert record.evidence["barrier_failure"] == "no fire watch"


def test_multiple_activities_are_preserved():
    record = extract_precursor(
        "Crew welded pipe and lifted a spool with a crane; no fire watch and damaged sling."
    )

    assert record.activity == "Hot work / welding"
    assert "Mechanical lifting" in record.secondary_activities


def test_ambiguous_report_returns_unknown_fields_without_hallucination():
    record = extract_precursor("Team discussed the routine schedule before lunch.")

    assert record.activity is None
    assert record.location is None
    assert record.barrier_failure is None
    assert record.hazard_exposure is None
    assert record.relevant_lsr is None
    assert record.evidence["activity"] is None
    assert record.confidence == 0.40
    assert record.extraction_method == EXTRACTION_VERSION
