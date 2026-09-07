"""OISD (Oil Industry Safety Directorate, India) Ingestion Module.

Parses public safety alerts, incident case studies, and root-cause analysis bulletins
from the Oil Industry Safety Directorate under the Ministry of Petroleum and Natural Gas (MoPNG).
Covers upstream exploration & production (e.g., Oil India Limited, ONGC), refineries,
and cross-country pipeline installations across India.

Source:
https://www.oisd.gov.in
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

OISD_SOURCE_URL = "https://www.oisd.gov.in"
OISD_DATASET_VERSION = "oisd_major_incident_case_studies_v1"


class OISDIngestionAdapter(IncidentNormalizer):
    """Adapter for ingesting Oil Industry Safety Directorate (OISD) incident reports."""

    @classmethod
    def normalize_record(cls, raw: dict[str, Any]) -> NormalizedIncident | None:
        """Normalize a single OISD incident report into canonical NormalizedIncident schema."""
        r = {str(k).strip(): v for k, v in raw.items() if k is not None}
        r_lower = {str(k).strip().lower().replace(" ", "_"): v for k, v in raw.items() if k is not None}

        # 1. Report ID & Provenance
        raw_id = (
            r.get("Incident No")
            or r.get("Case Study No")
            or r.get("Alert ID")
            or r_lower.get("incident_no")
            or r_lower.get("case_study_no")
            or r_lower.get("alert_id")
            or r.get("ID")
            or r_lower.get("id")
        )
        if not raw_id:
            return None
        source_id = str(raw_id).strip()
        report_id = f"OISD-{source_id}"

        # 2. Date
        raw_date = (
            r.get("Date of Occurrence")
            or r_lower.get("date_of_occurrence")
            or r.get("Incident Date")
            or r_lower.get("incident_date")
            or r.get("Date")
        )
        date_iso = cls.parse_optional_date(raw_date)

        # 3. Geography & Facility
        org = cls.clean_text(r.get("Organization") or r_lower.get("organization") or r.get("Company"))
        unit = cls.clean_text(r.get("Installation / Unit") or r_lower.get("installation_unit") or r.get("Facility") or r.get("Site"))
        state = cls.clean_text(r.get("State / Region") or r_lower.get("state_region") or r.get("State") or r.get("Region"))

        site_parts = [p for p in [unit, org, state] if p]
        site_str = " - ".join(site_parts) if site_parts else None

        # 4. Sector
        sector = cls.clean_text(r.get("Sector") or r_lower.get("sector"))
        if not sector:
            comb = (org + " " + unit).upper()
            if "REFINERY" in comb or "CDU" in comb or "PETROCHEM" in comb:
                sector = "Downstream - Refining & Petrochemicals"
            elif "PIPELINE" in comb or "PUMPING" in comb:
                sector = "Midstream - Cross-Country Pipelines"
            else:
                sector = "Upstream - Exploration & Production"

        # 5. Activity & Work Context
        activity = cls.parse_str_optional(
            cls.clean_text(
                r.get("Activity Underway")
                or r_lower.get("activity_underway")
                or r.get("Job Type")
                or r_lower.get("job_type")
                or r.get("Work Activity")
            )
        )

        # 6. Incident Narrative & Description
        narrative = cls.clean_text(
            r.get("Description of Incident")
            or r_lower.get("description_of_incident")
            or r.get("Sequence of Events")
            or r_lower.get("sequence_of_events")
            or r.get("Narrative")
            or r_lower.get("narrative")
            or r.get("Details")
        )
        if not narrative or len(narrative) < 10:
            hazard_det = cls.clean_text(r.get("Hazard Type") or r_lower.get("hazard_type"))
            barrier_det = cls.clean_text(r.get("Barrier Failure") or r_lower.get("barrier_failure"))
            parts = [f"OISD safety case record at {unit or org or 'oil & gas installation'}."]
            if activity:
                parts.append(f"Activity underway: {activity}.")
            if hazard_det:
                parts.append(f"Hazard encountered: {hazard_det}.")
            if barrier_det:
                parts.append(f"Barrier deficiency: {barrier_det}.")
            narrative = " ".join(parts).strip()

        # 7. Hazard & Barrier Failure
        hazard = cls.parse_str_optional(cls.clean_text(r.get("Hazard Type") or r_lower.get("hazard_type"))) or "Pressurized Hydrocarbon"
        barrier_failure = cls.parse_str_optional(
            cls.clean_text(r.get("Barrier Failure") or r_lower.get("barrier_failure") or r.get("Root Cause"))
        )
        energy_source = cls.parse_str_optional(cls.clean_text(r.get("Energy Source") or r_lower.get("energy_source"))) or "Hydrocarbon Chemical & Pressure Energy"

        consequence_str = cls.clean_text(r.get("Consequence") or r_lower.get("consequence")) or "Loss of Containment / Flash Fire"

        # 8. Fatalities & Injuries
        fatality_cnt = cls.parse_int_optional(r.get("Fatalities") or r_lower.get("fatalities"))
        injury_cnt = cls.parse_int_optional(r.get("Injuries") or r_lower.get("injuries"))

        injury_severity = None
        if fatality_cnt and fatality_cnt > 0:
            injury_severity = "FATALITY"
        elif injury_cnt and injury_cnt > 0:
            injury_severity = "HOSPITALIZED"

        # 9. SIF Potential (Based strictly on documented outcome or official classification)
        sif_potential: bool | None = None
        sif_flag_raw = r.get("SIF Potential") or r_lower.get("sif_potential")
        if sif_flag_raw is not None:
            sif_potential = str(sif_flag_raw).strip().lower() in ("yes", "true", "1", "high")
        elif (fatality_cnt is not None and fatality_cnt > 0) or (injury_cnt is not None and injury_cnt > 0):
            sif_potential = True
        elif fatality_cnt == 0 and injury_cnt == 0:
            sif_potential = False

        # 10. Canonical Life-Saving Rule & Standard Mapping
        lsr_field = cls.clean_text(
            r.get("Life Saving Rule Violated")
            or r_lower.get("life_saving_rule_violated")
            or r.get("LSR")
            or r.get("OISD Standard")
            or r_lower.get("oisd_standard")
        )
        lsr: str | None = None
        comb_text = (lsr_field + " " + narrative + " " + str(barrier_failure)).upper()
        if "ISOLATION" in comb_text or "LOTO" in comb_text or "ENERGY" in comb_text:
            lsr = "Energy Isolation"
        elif "HOT WORK" in comb_text or "PERMIT" in comb_text or "PTW" in comb_text or "OISD-STD-105" in comb_text:
            lsr = "Hot Work / Work Authorisation"
        elif "LINE OF FIRE" in comb_text or "HOSE" in comb_text or "PRESSURE" in comb_text:
            lsr = "Line of Fire"
        elif "CONFINED SPACE" in comb_text or "CSE" in comb_text:
            lsr = "Confined Space Entry"
        elif "LIFTING" in comb_text or "CRANE" in comb_text or "SUSPENDED" in comb_text:
            lsr = "Mechanical Lifting"
        elif "BYPASS" in comb_text or "INTERLOCK" in comb_text:
            lsr = "Bypassing Safety Controls"
        elif lsr_field:
            lsr = lsr_field

        # 11. Metadata
        metadata = {
            "organization": org,
            "unit": unit,
            "oisd_standard": r.get("OISD Standard") or r_lower.get("oisd_standard"),
            "corrective_actions_advised": r.get("Corrective Actions") or r_lower.get("corrective_actions"),
            "investigation_status": r.get("Investigation Status") or r_lower.get("investigation_status"),
        }

        return NormalizedIncident(
            report_id=report_id,
            source="OISD",
            date=date_iso,
            country="India",
            site=site_str,
            sector=sector,
            activity=activity,
            incident_description=narrative,
            hazard=hazard,
            energy_source=energy_source,
            exposure="Process hazard exposure",
            barrier_failure=barrier_failure,
            consequence=consequence_str,
            fatality=fatality_cnt,
            injury_severity=injury_severity,
            sif_potential=sif_potential,
            lsr=lsr,
            precursor={"barrier_failure": barrier_failure, "activity": activity, "hazard": hazard},
            source_dataset="oisd_safety_reports",
            source_record_id=source_id,
            source_url=OISD_SOURCE_URL,
            dataset_version=OISD_DATASET_VERSION,
            data_type="real",
            metadata={k: v for k, v in metadata.items() if v is not None},
        )

    @classmethod
    def ingest_file(cls, file_path: str | Path) -> tuple[list[NormalizedIncident], list[dict[str, Any]]]:
        """Ingest and normalize an OISD JSON or CSV file."""
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"OISD data file not found at: {p}")

        raw_records: list[dict[str, Any]] = []
        if p.suffix.lower() == ".json":
            content = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(content, list):
                raw_records = content
            elif isinstance(content, dict) and "reports" in content:
                raw_records = content["reports"]
            elif isinstance(content, dict) and "case_studies" in content:
                raw_records = content["case_studies"]
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
                logger.error(f"Error normalizing OISD record {idx}: {e}")
                rejected.append({"index": idx, "raw": item, "reason": str(e)})

        return normalized, rejected
