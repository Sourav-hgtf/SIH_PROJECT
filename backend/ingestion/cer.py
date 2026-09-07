"""CER (Canada Energy Regulator) Pipeline Incident Ingestion Module.

Parses public Canada Energy Regulator open pipeline incident datasets.

Source:
https://open.canada.ca/data/en/dataset/918c50ff-244e-4f11-9a74-b5a837072935
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

CER_SOURCE_URL = "https://open.canada.ca/data/en/dataset/918c50ff-244e-4f11-9a74-b5a837072935"
CER_DATASET_VERSION = "cer_pipeline_incidents_v2024"


class CERIngestionAdapter(IncidentNormalizer):
    """Adapter for ingesting public Canada Energy Regulator pipeline incident records."""

    @classmethod
    def normalize_record(cls, raw: dict[str, Any]) -> NormalizedIncident | None:
        """Normalize a single CER raw record dictionary into canonical NormalizedIncident schema."""
        r = {str(k).strip(): v for k, v in raw.items() if k is not None}
        r_lower = {str(k).strip().lower().replace(" ", "_"): v for k, v in raw.items() if k is not None}

        # 1. Report ID & Provenance
        raw_id = (
            r.get("Incident Number")
            or r.get("Incident ID")
            or r_lower.get("incident_number")
            or r_lower.get("incident_id")
            or r.get("ID")
        )
        if not raw_id:
            return None
        source_id = str(raw_id).strip()
        report_id = f"CER-{source_id}"

        # 2. Date
        raw_date = (
            r.get("Incident Date")
            or r_lower.get("incident_date")
            or r.get("Date")
            or r_lower.get("date")
        )
        date_iso = cls.parse_optional_date(raw_date)

        # 3. Geography & Facility
        company = cls.clean_text(r.get("Company") or r_lower.get("company"))
        pipeline = cls.clean_text(r.get("Pipeline Name") or r_lower.get("pipeline_name"))
        province = cls.clean_text(r.get("Province") or r_lower.get("province"))

        site_parts = [p for p in [company, pipeline, province] if p]
        site_str = " - ".join(site_parts) if site_parts else None

        # 4. Sector & Substance
        substance = cls.clean_text(r.get("Substance") or r_lower.get("substance"))
        sector = "Pipeline Transportation"
        if substance:
            sector = f"Pipeline Transportation - {substance}"

        # 5. Activity & Work Context
        activity = cls.parse_str_optional(
            cls.clean_text(
                r.get("Activity at time of incident")
                or r_lower.get("activity_at_time_of_incident")
                or r.get("Activity")
                or "Pipeline Operations & Maintenance"
            )
        )

        # 6. Incident Narrative & Description
        narrative = cls.clean_text(
            r.get("What happened narrative")
            or r_lower.get("what_happened_narrative")
            or r.get("Detailed Description")
            or r_lower.get("detailed_description")
            or r.get("Incident Description")
            or r_lower.get("incident_description")
            or r.get("Narrative")
        )
        if not narrative or len(narrative) < 10:
            primary_cause = cls.clean_text(r.get("Primary Cause") or r_lower.get("primary_cause"))
            adverse = cls.clean_text(r.get("Adverse Effects") or r_lower.get("adverse_effects"))
            parts = [f"CER recorded pipeline incident involving {company or 'operator'} on {pipeline or 'pipeline'}."]
            if primary_cause:
                parts.append(f"Primary cause: {primary_cause}.")
            if substance:
                parts.append(f"Substance involved: {substance}.")
            if adverse:
                parts.append(f"Effects observed: {adverse}.")
            narrative = " ".join(parts).strip()

        # 7. Hazards & Barrier Failures
        cause = cls.clean_text(r.get("Primary Cause") or r_lower.get("primary_cause"))
        barrier_failure = cls.parse_str_optional(cause)

        hazard = cls.parse_str_optional(substance) or "Pressurized Pipeline Fluid"
        energy_source = "Pressure & Stored Chemical Energy"

        adverse_effects = cls.clean_text(r.get("Adverse Effects") or r_lower.get("adverse_effects"))
        event_types = cls.clean_text(r.get("Event Types") or r_lower.get("event_types"))
        consequence_str = adverse_effects or event_types or "Loss of Containment"

        # 8. Fatalities & Injuries
        fatality_cnt = cls.parse_int_optional(r.get("Fatalities") or r_lower.get("fatalities"))
        injury_cnt = cls.parse_int_optional(r.get("Serious Injuries") or r_lower.get("serious_injuries"))

        injury_severity = None
        if fatality_cnt and fatality_cnt > 0:
            injury_severity = "FATALITY"
        elif injury_cnt and injury_cnt > 0:
            injury_severity = "HOSPITALIZED"

        # 9. SIF Potential (Never invent arbitrary heuristics!)
        # Check explicit CER "Significant" classification and casualty records
        is_significant = str(r.get("Significant") or r_lower.get("significant") or "").strip().lower() in ("yes", "true", "1")
        sif_potential: bool | None = None
        if (fatality_cnt is not None and fatality_cnt > 0) or (injury_cnt is not None and injury_cnt > 0):
            sif_potential = True
        elif is_significant:
            sif_potential = True
        elif fatality_cnt == 0 and injury_cnt == 0 and not is_significant:
            sif_potential = False

        # 10. Canonical LSR mapping
        lsr: str | None = None
        cause_upper = (cause + " " + narrative).upper()
        if "CORROSION" in cause_upper or "CRACKING" in cause_upper or "DEFECT" in cause_upper:
            lsr = "Asset Integrity / Work Authorisation"
        elif "EXTERNAL INTERFERENCE" in cause_upper or "EXCAVATION" in cause_upper:
            lsr = "Excavation / Line of Fire"
        elif "INCORRECT OPERATION" in cause_upper or "VALVE" in cause_upper or "ISOLATION" in cause_upper:
            lsr = "Energy Isolation"
        elif "FIRE" in cause_upper or "EXPLOSION" in cause_upper:
            lsr = "Hot Work"

        # 11. Metadata
        metadata = {
            "pipeline_name": pipeline,
            "province": province,
            "substance": substance,
            "significant_flag": is_significant,
            "approximate_volume_released": r.get("Approximate Volume Released") or r_lower.get("approximate_volume_released"),
            "status": r.get("Status") or r_lower.get("status"),
        }

        return NormalizedIncident(
            report_id=report_id,
            source="CER",
            date=date_iso,
            country="Canada",
            site=site_str,
            sector=sector,
            activity=activity,
            incident_description=narrative,
            hazard=hazard,
            energy_source=energy_source,
            exposure="Pipeline substance release",
            barrier_failure=barrier_failure,
            consequence=consequence_str,
            fatality=fatality_cnt,
            injury_severity=injury_severity,
            sif_potential=sif_potential,
            lsr=lsr,
            precursor={"primary_cause": cause, "pipeline": pipeline, "province": province},
            source_dataset="cer_pipeline_incidents",
            source_record_id=source_id,
            source_url=CER_SOURCE_URL,
            dataset_version=CER_DATASET_VERSION,
            data_type="real",
            metadata={k: v for k, v in metadata.items() if v is not None},
        )

    @classmethod
    def ingest_file(cls, file_path: str | Path) -> tuple[list[NormalizedIncident], list[dict[str, Any]]]:
        """Ingest and normalize a CER CSV or JSON file."""
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"CER data file not found at: {p}")

        raw_records: list[dict[str, Any]] = []
        if p.suffix.lower() == ".json":
            content = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(content, list):
                raw_records = content
            elif isinstance(content, dict) and "records" in content:
                raw_records = content["records"]
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
                logger.error(f"Error normalizing CER record {idx}: {e}")
                rejected.append({"index": idx, "raw": item, "reason": str(e)})

        return normalized, rejected
