"""Tests for canonical Normalizer, DataQualityReport generation, and synthetic adapter."""

import pytest
from pathlib import Path
from ingestion.normalizer import (
    DataQualityReport,
    NormalizedIncident,
    compute_data_quality_report,
)
from ingestion.synthetic import SyntheticIngestionAdapter
from ingestion import ingest_dataset


def test_normalized_incident_serialization():
    inc = NormalizedIncident(
        report_id="TEST-001",
        source="TEST",
        date="2026-05-01",
        country="India",
        site="Duliajan GCS",
        sector="Upstream",
        activity="Wellhead maintenance",
        incident_description="Technician isolated valve and purged gas line successfully.",
        hazard="Pressurized gas",
        energy_source="Pressure",
        exposure="Line of fire",
        barrier_failure=None,
        consequence="Near miss",
        fatality=0,
        injury_severity=None,
        sif_potential=False,
        lsr="Energy Isolation",
        data_type="real",
        source_dataset="test_dataset",
        source_record_id="REC-1",
        source_url="https://example.com",
    )
    data = inc.to_dict()
    assert data["report_id"] == "TEST-001"
    assert data["data_type"] == "real"
    assert data["source_dataset"] == "test_dataset"

    # Test conversion to app report dict
    app_dict = inc.to_app_report_dict()
    assert app_dict["source_report_id"] == "TEST-001"
    assert app_dict["site_name"] == "Duliajan GCS"
    assert app_dict["report_type"] == "near_miss"


def test_data_quality_report_metrics():
    valid_rec = NormalizedIncident(
        report_id="REC-01",
        source="PHMSA",
        date="2022-01-01",
        country="USA",
        site="Site A",
        sector="Pipeline",
        activity="Pumping",
        incident_description="Detailed description of pipeline leak meeting minimum character length requirement.",
        hazard="Crude oil",
        energy_source="Pressure",
        exposure=None,
        barrier_failure="Defective flange",
        consequence="Spill",
        fatality=0,
        injury_severity=None,
        sif_potential=False,
        lsr="Asset Integrity",
        data_type="real",
    )
    dup_rec = NormalizedIncident(
        report_id="REC-01",  # Duplicate ID
        source="PHMSA",
        date="2022-01-01",
        country="USA",
        site="Site A",
        sector="Pipeline",
        activity="Pumping",
        incident_description="Duplicate record description.",
        hazard="Crude oil",
        energy_source="Pressure",
        exposure=None,
        barrier_failure=None,
        consequence="Spill",
        fatality=None,
        injury_severity=None,
        sif_potential=None,
        lsr=None,
        data_type="real",
    )
    rejected = [{"index": 3, "reason": "Missing description"}]

    report = compute_data_quality_report([valid_rec, dup_rec], rejected)
    assert isinstance(report, DataQualityReport)
    assert report.total_records == 3
    assert report.valid_records == 2
    assert report.rejected_records == 1
    assert report.duplicate_records == 1
    assert report.data_type_distribution["real"] == 2
    assert report.source_distribution["PHMSA"] == 2
    assert report.label_availability["sif_unlabeled"] == 1
    assert report.label_availability["sif_labeled_false"] == 1
    summary = report.summary_text()
    assert "HSE DATA QUALITY AUDIT REPORT" in summary
    assert "Total Records Ingested : 3" in summary


def test_synthetic_adapter_labels():
    synthetic_row = {
        "source_report_id": "DEMO-01",
        "raw_text": "Near miss: worker unclipped safety harness while on level 4 scaffolding.",
        "site_name": "Duliajan GCS",
        "report_type": "near_miss",
        "reported_at": "2026-07-01T12:00:00Z",
    }
    rec = SyntheticIngestionAdapter.normalize_record(synthetic_row)
    assert rec is not None
    assert rec.data_type == "synthetic"  # Explicitly labeled synthetic
    assert rec.source == "SYNTHETIC"
    assert rec.report_id == "SYN-DEMO-01"


def test_unified_ingest_dataset():
    root = Path(__file__).resolve().parent.parent.parent
    sample_file = root / "data" / "raw" / "phmsa" / "phmsa_pipeline_incidents_sample.csv"
    if sample_file.exists():
        records, rejected, report = ingest_dataset("phmsa", sample_file)
        assert len(records) > 0
        assert report.valid_records == len(records)
        assert report.source_distribution["PHMSA"] == len(records)
