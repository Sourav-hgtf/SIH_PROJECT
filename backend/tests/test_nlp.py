from app.nlp.classify import classify_sif, tag_life_saving_rules
from app.nlp.labeling import LABELING_FUNCTIONS, apply_labeling_functions
from app.nlp.preprocess import (
    expand_abbreviations,
    preprocess,
    redact_pii,
    _is_excluded,
)
from app.nlp.mining import assign_trend
from datetime import datetime
from unittest import mock


def test_abbreviation_expansion():
    text = "LOTO not applied and H2S possible. PTW expired."
    out = expand_abbreviations(text)
    assert "Lock-Out Tag-Out" in out
    assert "Hydrogen Sulfide" in out
    assert "Permit to Work" in out


def test_pii_redaction():
    text = "Amit Sharma (EMP-44102, +91 9876543210) reported the event."
    redacted, count = redact_pii(text)
    assert "[PERSON]" in redacted
    assert "[ID]" in redacted
    assert "[PHONE]" in redacted
    assert "Amit Sharma" not in redacted
    assert "9876543210" not in redacted
    assert count >= 3


def test_preprocess_never_keeps_raw_pii():
    result = preprocess("Call Rina Das at 9988776655 EMP-12")
    assert "Rina Das" not in result["raw_text_redacted"]
    assert "9988776655" not in result["raw_text_redacted"]


def test_at_least_five_labeling_functions():
    assert len(LABELING_FUNCTIONS) >= 5


@mock.patch("app.nlp.classify.predict_sif_probability")
def test_sif_positive_on_energy_barrier(mock_predict):
    mock_predict.return_value = (0.85, "mock-v1")
    text = (
        "Crew worked on live electrical panel. Lock-out tag-out not applied. "
        "Workers nearby in the line of fire of residual pressure."
    )
    clf = classify_sif(text)
    assert clf["sif_label"] is True
    assert clf["sif_probability"] >= 0.45
    assert clf["contributing_phrases"]


@mock.patch("app.nlp.classify.predict_sif_probability")
def test_sif_negative_on_housekeeping(mock_predict):
    mock_predict.return_value = (0.15, "mock-v1")
    text = "Poor housekeeping in workshop. Slippery floor and trip hazard. Hard hat not worn."
    clf = classify_sif(text)
    assert clf["sif_label"] is False


def test_lsr_multi_label():
    text = "Hot work welding without permit. Fire watch missing. Confined space tank entry, no gas test."
    tags = tag_life_saving_rules(text)
    names = {t["lsr_category"] for t in tags}
    assert "Hot Work" in names
    assert "Confined Space" in names or "Work Authorization" in names


def test_weak_supervision_votes():
    result = apply_labeling_functions("Dropped object on rig floor. Standing under suspended load. Crane lift.")
    assert result["positive_votes"] >= 1
    assert result["weak_label"] == 1


def test_cluster_trend_accepts_sqlite_naive_timestamps():
    assert assign_trend([datetime.now()]) in {"growing", "stable", "shrinking"}


# ===========================================================================
# Comprehensive PII Detection Tests
# ===========================================================================

class TestPIITruePositives:
    """Verify that genuine person names ARE redacted."""

    def test_two_word_indian_name(self):
        text = "Amit Sharma reported the near miss."
        redacted, count = redact_pii(text)
        assert "Amit Sharma" not in redacted
        assert "[PERSON]" in redacted
        assert count >= 1

    def test_two_word_name_rina_das(self):
        text = "Rina Das was the permit receiver."
        redacted, count = redact_pii(text)
        assert "Rina Das" not in redacted
        assert "[PERSON]" in redacted

    def test_three_word_name(self):
        text = "Rahul Verma Singh signed off on the PTW."
        redacted, count = redact_pii(text)
        assert "Rahul Verma Singh" not in redacted
        assert "[PERSON]" in redacted

    def test_name_with_context_clues(self):
        """Name preceded by 'Mr.' should be detected by NER."""
        text = "Mr. Priya Mehta witnessed the incident."
        redacted, count = redact_pii(text)
        assert "Priya Mehta" not in redacted

    def test_name_in_mixed_report(self):
        text = (
            "Suresh Kumar (EMP-00451) entered the confined space without PTW. "
            "Safety Officer on duty was unavailable."
        )
        redacted, count = redact_pii(text)
        assert "Suresh Kumar" not in redacted
        assert "[PERSON]" in redacted
        assert "[ID]" in redacted
        # Safety Officer must NOT be redacted
        assert "Safety Officer" in redacted or "safety officer" in redacted.lower()


