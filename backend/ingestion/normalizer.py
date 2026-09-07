"""Canonical normalization schema, data quality reporting, and base adapter interfaces.

Defines the unified incident representation for multi-source ingestion (PHMSA, CER, OISD, OSHA,
and synthetic demo data). Adheres strictly to the principle of never inventing missing values,
tracking complete data provenance, and distinguishing real public data from synthetic demo data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def utcnow_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class NormalizedIncident:
    """Canonical HSE incident/report record conforming to enterprise safety schema."""

    # Core Identifiers and Source
    report_id: str
    source: str  # e.g., "PHMSA", "CER", "OISD", "OSHA", "SYNTHETIC"

    # Temporal & Geographical
    date: str | None  # ISO 8601 YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS, or None if missing
    country: str | None
    site: str | None
    sector: str | None  # e.g., "Pipeline - Hazardous Liquids", "Drilling", "Refining"

    # Context & Narrative
    activity: str | None  # Operational task or work type
    incident_description: str  # Primary factual narrative
    hazard: str | None  # Primary hazard involved
    energy_source: str | None  # Identified energy type (pressure, electrical, etc.)
    exposure: str | None  # Exposure mechanism (inhalation, line of fire, etc.)
    barrier_failure: str | None  # Primary barrier or control breakdown

    # Consequence & Safety Outcomes
    consequence: str | None  # Loss of containment, fire, explosion, injury
    fatality: int | None  # Count of confirmed fatalities, or None if unknown
    injury_severity: str | None  # "FATALITY", "HOSPITALIZED", "NON_HOSPITALIZED", "FIRST_AID", None
    sif_potential: bool | None  # Documented actual/high-potential SIF; None if unlabelled/unknown
    lsr: str | None  # Life-Saving Rule category if explicitly classified, else None
    precursor: dict[str, Any] | None = None  # Precursor signals or extracted triple

    # Provenance Tracking (Auditable lineage)
    source_dataset: str = ""
    source_record_id: str = ""
    source_url: str = ""
    dataset_version: str = "1.0"
    ingestion_timestamp: str = field(default_factory=utcnow_iso)

    # Data Type Distinction (Strict separation of real vs synthetic)
    data_type: str = "real"  # Strictly "real" or "synthetic"

    # Supplementary Metadata (Retains unmapped raw attributes without polluting canonical fields)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert normalized incident to a clean JSON-serializable dictionary."""
        return asdict(self)

    def to_app_report_dict(self, default_site_name: str = "Central Facility") -> dict[str, Any]:
        """Map canonical incident to backend Report schema dict for ingestion."""
        rep_date = self.date or utcnow_iso()
        return {
            "source_report_id": self.report_id,
            "report_type": "incident" if (self.fatality or self.injury_severity) else "near_miss",
            "site_name": self.site or default_site_name,
            "department": self.sector or "Operations",
            "shift": "Day",
            "equipment_type": self.hazard or "Industrial Asset",
            "job_type": self.activity or "Operational Work",
            "reported_at": rep_date,
            "raw_text": self.incident_description,
            "data_type": self.data_type,
            "source_dataset": self.source_dataset,
            "country": self.country,
        }


