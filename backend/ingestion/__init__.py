"""Enterprise Ingestion Package for Public and Synthetic HSE Incident Datasets.

Exposes source-specific ingestion adapters for:
- PHMSA (US Pipeline and Hazardous Materials Safety Administration)
- CER (Canada Energy Regulator)
- OISD (Oil Industry Safety Directorate, India)
- OSHA (Severe Injury Reports, Oil & Gas Sector)
- Synthetic Demo Data Normalizer
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ingestion.cer import CERIngestionAdapter
from ingestion.normalizer import (
    DataQualityReport,
    IncidentNormalizer,
    NormalizedIncident,
    compute_data_quality_report,
)
from ingestion.oisd import OISDIngestionAdapter
from ingestion.osha import OSHAIngestionAdapter
from ingestion.phmsa import PHMSAIngestionAdapter

__all__ = [
    "NormalizedIncident",
    "IncidentNormalizer",
    "DataQualityReport",
    "compute_data_quality_report",
    "PHMSAIngestionAdapter",
    "CERIngestionAdapter",
    "OISDIngestionAdapter",
    "OSHAIngestionAdapter",
    "ingest_dataset",
]


def ingest_dataset(
    source_type: str,
    file_path: str | Path,
    filter_oil_gas: bool = True,
) -> tuple[list[NormalizedIncident], list[dict[str, Any]], DataQualityReport]:
    """Unified ingestion entry point for any supported public or synthetic HSE dataset.

    Parameters
    ----------
    source_type : str
        One of 'phmsa', 'cer', 'oisd', 'osha', or 'synthetic'.
    file_path : str | Path
        Path to raw CSV or JSON file.
    filter_oil_gas : bool
        Applies oil & gas sector filtering (primarily for OSHA reports).

    Returns
    -------
    tuple[list[NormalizedIncident], list[dict], DataQualityReport]
        Normalized records, rejected raw records, and comprehensive data-quality report.
    """
    src = source_type.strip().lower()
    if src == "phmsa":
        records, rejected = PHMSAIngestionAdapter.ingest_file(file_path)
    elif src == "cer":
        records, rejected = CERIngestionAdapter.ingest_file(file_path)
    elif src == "oisd":
        records, rejected = OISDIngestionAdapter.ingest_file(file_path)
    elif src == "osha":
        records, rejected = OSHAIngestionAdapter.ingest_file(file_path, filter_oil_gas=filter_oil_gas)
    elif src in ("synthetic", "demo"):
        from ingestion.synthetic import SyntheticIngestionAdapter
        records, rejected = SyntheticIngestionAdapter.ingest_file(file_path)
    else:
        raise ValueError(f"Unsupported source type '{source_type}'. Supported: phmsa, cer, oisd, osha, synthetic")

    report = compute_data_quality_report(records, rejected)
    return records, rejected, report