class TestPIIFalsePositiveSuppression:
    """Verify that non-person phrases are NOT mistakenly redacted."""

    def test_job_title_safety_officer(self):
        text = "The Safety Officer conducted the site inspection."
        redacted, count = redact_pii(text)
        assert "Safety Officer" in redacted, (
            f"Safety Officer was incorrectly redacted. Got: {redacted!r}"
        )

    def test_job_title_production_engineer(self):
        text = "Production Engineer approved the MOC."
        redacted, count = redact_pii(text)
        assert "Production Engineer" in redacted, (
            f"Production Engineer was incorrectly redacted. Got: {redacted!r}"
        )

    def test_job_title_mechanical_supervisor(self):
        text = "Mechanical Supervisor was not informed before isolation."
        redacted, count = redact_pii(text)
        assert "Mechanical Supervisor" in redacted, (
            f"Mechanical Supervisor was incorrectly redacted. Got: {redacted!r}"
        )

    def test_chemical_name_hydrogen_sulfide(self):
        text = "Hydrogen Sulfide levels exceeded 10 ppm in the pit."
        redacted, count = redact_pii(text)
        assert "Hydrogen Sulfide" in redacted, (
            f"Hydrogen Sulfide was incorrectly redacted. Got: {redacted!r}"
        )

    def test_chemical_name_carbon_monoxide(self):
        text = "Carbon Monoxide was detected inside the vessel."
        redacted, count = redact_pii(text)
        assert "Carbon Monoxide" in redacted, (
            f"Carbon Monoxide was incorrectly redacted. Got: {redacted!r}"
        )

    def test_equipment_blowout_preventer(self):
        text = "The Blowout Preventer was not tested before drilling began."
        redacted, count = redact_pii(text)
        assert "Blowout Preventer" in redacted, (
            f"Blowout Preventer was incorrectly redacted. Got: {redacted!r}"
        )

    def test_document_permit_work(self):
        text = "Permit Work was not completed before excavation started."
        redacted, _ = redact_pii(text)
        assert "Permit Work" in redacted

    def test_no_false_positive_count(self):
        """A text with only job titles and chemical names should have zero PII replacements."""
        text = (
            "Safety Officer, Mechanical Supervisor, and Production Engineer "
            "discussed Hydrogen Sulfide exposure risks."
        )
        redacted, count = redact_pii(text)
        # count should be 0 – no real PII
        assert count == 0, f"Expected 0 PII hits, got {count}. Redacted: {redacted!r}"

    def test_exclusion_helper_job_titles(self):
        assert _is_excluded("Safety Officer") is True
        assert _is_excluded("Mechanical Supervisor") is True
        assert _is_excluded("Production Engineer") is True
        assert _is_excluded("Hydrogen Sulfide") is True

    def test_exclusion_helper_real_names(self):
        assert _is_excluded("Amit Sharma") is False
        assert _is_excluded("Rina Das") is False
        assert _is_excluded("Rahul Verma") is False


class TestPIIEmails:
    """Verify email addresses are redacted."""

    def test_simple_email(self):
        text = "Send the report to worker@example.com for review."
        redacted, count = redact_pii(text)
        assert "worker@example.com" not in redacted
        assert "[EMAIL]" in redacted
        assert count >= 1

    def test_email_with_dots_in_local(self):
        text = "Contact john.doe.hsse@oilcorp.co.in immediately."
        redacted, count = redact_pii(text)
        assert "john.doe.hsse@oilcorp.co.in" not in redacted
        assert "[EMAIL]" in redacted

    def test_email_is_not_treated_as_person(self):
        text = "Send alert to site.manager@platform.com and log EMP-123."
        redacted, _ = redact_pii(text)
        assert "[EMAIL]" in redacted
        assert "[ID]" in redacted