@dataclass
class DataQualityReport:
    """Comprehensive data-quality assessment generated after ingestion/normalization."""

    total_records: int = 0
    valid_records: int = 0
    rejected_records: int = 0
    missing_descriptions: int = 0
    missing_dates: int = 0
    duplicate_records: int = 0
    source_distribution: dict[str, int] = field(default_factory=dict)
    label_availability: dict[str, int] = field(default_factory=dict)
    data_type_distribution: dict[str, int] = field(default_factory=dict)
    completeness_percentages: dict[str, float] = field(default_factory=dict)
    rejection_reasons: dict[str, int] = field(default_factory=dict)
    data_quality_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary_text(self) -> str:
        """Produce a formatted human-readable summary of the data quality report."""
        lines = [
            "=" * 64,
            "HSE DATA QUALITY AUDIT REPORT",
            "=" * 64,
            f"Total Records Ingested : {self.total_records}",
            f"Valid Records Accepted : {self.valid_records} ({round(self.valid_records / max(1, self.total_records) * 100, 1)}%)",
            f"Rejected Records       : {self.rejected_records} ({round(self.rejected_records / max(1, self.total_records) * 100, 1)}%)",
            f"Duplicate Records      : {self.duplicate_records}",
            f"Missing Descriptions   : {self.missing_descriptions}",
            f"Missing Dates          : {self.missing_dates}",
            f"Data Quality Score     : {self.data_quality_score}/100",
            "-" * 64,
            "Source Distribution:",
        ]
        for src, cnt in self.source_distribution.items():
            lines.append(f"  • {src}: {cnt} records")
        lines.append("Data Type Separation:")
        for dtype, cnt in self.data_type_distribution.items():
            lines.append(f"  • {dtype}: {cnt} records")
        lines.append("Label Availability:")
        for lbl, cnt in self.label_availability.items():
            lines.append(f"  • {lbl}: {cnt}")
        if self.rejection_reasons:
            lines.append("Rejection Reasons:")
            for reason, cnt in self.rejection_reasons.items():
                lines.append(f"  • {reason}: {cnt}")
        lines.append("=" * 64)
        return "\n".join(lines)


class IncidentNormalizer:
    """Base helper for cleaning, sanitizing, and validating incident data."""

    @staticmethod
    def clean_text(val: Any) -> str:
        """Sanitize raw text string, collapsing erratic whitespace and removing control chars."""
        if val is None:
            return ""
        s = str(val).strip()
        s = re.sub(r"[\r\n\t]+", " ", s)
        s = re.sub(r"\s{2,}", " ", s)
        return s.strip()

    @staticmethod
    def parse_optional_date(val: Any) -> str | None:
        """Parse varied date formats into ISO 8601 string without inventing missing values."""
        if not val:
            return None
        s = str(val).strip()
        if not s or s.lower() in ("null", "none", "nan", "unknown", "n/a", ""):
            return None

        # Common datetime formats in public reports
        formats = [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%m/%d/%Y %H:%M:%S %p",
            "%m/%d/%Y %H:%M",
            "%m/%d/%Y",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%Y/%m/%d",
            "%d-%b-%Y",
            "%d-%b-%y",
            "%b %d, %Y",
        ]
        for fmt in formats:
            try:
                # Strip trailing microseconds or Z for standard strptime
                clean_s = s.replace("Z", "+00:00") if "T" in s and s.endswith("Z") else s
                if "+" in clean_s or "-" in clean_s[10:]:
                    # Has timezone offset
                    dt = datetime.fromisoformat(clean_s)
                    return dt.date().isoformat()
                dt = datetime.strptime(s, fmt)
                return dt.date().isoformat()
            except Exception:
                continue

        # ISO date prefix match (e.g., 2021-05-14 ...)
        iso_match = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
        if iso_match:
            return iso_match.group(1)

        return None

    @staticmethod
    def parse_int_optional(val: Any) -> int | None:
        """Safely parse integer count, returning None if absent or invalid."""
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return int(val)
        s = str(val).strip()
        if not s or s.lower() in ("null", "none", "nan", "unknown", "n/a", ""):
            return None
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def parse_str_optional(val: Any) -> str | None:
        """Return non-empty string or None."""
        if val is None:
            return None
        s = str(val).strip()
        if not s or s.lower() in ("null", "none", "nan", "unknown", "n/a", ""):
            return None
        return s


