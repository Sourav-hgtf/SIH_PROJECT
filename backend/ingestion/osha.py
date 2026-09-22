"""OSHA (Occupational Safety and Health Administration) Ingestion Module.

Parses public OSHA Severe Injury and Fatality Reports, with domain filtering
and sector mapping tailored to Oil & Gas extraction, drilling, refining, and pipeline transport.

NAICS Codes Mapped:
- 211: Oil and Gas Extraction (Crude petroleum & natural gas)
- 213: Support Activities for Mining / Drilling Oil and Gas Wells
- 324: Petroleum and Coal Products Manufacturing (Refineries)
- 486: Pipeline Transportation (Crude oil, refined products, natural gas)

Source:
https://www.osha.gov/severe-injury-reports
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

OSHA_SOURCE_URL = "https://www.osha.gov/severe-injury-reports"
OSHA_DATASET_VERSION = "osha_severe_injuries_v2024"

# Oil & Gas Sector NAICS Prefixes
OIL_GAS_NAICS_PREFIXES = ("211", "213", "324", "486")


class OSHAIngestionAdapter(IncidentNormalizer):
    """Adapter for ingesting public OSHA severe injury records."""

    @classmethod
    def is_oil_gas_record(cls, raw: dict[str, Any]) -> bool:
        """Check if record belongs to Oil & Gas extraction, refining, or pipeline NAICS codes."""
        r = {str(k).strip().upper(): v for k, v in raw.items() if k is not None}
        naics = str(r.get("NAICS") or r.get("NAICS_CODE") or "").strip()
        if any(naics.startswith(pfx) for pfx in OIL_GAS_NAICS_PREFIXES):
            return True

        employer = str(r.get("EMPLOYER") or "").upper()
        narrative = str(r.get("FINAL NARRATIVE") or r.get("NARRATIVE") or "").upper()
        combined = f"{employer} {narrative}"
        oil_gas_patterns = [
            r"\bDRILLING\b",
            r"\bWELLHEAD\b",
            r"\bRIG\b",
            r"\bRIG FLOOR\b",
            r"\bREFINERY\b",
            r"\bPIPELINE\b",
            r"\bOILFIELD\b",
            r"\bHYDRAULIC FRACTURING\b",
            r"\bFRACKING\b",
            r"\bFRAC TANK\b",
            r"\bBLOWOUT\b",
            r"\bCRUDE OIL\b",
            r"\bPETROLEUM\b",
        ]
        import re
        return any(re.search(pat, combined) for pat in oil_gas_patterns)

    @classmethod
    def normalize_record(cls, raw: dict[str, Any], filter_oil_gas: bool = False) -> NormalizedIncident | None:
        """Normalize a single OSHA severe injury record into canonical NormalizedIncident schema."""
        if filter_oil_gas and not cls.is_oil_gas_record(raw):
            return None

        r = {str(k).strip().upper(): v for k, v in raw.items() if k is not None}

        # 1. Report ID & Provenance
        raw_id = r.get("ID") or r.get("INCIDENT_ID") or r.get("REPORT_ID")
        if not raw_id:
            return None
        source_id = str(raw_id).strip()
        report_id = f"OSHA-{source_id}"

        # 2. Date
        raw_date = r.get("INCIDENT DATE") or r.get("EVENT_DATE") or r.get("DATE")
        date_iso = cls.parse_optional_date(raw_date)

        # 3. Geography & Facility
        employer = cls.clean_text(r.get("EMPLOYER") or r.get("ESTABLISHMENT_NAME"))
        city = cls.clean_text(r.get("CITY"))
        state = cls.clean_text(r.get("STATE"))

        site_parts = [p for p in [employer, city, state] if p]
        site_str = " - ".join(site_parts) if site_parts else (employer or None)

        # 4. Sector & NAICS
        naics = str(r.get("NAICS") or r.get("NAICS_CODE") or "").strip()
        sector = "Industrial Workplace"
        if naics.startswith("211"):
            sector = "Upstream - Oil and Gas Extraction"
        elif naics.startswith("213"):
            sector = "Upstream - Drilling and Well Services"
        elif naics.startswith("324"):
            sector = "Downstream - Petroleum Refining"
        elif naics.startswith("486"):
            sector = "Midstream - Pipeline Transportation"
        elif cls.is_oil_gas_record(raw):
            sector = "Oil and Gas Operations"

        # 5. Activity & Context
        event_title = cls.clean_text(r.get("EVENTTITLE") or r.get("EVENT_TITLE") or r.get("EVENT"))
        source_title = cls.clean_text(r.get("SOURCETITLE") or r.get("SOURCE_TITLE") or r.get("SOURCE"))
        activity = cls.parse_str_optional(f"{event_title} involving {source_title}".strip(" involving")) or event_title or None

        # 6. Incident Narrative & Description
        narrative = cls.clean_text(
            r.get("FINAL NARRATIVE")
            or r.get("FINAL_NARRATIVE")
            or r.get("NARRATIVE")
            or r.get("EVENT_DESCRIPTION")
            or r.get("DESCRIPTION")
        )
        if not narrative or len(narrative) < 10:
            nature = cls.clean_text(r.get("NATURETITLE") or r.get("NATURE_TITLE"))
            part = cls.clean_text(r.get("PARTTITLE") or r.get("PART_TITLE"))
            parts = [f"OSHA severe injury reported at {employer or 'worksite'}."]
            if activity:
                parts.append(f"Event: {activity}.")
            if nature and part:
                parts.append(f"Injury sustained: {nature} to {part}.")
            elif nature:
                parts.append(f"Injury sustained: {nature}.")
            narrative = " ".join(parts).strip()

        # 7. Hazards, Energy Source, & Barrier Failures
        hazard = cls.parse_str_optional(source_title) or "Mechanical / Industrial Equipment"
        energy_source = "Mechanical & Kinetic Energy"
        narrative_upper = narrative.upper()
        if "PRESSURE" in narrative_upper or "HYDRAULIC" in narrative_upper:
            energy_source = "Hydraulic & Pressure Energy"
        elif "ELECTRICAL" in narrative_upper or "VOLTAGE" in narrative_upper:
            energy_source = "Electrical Energy"
        elif "THERMAL" in narrative_upper or "BURN" in narrative_upper or "FIRE" in narrative_upper:
            energy_source = "Thermal & Flammable Hydrocarbon"

        barrier_failure = cls.parse_str_optional(f"Deficiency in barrier during {event_title}".strip()) if event_title else None

        nature_title = cls.clean_text(r.get("NATURETITLE") or r.get("NATURE_TITLE"))
        consequence_str = nature_title or "Severe Occupational Injury"

        # 8. Fatalities & Injuries
        fatality_cnt = cls.parse_int_optional(r.get("FATALITY") or r.get("FATALITIES"))
        hospitalized = cls.parse_int_optional(r.get("HOSPITALIZED") or r.get("INJURED"))
        amputation = cls.parse_int_optional(r.get("AMPUTATION"))

        injury_severity = None
        if fatality_cnt and fatality_cnt > 0:
            injury_severity = "FATALITY"
        elif hospitalized and hospitalized > 0:
            injury_severity = "HOSPITALIZED"
        elif amputation and amputation > 0:
            injury_severity = "AMPUTATION"

        # 9. SIF Potential
        # In OSHA Severe Injury Reports, all records are verified life-altering / severe events (in-patient hospitalizations or amputations)
        sif_potential: bool | None = None
        if (fatality_cnt is not None and fatality_cnt > 0) or (hospitalized and hospitalized > 0) or (amputation and amputation > 0):
            sif_potential = True
        elif fatality_cnt == 0 and (hospitalized == 0 or hospitalized is None) and (amputation == 0 or amputation is None):
            sif_potential = False

        # 10. Canonical LSR mapping
        lsr: str | None = None
        comb = (event_title + " " + source_title + " " + narrative).upper()
        if "LINE OF FIRE" in comb or "PINCH" in comb or "STRUCK" in comb or "CAUGHT" in comb:
            lsr = "Line of Fire"
        elif "FALL" in comb or "HEIGHT" in comb or "SCAFFOLD" in comb or "LADDER" in comb:
            lsr = "Working at Height"
        elif "CRANE" in comb or "HOIST" in comb or "SLING" in comb or "SUSPENDED" in comb:
            lsr = "Mechanical Lifting"
        elif "ISOLATION" in comb or "LOTO" in comb or "ENERGIZED" in comb:
            lsr = "Energy Isolation"
        elif "CONFINED" in comb:
            lsr = "Confined Space Entry"
        elif "HOT WORK" in comb or "WELDING" in comb or "TORCH" in comb:
            lsr = "Hot Work"

        # 11. Metadata
        metadata = {
            "employer": employer,
            "naics": naics,
            "nature": nature_title,
            "part_of_body": r.get("PARTTITLE") or r.get("PART_TITLE"),
            "event_title": event_title,
            "source_title": source_title,
            "hospitalized": hospitalized,
            "amputation": amputation,
        }

        return NormalizedIncident(
            report_id=report_id,
            source="OSHA",
            date=date_iso,
            country="USA",
            site=site_str,
            sector=sector,
            activity=activity,
            incident_description=narrative,
            hazard=hazard,
            energy_source=energy_source,
            exposure="Kinetic / Mechanical / Chemical hazard exposure",
            barrier_failure=barrier_failure,
            consequence=consequence_str,
            fatality=fatality_cnt,
            injury_severity=injury_severity,
            sif_potential=sif_potential,
            lsr=lsr,
            precursor={"event": event_title, "source": source_title, "nature": nature_title},
            source_dataset="osha_severe_injury_reports",
            source_record_id=source_id,
            source_url=OSHA_SOURCE_URL,
            dataset_version=OSHA_DATASET_VERSION,
            data_type="real",
            metadata={k: v for k, v in metadata.items() if v is not None},
        )

    @classmethod
    def ingest_file(
        cls, file_path: str | Path, filter_oil_gas: bool = False
    ) -> tuple[list[NormalizedIncident], list[dict[str, Any]]]:
        """Ingest and normalize an OSHA severe injury CSV or JSON file."""
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"OSHA data file not found at: {p}")

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
                rec = cls.normalize_record(item, filter_oil_gas=filter_oil_gas)
                if rec and rec.incident_description and len(rec.incident_description) >= 10:
                    normalized.append(rec)
                else:
                    if filter_oil_gas and not cls.is_oil_gas_record(item):
                        continue  # Skipped by domain filter
                    rejected.append({
                        "index": idx,
                        "raw": item,
                        "reason": "Missing or insufficient incident description or invalid ID",
                    })
            except Exception as e:
                logger.error(f"Error normalizing OSHA record {idx}: {e}")
                rejected.append({"index": idx, "raw": item, "reason": str(e)})

        return normalized, rejected
