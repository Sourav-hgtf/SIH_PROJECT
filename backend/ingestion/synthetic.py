"""Synthetic and Demo Data Ingestion and Normalization Module.

Explicitly labels all generated or simulated demo records with `data_type = 'synthetic'`.
Enforces full separation between real public safety incident datasets and synthetic testing data.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from pathlib import Path
from typing import Any

from ingestion.normalizer import IncidentNormalizer, NormalizedIncident

logger = logging.getLogger(__name__)

SYNTHETIC_SOURCE_URL = "internal://synthetic/demo-seed"
SYNTHETIC_DATASET_VERSION = "synthetic_demo_v1"


class SyntheticIngestionAdapter(IncidentNormalizer):
    """Adapter for ingesting and validating synthetic/demo incident records."""

    @classmethod
    def normalize_record(cls, raw: dict[str, Any]) -> NormalizedIncident | None:
        """Normalize a synthetic record into canonical NormalizedIncident schema."""
        r = {str(k).strip(): v for k, v in raw.items() if k is not None}
        r_lower = {str(k).strip().lower().replace(" ", "_"): v for k, v in raw.items() if k is not None}

        # 1. Report ID
        raw_id = (
            r.get("source_report_id")
            or r_lower.get("source_report_id")
            or r.get("report_id")
            or r_lower.get("report_id")
            or r.get("id")
        )
        if not raw_id:
            return None
        source_id = str(raw_id).strip()
        report_id = source_id if source_id.startswith("SYN-") else f"SYN-{source_id}"

        # 2. Date
        raw_date = (
            r.get("reported_at")
            or r_lower.get("reported_at")
            or r.get("date")
            or r_lower.get("date")
        )
        date_iso = cls.parse_optional_date(raw_date)

        # 3. Geography & Facility
        site = cls.clean_text(r.get("site_name") or r_lower.get("site_name") or r.get("site") or "Duliajan GCS")

        # 4. Department & Sector
        dept = cls.clean_text(r.get("department") or r_lower.get("department") or "Operations")
        sector = f"Upstream Oil & Gas - {dept}" if dept else "Upstream Oil & Gas"

        # 5. Activity & Work Context
        activity = cls.parse_str_optional(
            cls.clean_text(r.get("job_type") or r_lower.get("job_type") or r.get("activity") or "Field Operation")
        )

        # 6. Incident Narrative & Description
        narrative = cls.clean_text(
            r.get("raw_text")
            or r_lower.get("raw_text")
            or r.get("incident_description")
            or r_lower.get("incident_description")
            or r.get("text")
        )
        if not narrative or len(narrative) < 10:
            return None

        # 7. Hazards, Barrier Failures & Consequence
        equip = cls.clean_text(r.get("equipment_type") or r_lower.get("equipment_type") or "Equipment")
        hazard = f"Hydrocarbon / {equip}"
        energy_source = "Pressure & Mechanical Energy"
        barrier_failure = cls.parse_str_optional(cls.clean_text(r.get("barrier_failure") or r_lower.get("barrier_failure")))

        report_type = str(r.get("report_type") or r_lower.get("report_type") or "near_miss").lower()
        consequence_str = "Near Miss Event" if "near" in report_type else ("Unsafe Act / Condition" if "ua" in report_type else "Recorded Incident")

        # 8. Fatalities & Injuries
        fatality_cnt = cls.parse_int_optional(r.get("fatality"))
        injury_cnt = cls.parse_int_optional(r.get("injuries"))

        injury_severity = None
        if fatality_cnt and fatality_cnt > 0:
            injury_severity = "FATALITY"
        elif injury_cnt and injury_cnt > 0:
            injury_severity = "HOSPITALIZED"

        # 9. SIF Potential
        # In synthetic demo data, sif_potential may be specified or None
        sif_potential: bool | None = None
        if "sif_potential" in r_lower:
            raw_sif = r_lower["sif_potential"]
            if raw_sif is not None:
                sif_potential = bool(raw_sif)

        # 10. LSR
        lsr = cls.parse_str_optional(r.get("lsr") or r_lower.get("lsr"))

        # 11. Metadata
        metadata = {
            "shift": r.get("shift") or r_lower.get("shift"),
            "equipment_type": equip,
            "department": dept,
            "is_demo_template": True,
        }

        return NormalizedIncident(
            report_id=report_id,
            source="SYNTHETIC",
            date=date_iso,
            country="India",
            site=site,
            sector=sector,
            activity=activity,
            incident_description=narrative,
            hazard=hazard,
            energy_source=energy_source,
            exposure="Simulated hazard exposure",
            barrier_failure=barrier_failure,
            consequence=consequence_str,
            fatality=fatality_cnt,
            injury_severity=injury_severity,
            sif_potential=sif_potential,
            lsr=lsr,
            precursor={"simulated": True, "equipment": equip},
            source_dataset="synthetic_demo_reports",
            source_record_id=source_id,
            source_url=SYNTHETIC_SOURCE_URL,
            dataset_version=SYNTHETIC_DATASET_VERSION,
            data_type="synthetic",  # STRICTLY LABEL AS SYNTHETIC
            metadata={k: v for k, v in metadata.items() if v is not None},
        )

    @classmethod
    def ingest_file(cls, file_path: str | Path) -> tuple[list[NormalizedIncident], list[dict[str, Any]]]:
        """Ingest and normalize a synthetic JSON or CSV file."""
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"Synthetic data file not found at: {p}")

        raw_records: list[dict[str, Any]] = []
        if p.suffix.lower() == ".json":
            content = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(content, list):
                raw_records = content
            elif isinstance(content, dict) and "reports" in content:
                raw_records = content["reports"]
            elif isinstance(content, dict) and "data" in content:
                raw_records = content["data"]
            else:
                raw_records = [content]
        else:
            text = p.read_text(encoding="utf-8-sig", errors="replace")
            sample = text[:2048]
            delimiter = ","
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=",\t;|").delimiter
            except Exception:
                pass
            reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
            raw_records = [dict(row) for row in reader]

        normalized: list[NormalizedIncident] = []
        rejected: list[dict[str, Any]] = []

        for idx, item in enumerate(raw_records):
            try:
                rec = cls.normalize_record(item)
                if rec and rec.incident_description and len(rec.incident_description) >= 10:
                    normalized.append(rec)
                else:
                    rejected.append({
                        "index": idx,
                        "raw": item,
                        "reason": "Missing or insufficient incident description or invalid ID",
                    })
            except Exception as e:
                logger.error(f"Error normalizing synthetic record {idx}: {e}")
                rejected.append({"index": idx, "raw": item, "reason": str(e)})

        return normalized, rejected
