"""Re-export backend.ingestion package for app namespace compatibility."""

from ingestion import (
    CERIngestionAdapter,
    DataQualityReport,
    IncidentNormalizer,
    NormalizedIncident,
    OISDIngestionAdapter,
    OSHAIngestionAdapter,
    PHMSAIngestionAdapter,
    compute_data_quality_report,
    ingest_dataset,
)

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
