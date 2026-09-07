"""Tests for OSHA severe injury ingestion and normalization adapter."""

import pytest
from pathlib import Path
from ingestion.osha import OSHAIngestionAdapter
from ingestion.normalizer import NormalizedIncident

SAMPLE_OSHA_ROW = {
    "ID": "2021090123",
    "Incident Date": "09/03/2021",
    "Employer": "PLAINS ALL AMERICAN PIPELINE LP",
    "Address": "ROUTE 3 SOUTH",
    "City": "CUSHING",
    "State": "OK",
    "Zip": "74023",
    "NAICS": "486110",
    "Hospitalized": "1",
    "Amputation": "1",
    "EventTitle": "Caught in pinch point between objects",
    "SourceTitle": "Motor operated valve actuator",
    "NatureTitle": "Traumatic amputation",
    "PartTitle": "Hand",
    "Final Narrative": "A pipeline maintenance technician was troubleshooting an electric motor-operated valve actuator. Two fingers were amputated when the unit cycled.",
}


def test_osha_normalize_record():
    incident = OSHAIngestionAdapter.normalize_record(SAMPLE_OSHA_ROW)
    assert isinstance(incident, NormalizedIncident)
    assert incident.report_id == "OSHA-2021090123"
    assert incident.source == "OSHA"
    assert incident.country == "USA"
    assert incident.data_type == "real"
    assert "PLAINS ALL AMERICAN" in incident.site
    assert incident.date == "2021-09-03"
    assert incident.sif_potential is True
    assert incident.injury_severity in ("HOSPITALIZED", "AMPUTATION")
    assert incident.lsr == "Line of Fire"
    assert incident.sector == "Midstream - Pipeline Transportation"
    assert incident.source_dataset == "osha_severe_injury_reports"


def test_osha_oil_gas_filtering():
    non_oil_gas_row = {
        "ID": "999999",
        "NAICS": "722511",  # Full-Service Restaurants
        "EMPLOYER": "JOE PIZZA",
        "FINAL NARRATIVE": "Cook slipped on wet kitchen floor and fractured wrist.",
    }
    assert OSHAIngestionAdapter.is_oil_gas_record(non_oil_gas_row) is False
    assert OSHAIngestionAdapter.normalize_record(non_oil_gas_row, filter_oil_gas=True) is None

    oil_gas_row = {
        "ID": "888888",
        "NAICS": "213111",  # Drilling Oil & Gas Wells
        "EMPLOYER": "RIG SERVICES LLC",
        "FINAL NARRATIVE": "Roughneck hand caught in spinning chain during connection.",
    }
    assert OSHAIngestionAdapter.is_oil_gas_record(oil_gas_row) is True
    normalized = OSHAIngestionAdapter.normalize_record(oil_gas_row, filter_oil_gas=True)
    assert normalized is not None
    assert normalized.report_id == "OSHA-888888"


def test_osha_ingest_sample_file():
    root = Path(__file__).resolve().parent.parent.parent
    sample_file = root / "data" / "raw" / "osha" / "osha_oil_gas_severe_injuries_sample.csv"
    if sample_file.exists():
        records, rejected = OSHAIngestionAdapter.ingest_file(sample_file, filter_oil_gas=True)
        assert len(records) >= 5
        assert len(rejected) == 0
        for r in records:
            assert r.data_type == "real"
            assert r.source == "OSHA"
            assert r.country == "USA"
            assert r.sif_potential is True
