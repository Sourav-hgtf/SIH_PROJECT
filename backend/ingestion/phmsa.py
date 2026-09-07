"""PHMSA (Pipeline and Hazardous Materials Safety Administration) Ingestion Module.

Parses public US DOT PHMSA pipeline accident and incident reports (hazardous liquids,
gas transmission, and gathering systems).

Source:
https://www.phmsa.dot.gov/data-and-statistics/pipeline/distribution-transmission-gathering-lng-and-liquid-accident-and-incident-data
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

PHMSA_SOURCE_URL = (
    "https://www.phmsa.dot.gov/data-and-statistics/pipeline/"
    "distribution-transmission-gathering-lng-and-liquid-accident-and-incident-data"
)
PHMSA_DATASET_VERSION = "phmsa_incident_data_2010_present_v1"


class PHMSAIngestionAdapter(IncidentNormalizer):
    """Adapter for ingesting public US DOT PHMSA pipeline accident records."""

    @classmethod
    def normalize_record(cls, raw: dict[str, Any]) -> NormalizedIncident | None:
        """Normalize a single PHMSA raw record dictionary into canonical NormalizedIncident schema."""
        # Clean keys (case-insensitive, strip whitespace)
        r = {str(k).strip().upper(): v for k, v in raw.items() if k is not None}

        # 1. Report ID & Provenance
        raw_id = (
            r.get("REPORT_NUMBER")
            or r.get("ACCIDENT_IDENTIFIER")
            or r.get("REPORT_NUM")
            or r.get("ID")
        )
        if not raw_id:
            return None
        source_id = str(raw_id).strip()
        report_id = f"PHMSA-{source_id}"

        # 2. Date
        raw_date = (
            r.get("LOCAL_DATETIME")
            or r.get("LOCAL_SIGNIFICANT_DATETIME")
            or r.get("ACCIDENT_DATE")
            or r.get("DATE")
        )
        # Fallback to year-month-day columns if composite date is absent
        if not raw_date and r.get("IYEAR") and r.get("IMONTH") and r.get("IDAY"):
            try:
                y = int(r["IYEAR"])
                m = int(r["IMONTH"])
                d = int(r["IDAY"])
                raw_date = f"{y:04d}-{m:02d}-{d:02d}"
            except (ValueError, TypeError):
                raw_date = None
        date_iso = cls.parse_optional_date(raw_date)

        # 3. Geography & Facility
        operator = cls.clean_text(r.get("OPERATOR_NAME") or r.get("NAME_OPERATOR") or r.get("OPERATOR_ID"))
        city = cls.clean_text(r.get("LOCATION_CITY_NAME") or r.get("CITY"))
        state = cls.clean_text(r.get("LOCATION_STATE_ABBREVIATION") or r.get("STATE"))
        loc_parts = [p for p in [city, state] if p]
        loc_str = f"({', '.join(loc_parts)})" if loc_parts else ""
        site_parts = [p for p in [operator, loc_str] if p]
        site_str = " ".join(site_parts).strip() if site_parts else None

        # 4. Sector & Commodity
        commodity = cls.clean_text(r.get("COMMODITY_RELEASED_TYPE") or r.get("COMMODITY_SUBTYPE") or r.get("COMMODITY"))
        system_type = cls.clean_text(r.get("SYSTEM_TYPE") or r.get("SIGNIFICANT_INCIDENT_TYPE"))
        if "GAS" in (commodity + system_type).upper():
            sector = "Pipeline Transportation - Natural Gas"
        elif "LIQUID" in (commodity + system_type).upper() or "CRUDE" in commodity.upper():
            sector = "Pipeline Transportation - Hazardous Liquids"
        else:
            sector = cls.parse_str_optional(f"Pipeline Transportation - {commodity}" if commodity else "Pipeline Transportation")

        # 5. Activity & Work Context
        activity = cls.parse_str_optional(
            cls.clean_text(r.get("OPERATION_TYPE") or r.get("ACTIVITY_TYPE") or r.get("ITEM_INVOLVED") or "Pipeline Transmission & Distribution")
        )

        # 6. Incident Narrative & Description
        narrative = cls.clean_text(
            r.get("NARRATIVE")
            or r.get("INCIDENT_SUMMARY")
            or r.get("CAUSE_DESCRIPTION")
            or r.get("ACCIDENT_DESCRIPTION")
            or r.get("DESCRIPTION")
        )
        if not narrative or len(narrative) < 10:
            # If explicit narrative column is missing, construct strictly factual summary from documented fields
            cause_detail = cls.clean_text(r.get("CAUSE") or r.get("APPARENT_CAUSE") or r.get("GENERAL_CAUSE"))
            system_part = cls.clean_text(r.get("SYSTEM_PART_INVOLVED") or r.get("ITEM_INVOLVED"))
            spill_vol = cls.clean_text(r.get("UNINTENTIONAL_RELEASE_BBLS") or r.get("SPILL_TYPE_DESCRIPTION"))
            parts = [f"PHMSA reported pipeline accident involving {operator or 'operator'}."]
            if system_part:
                parts.append(f"Component involved: {system_part}.")
            if cause_detail:
                parts.append(f"Cause documented: {cause_detail}.")
            if commodity:
                parts.append(f"Commodity released: {commodity}.")
            if spill_vol:
                parts.append(f"Release volume: {spill_vol}.")
            narrative = " ".join(parts).strip()

        # 7. Hazards, Barrier Failures & Consequence
        cause = cls.clean_text(r.get("CAUSE") or r.get("GENERAL_CAUSE") or r.get("APPARENT_CAUSE"))
        subcause = cls.clean_text(r.get("SUBCAUSE") or r.get("SPECIFIC_CAUSE"))
        barrier_failure = cls.parse_str_optional(f"{cause} - {subcause}".strip(" -")) or cls.parse_str_optional(cause)

        hazard = cls.parse_str_optional(commodity) or "Pressurized Hydrocarbon"
        energy_source = "Pressure & Chemical Hydrocarbon"

        # Consequence indicators
        ignite = str(r.get("IGNITE_IND") or "").strip().upper() in ("YES", "Y", "1", "TRUE")
        explode = str(r.get("EXPLODE_IND") or "").strip().upper() in ("YES", "Y", "1", "TRUE")
        consequences = []
        if explode:
            consequences.append("Explosion")
        if ignite:
            consequences.append("Fire")
        consequences.append("Loss of Containment")
        consequence_str = ", ".join(consequences)

        # 8. Fatalities & Injuries (Strict parsing, no invention)
        fatality_cnt = cls.parse_int_optional(r.get("NUM_FATALITIES") or r.get("FATAL") or r.get("FATALITIES"))
        injury_cnt = cls.parse_int_optional(r.get("NUM_INJURIES") or r.get("INJURE") or r.get("INJURIES"))

        injury_severity = None
        if fatality_cnt and fatality_cnt > 0:
            injury_severity = "FATALITY"
        elif injury_cnt and injury_cnt > 0:
            injury_severity = "HOSPITALIZED"

        # 9. SIF Potential (Never invent arbitrary heuristics!)
        # Documented SIF = True if verified fatality or hospitalized injury or explosion occurred
        sif_potential: bool | None = None
        if (fatality_cnt is not None and fatality_cnt > 0) or (injury_cnt is not None and injury_cnt > 0) or explode:
            sif_potential = True
        elif fatality_cnt == 0 and injury_cnt == 0 and not ignite and not explode:
            sif_potential = False
        # else remains None (unlabeled)

        # 10. Canonical LSR mapping
        lsr: str | None = None
        cause_upper = (cause + " " + subcause + " " + narrative).upper()
        if "CORROSION" in cause_upper or "MATERIAL FAILURE" in cause_upper:
            lsr = "Asset Integrity / Work Authorisation"
        elif "EXCAVATION" in cause_upper or "THIRD PARTY" in cause_upper or "DIGGING" in cause_upper:
            lsr = "Excavation / Line of Fire"
        elif "ISOLATION" in cause_upper or "VALVE" in cause_upper:
            lsr = "Energy Isolation"
        elif ignite or explode or "HOT WORK" in cause_upper:
            lsr = "Hot Work"

        # 11. Retain unmapped metadata
        metadata = {
            "operator_id": r.get("OPERATOR_ID"),
            "system_part": r.get("SYSTEM_PART_INVOLVED"),
            "release_volume": r.get("UNINTENTIONAL_RELEASE_BBLS") or r.get("VOLUME_RELEASED"),
            "property_damage": r.get("TOTAL_COST") or r.get("ESTIMATED_PROPERTY_DAMAGE"),
            "commodity_type": commodity,
            "fire_ignition": ignite,
            "explosion": explode,
        }

        return NormalizedIncident(
            report_id=report_id,
            source="PHMSA",
            date=date_iso,
            country="USA",
            site=site_str,
            sector=sector,
            activity=activity,
            incident_description=narrative,
            hazard=hazard,
            energy_source=energy_source,
            exposure="Pipeline release / Rupture exposure",
            barrier_failure=barrier_failure,
            consequence=consequence_str,
            fatality=fatality_cnt,
            injury_severity=injury_severity,
            sif_potential=sif_potential,
            lsr=lsr,
            precursor={"cause": cause, "subcause": subcause, "component": r.get("SYSTEM_PART_INVOLVED")},
            source_dataset="phmsa_pipeline_incidents",
            source_record_id=source_id,
            source_url=PHMSA_SOURCE_URL,
            dataset_version=PHMSA_DATASET_VERSION,
            data_type="real",
            metadata={k: v for k, v in metadata.items() if v is not None},
        )

    @classmethod
    def ingest_file(cls, file_path: str | Path) -> tuple[list[NormalizedIncident], list[dict[str, Any]]]:
        """Ingest and normalize a PHMSA CSV or JSON file."""
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"PHMSA data file not found at: {p}")

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
            # CSV parsing
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
                logger.error(f"Error normalizing PHMSA record {idx}: {e}")
                rejected.append({"index": idx, "raw": item, "reason": str(e)})

        return normalized, rejected