def compute_data_quality_report(
    records: list[NormalizedIncident | dict[str, Any]],
    rejected: list[dict[str, Any]] | None = None,
) -> DataQualityReport:
    """Compute strict data quality metrics over a collection of normalized records."""
    rejected_list = rejected or []
    total = len(records) + len(rejected_list)
    valid_count = 0
    missing_desc = 0
    missing_dates = 0
    seen_ids: set[str] = set()
    duplicates = 0

    sources: dict[str, int] = {}
    data_types: dict[str, int] = {}
    label_stats: dict[str, int] = {
        "sif_labeled_true": 0,
        "sif_labeled_false": 0,
        "sif_unlabeled": 0,
        "fatalities_recorded": 0,
        "injuries_recorded": 0,
        "lsr_mapped": 0,
    }
    field_counts: dict[str, int] = {
        "report_id": 0,
        "incident_description": 0,
        "date": 0,
        "site": 0,
        "sector": 0,
        "activity": 0,
        "hazard": 0,
        "barrier_failure": 0,
        "consequence": 0,
    }
    rejection_reasons: dict[str, int] = {}

    for rej in rejected_list:
        reason = rej.get("reason", "Validation failed")
        rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1

    for item in records:
        rec = item if isinstance(item, NormalizedIncident) else NormalizedIncident(**item)

        # Check description
        desc = rec.incident_description
        if not desc or len(desc.strip()) < 10:
            missing_desc += 1
        else:
            field_counts["incident_description"] += 1

        # Check date
        if not rec.date:
            missing_dates += 1
        else:
            field_counts["date"] += 1

        # Check duplicate
        if rec.report_id:
            field_counts["report_id"] += 1
            if rec.report_id in seen_ids:
                duplicates += 1
            seen_ids.add(rec.report_id)

        # Track sources & data types
        src = rec.source or "UNKNOWN"
        sources[src] = sources.get(src, 0) + 1
        dtype = rec.data_type or "unknown"
        data_types[dtype] = data_types.get(dtype, 0) + 1

        # Track optional fields
        if rec.site:
            field_counts["site"] += 1
        if rec.sector:
            field_counts["sector"] += 1
        if rec.activity:
            field_counts["activity"] += 1
        if rec.hazard:
            field_counts["hazard"] += 1
        if rec.barrier_failure:
            field_counts["barrier_failure"] += 1
        if rec.consequence:
            field_counts["consequence"] += 1

        # Track label availability
        if rec.sif_potential is True:
            label_stats["sif_labeled_true"] += 1
        elif rec.sif_potential is False:
            label_stats["sif_labeled_false"] += 1
        else:
            label_stats["sif_unlabeled"] += 1

        if rec.fatality is not None and rec.fatality > 0:
            label_stats["fatalities_recorded"] += 1
        if rec.injury_severity:
            label_stats["injuries_recorded"] += 1
        if rec.lsr:
            label_stats["lsr_mapped"] += 1

        valid_count += 1

    # Completeness percentages
    n_valid = max(1, valid_count)
    completeness = {k: round((v / n_valid) * 100.0, 1) for k, v in field_counts.items()}

    # Data Quality Score calculation (0 - 100)
    # 40% description, 20% date, 20% contextual attributes, 20% uniqueness & validity
    score_desc = (field_counts["incident_description"] / max(1, total)) * 40.0
    score_date = (field_counts["date"] / max(1, total)) * 20.0
    score_context = (
        (field_counts["site"] + field_counts["sector"] + field_counts["activity"] + field_counts["hazard"])
        / (max(1, total) * 4.0)
    ) * 20.0
    dup_penalty = (duplicates / max(1, total)) * 10.0
    rej_penalty = (len(rejected_list) / max(1, total)) * 10.0
    dq_score = max(0.0, min(100.0, round(score_desc + score_date + score_context + (20.0 - dup_penalty - rej_penalty), 1)))

    return DataQualityReport(
        total_records=total,
        valid_records=valid_count,
        rejected_records=len(rejected_list),
        missing_descriptions=missing_desc,
        missing_dates=missing_dates,
        duplicate_records=duplicates,
        source_distribution=sources,
        label_availability=label_stats,
        data_type_distribution=data_types,
        completeness_percentages=completeness,
        rejection_reasons=rejection_reasons,
        data_quality_score=dq_score,
    )
