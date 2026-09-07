"""Tests for PHMSA pipeline incident ingestion and normalization adapter."""

import pytest
from pathlib import Path
from ingestion.phmsa import PHMSAIngestionAdapter
from ingestion.normalizer import NormalizedIncident

SAMPLE_PHMSA_ROW = {
    "REPORT_NUMBER": "20210042",
    "LOCAL_DATETIME": "2021-04-15 10:30:00",
    "OPERATOR_NAME": "COLONIAL PIPELINE CO",
    "LOCATION_CITY_NAME": "PELHAM",
    "LOCATION_STATE_ABBREVIATION": "AL",
    "COMMODITY_RELEASED_TYPE": "REFINED PRODUCT",
    "SYSTEM_TYPE": "HAZARDOUS LIQUID",
    "SYSTEM_PART_INVOLVED": "LINE PIPE",
    "CAUSE": "CORROSION",
    "SUBCAUSE": "EXTERNAL CORROSION",
    "IGNITE_IND": "NO",
    "EXPLODE_IND": "NO",
    "UNINTENTIONAL_RELEASE_BBLS": "12.5",
    "NUM_FATALITIES": "0",
    "NUM_INJURIES": "0",
    "NARRATIVE": "A localized external corrosion defect resulted in a pinhole leak on 36-inch pipeline. Repaired with full encirclement clamp.",
}


def test_phmsa_normalize_record():
    incident = PHMSAIngestionAdapter.normalize_record(SAMPLE_PHMSA_ROW)
    assert isinstance(incident, NormalizedIncident)
    assert incident.report_id == "PHMSA-20210042"
    assert incident.source == "PHMSA"
    assert incident.country == "USA"
    assert incident.data_type == "real"
    assert "COLONIAL PIPELINE" in incident.site
    assert incident.date == "2021-04-15"
    assert incident.fatality == 0
    assert incident.injury_severity is None
    assert incident.sif_potential is False
    assert incident.source_dataset == "phmsa_pipeline_incidents"
    assert incident.source_record_id == "20210042"


def test_phmsa_severe_consequence():
    severe_row = dict(SAMPLE_PHMSA_ROW)
    severe_row["REPORT_NUMBER"] = "20210099"
    severe_row["NUM_FATALITIES"] = "1"
    severe_row["NUM_INJURIES"] = "2"
    severe_row["IGNITE_IND"] = "YES"
    severe_row["EXPLODE_IND"] = "YES"
    incident = PHMSAIngestionAdapter.normalize_record(severe_row)
    assert incident.fatality == 1
    assert incident.injury_severity == "FATALITY"
    assert incident.sif_potential is True
    assert "Explosion" in incident.consequence
    assert "Fire" in incident.consequence


def test_phmsa_missing_fields_never_invented():
    minimal_row = {
        "REPORT_NUMBER": "20219999",
        "NARRATIVE": "Unknown pressure surge caused pipe rupture during routine test.",
    }
    incident = PHMSAIngestionAdapter.normalize_record(minimal_row)
    assert incident.report_id == "PHMSA-20219999"
    assert incident.date is None
    assert incident.site is None
    assert incident.fatality is None
    assert incident.injury_severity is None
    assert incident.sif_potential is None  # Never fabricated


def test_phmsa_ingest_sample_file():
    root = Path(__file__).resolve().parent.parent.parent
    sample_file = root / "data" / "raw" / "phmsa" / "phmsa_pipeline_incidents_sample.csv"
    if sample_file.exists():
        records, rejected = PHMSAIngestionAdapter.ingest_file(sample_file)
        assert len(records) >= 5
        assert len(rejected) == 0
        for r in records:
            assert r.data_type == "real"
            assert r.source == "PHMSA"
            assert r.report_id.startswith("PHMSA-")
