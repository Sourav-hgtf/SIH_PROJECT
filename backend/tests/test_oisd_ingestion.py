"""Tests for OISD (India) incident ingestion and normalization adapter."""

import pytest
from pathlib import Path
from ingestion.oisd import OISDIngestionAdapter
from ingestion.normalizer import NormalizedIncident

SAMPLE_OISD_ROW = {
    "Incident No": "OISD-CS-2021-99",
    "Date of Occurrence": "2021-05-12",
    "Organization": "Oil India Limited",
    "Installation / Unit": "Duliajan GCS",
    "State / Region": "Assam",
    "Sector": "Upstream - Exploration & Production",
    "Activity Underway": "Wellhead line servicing",
    "Description of Incident": "Technician removed flange bolts while line had residual pressure. Released liquid hydrocarbon spray.",
    "Hazard Type": "High Pressure Hydrocarbon",
    "Energy Source": "Pressure Energy",
    "Barrier Failure": "Failure to depressurize before breaking containment",
    "Consequence": "Near miss spray incident",
    "Fatalities": 0,
    "Injuries": 0,
    "SIF Potential": "True",
    "Life Saving Rule Violated": "Energy Isolation & Line of Fire",
    "OISD Standard": "OISD-STD-105",
}


def test_oisd_normalize_record():
    incident = OISDIngestionAdapter.normalize_record(SAMPLE_OISD_ROW)
    assert isinstance(incident, NormalizedIncident)
    assert incident.report_id == "OISD-OISD-CS-2021-99"
    assert incident.source == "OISD"
    assert incident.country == "India"
    assert incident.data_type == "real"
    assert "Duliajan" in incident.site
    assert incident.date == "2021-05-12"
    assert incident.fatality == 0
    assert incident.sif_potential is True
    assert incident.lsr == "Energy Isolation"
    assert incident.source_dataset == "oisd_safety_reports"


def test_oisd_casualty_mapping():
    casualty_row = dict(SAMPLE_OISD_ROW)
    casualty_row["Incident No"] = "OISD-FATAL-01"
    casualty_row["Fatalities"] = 1
    casualty_row["Injuries"] = 2
    incident = OISDIngestionAdapter.normalize_record(casualty_row)
    assert incident.fatality == 1
    assert incident.injury_severity == "FATALITY"
    assert incident.sif_potential is True


def test_oisd_missing_fields():
    minimal_row = {
        "Incident No": "OISD-ALERT-2022",
        "Description of Incident": "Safety alert issued regarding electrical switchgear grounding deficiencies.",
    }
    incident = OISDIngestionAdapter.normalize_record(minimal_row)
    assert incident.report_id == "OISD-OISD-ALERT-2022"
    assert incident.date is None
    assert incident.site is None
    assert incident.fatality is None
    assert incident.sif_potential is None


def test_oisd_ingest_sample_file():
    root = Path(__file__).resolve().parent.parent.parent
    sample_file = root / "data" / "raw" / "oisd" / "oisd_incident_reports_sample.json"
    if sample_file.exists():
        records, rejected = OISDIngestionAdapter.ingest_file(sample_file)
        assert len(records) >= 5
        assert len(rejected) == 0
        for r in records:
            assert r.data_type == "real"
            assert r.country == "India"
            assert r.source == "OISD"
