from app.nlp.classify import classify_sif, tag_life_saving_rules
from app.nlp.labeling import LABELING_FUNCTIONS, apply_labeling_functions
from app.nlp.preprocess import expand_abbreviations, preprocess, redact_pii
from app.nlp.mining import assign_trend
from datetime import datetime


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


from unittest import mock

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
