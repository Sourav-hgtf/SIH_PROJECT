"""Tests for CER pipeline incident ingestion and normalization adapter."""

import pytest
from pathlib import Path
from ingestion.cer import CERIngestionAdapter
from ingestion.normalizer import NormalizedIncident

SAMPLE_CER_ROW = {
    "Incident Number": "INC2021-099",
    "Incident Date": "2021-08-10",
    "Company": "Trans Mountain Pipeline ULC",
    "Pipeline Name": "Trans Mountain Mainline",
    "Province": "British Columbia",
    "Substance": "Crude Oil",
    "Activity at time of incident": "Operation",
    "What happened narrative": "Flange leak occurred on booster pump discharge header. Approximately 1.5 cubic meters collected in sump.",
    "Primary Cause": "Defect and Deterioration",
    "Adverse Effects": "Product release contained on site",
    "Significant": "No",
    "Fatalities": "0",
    "Serious Injuries": "0",
}


def test_cer_normalize_record():
    incident = CERIngestionAdapter.normalize_record(SAMPLE_CER_ROW)
    assert isinstance(incident, NormalizedIncident)
    assert incident.report_id == "CER-INC2021-099"
    assert incident.source == "CER"
    assert incident.country == "Canada"
    assert incident.data_type == "real"
    assert "Trans Mountain" in incident.site
    assert incident.date == "2021-08-10"
    assert incident.fatality == 0
    assert incident.injury_severity is None
    assert incident.sif_potential is False
    assert incident.source_dataset == "cer_pipeline_incidents"


def test_cer_significant_incident():
    sig_row = dict(SAMPLE_CER_ROW)
    sig_row["Incident Number"] = "INC2021-100"
    sig_row["Significant"] = "Yes"
    sig_row["Serious Injuries"] = "1"
    incident = CERIngestionAdapter.normalize_record(sig_row)
    assert incident.sif_potential is True
    assert incident.injury_severity == "HOSPITALIZED"


def test_cer_missing_fields_never_invented():
    minimal_row = {
        "Incident Number": "INC2022-001",
        "What happened narrative": "Pipeline pressure anomaly detected by automated SCADA system.",
    }
    incident = CERIngestionAdapter.normalize_record(minimal_row)
    assert incident.report_id == "CER-INC2022-001"
    assert incident.date is None
    assert incident.site is None
    assert incident.fatality is None
    assert incident.sif_potential is None


def test_cer_ingest_sample_file():
    root = Path(__file__).resolve().parent.parent.parent
    sample_file = root / "data" / "raw" / "cer" / "cer_pipeline_incidents_sample.csv"
    if sample_file.exists():
        records, rejected = CERIngestionAdapter.ingest_file(sample_file)
        assert len(records) >= 5
        assert len(rejected) == 0
        for r in records:
            assert r.data_type == "real"
            assert r.country == "Canada"
            assert r.report_id.startswith("CER-")