class TestPIIPhoneNumbers:
    """Verify phone numbers are redacted."""

    def test_indian_10_digit(self):
        text = "Worker's number is 9988776655."
        redacted, count = redact_pii(text)
        assert "9988776655" not in redacted
        assert "[PHONE]" in redacted

    def test_indian_plus91_with_space(self):
        text = "Call +91 9876543210 for emergency."
        redacted, count = redact_pii(text)
        assert "9876543210" not in redacted
        assert "[PHONE]" in redacted

    def test_us_style_dashes(self):
        text = "Contact safety line at 555-123-4567."
        redacted, count = redact_pii(text)
        assert "555-123-4567" not in redacted
        assert "[PHONE]" in redacted

    def test_us_style_dots(self):
        text = "Supervisor reachable at 800.555.1234."
        redacted, count = redact_pii(text)
        assert "800.555.1234" not in redacted
        assert "[PHONE]" in redacted


class TestPIIEmployeeIDs:
    """Verify employee IDs are redacted."""

    def test_emp_dash_format(self):
        text = "EMP-44102 was involved in the incident."
        redacted, count = redact_pii(text)
        assert "EMP-44102" not in redacted
        assert "[ID]" in redacted

    def test_emp_no_dash(self):
        text = "Employee EMP123456 filed the report."
        redacted, count = redact_pii(text)
        assert "EMP123456" not in redacted
        assert "[ID]" in redacted

    def test_oilid_format(self):
        text = "OILID: 78901234 was on site."
        redacted, count = redact_pii(text)
        assert "78901234" not in redacted
        assert "[ID]" in redacted

    def test_empid_format(self):
        text = "Logged under EMPID-9900112."
        redacted, count = redact_pii(text)
        assert "[ID]" in redacted


class TestPIIMixedReports:
    """End-to-end tests on realistic safety report paragraphs."""

    def test_full_report_with_person_phone_id(self):
        text = (
            "Suresh Kumar (EMP-00451, +91 9823456789) reported that the "
            "Safety Officer had not issued a PTW before the confined space entry. "
            "Mechanical Supervisor was alerted at 10:30. "
            "Contact: suresh.k@oilsite.in"
        )
        redacted, count = redact_pii(text)
        # PII must be gone
        assert "Suresh Kumar" not in redacted
        assert "9823456789" not in redacted
        assert "suresh.k@oilsite.in" not in redacted
        assert "EMP-00451" not in redacted
        # Job titles must survive
        assert "Safety Officer" in redacted
        assert "Mechanical Supervisor" in redacted
        assert count >= 4

    def test_report_without_names_not_over_redacted(self):
        """A report with no names should produce zero PERSON redactions."""
        text = (
            "Production Engineer found that the Hydrogen Sulfide alarm was inhibited. "
            "Blowout Preventer test was overdue. Safety Supervisor raised the concern."
        )
        redacted, count = redact_pii(text)
        assert "[PERSON]" not in redacted, (
            f"False positive PERSON redaction. Got: {redacted!r}"
        )

    def test_preprocess_output_keys_preserved(self):
        """Ensure preprocess() output structure is backward-compatible."""
        result = preprocess("Amit Sharma (EMP-1234) entered the tank.")
        assert "raw_text_redacted" in result
        assert "processed_text" in result
        assert "pii_replacements" in result
        assert "Amit Sharma" not in result["raw_text_redacted"]
        assert result["pii_replacements"] >= 2

    def test_preprocess_preserves_safety_terms(self):
        """Abbreviation expansion and spell-correction still work after PII redaction."""
        result = preprocess("LOTO not applied. H2S detected. Production Engineer alerted.")
        processed = result["processed_text"]
        assert "Lock-Out Tag-Out" in processed
        assert "Hydrogen Sulfide" in processed
        assert "Production Engineer" in processed
