"""CLI tool to ingest, normalize, and audit real public and synthetic HSE datasets.

Usage:
  python3 backend/scripts/ingest_public_data.py --source all
  python3 backend/scripts/ingest_public_data.py --source phmsa --input data/raw/phmsa/phmsa_pipeline_incidents_sample.csv
  python3 backend/scripts/ingest_public_data.py --source oisd
  python3 backend/scripts/ingest_public_data.py --source osha --filter-oil-gas
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

# Ensure backend and project root are in sys.path
backend_dir = Path(__file__).resolve().parent.parent
project_root = backend_dir.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from ingestion import (
    CERIngestionAdapter,
    DataQualityReport,
    NormalizedIncident,
    OISDIngestionAdapter,
    OSHAIngestionAdapter,
    PHMSAIngestionAdapter,
    compute_data_quality_report,
    ingest_dataset,
)
from ingestion.synthetic import SyntheticIngestionAdapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ingest_public_data")

DEFAULT_PATHS = {
    "phmsa": project_root / "data" / "raw" / "phmsa" / "phmsa_pipeline_incidents_sample.csv",
    "cer": project_root / "data" / "raw" / "cer" / "cer_pipeline_incidents_sample.csv",
    "oisd": project_root / "data" / "raw" / "oisd" / "oisd_incident_reports_sample.json",
    "osha": project_root / "data" / "raw" / "osha" / "osha_oil_gas_severe_injuries_sample.csv",
    "synthetic": project_root / "data" / "synthetic" / "synthetic_demo_reports.json",
}


def run_ingestion(
    sources: list[str],
    custom_inputs: dict[str, Path] | None = None,
    filter_oil_gas: bool = True,
    output_path: Path | None = None,
    report_path: Path | None = None,
    load_db: bool = False,
) -> tuple[list[NormalizedIncident], DataQualityReport]:
    """Execute multi-source dataset ingestion and produce comprehensive quality report."""
    inputs = custom_inputs or {}
    all_normalized: list[NormalizedIncident] = []
    all_rejected: list[dict] = []

    for src in sources:
        path = inputs.get(src) or DEFAULT_PATHS.get(src)
        if not path or not path.exists():
            logger.warning(f"File for source '{src}' not found at {path}. Skipping.")
            continue

        logger.info(f"Ingesting [{src.upper()}] from {path}...")
        try:
            records, rejected, report = ingest_dataset(src, path, filter_oil_gas=filter_oil_gas)
            logger.info(f"[{src.upper()}] Accepted: {len(records)}, Rejected: {len(rejected)}")
            all_normalized.extend(records)
            all_rejected.extend(rejected)
        except Exception as e:
            logger.error(f"Failed to ingest source '{src}': {e}", exc_info=True)
            all_rejected.append({"source": src, "reason": str(e)})

    # Generate global quality audit
    overall_report = compute_data_quality_report(all_normalized, all_rejected)

    # Save normalized dataset if requested
    out_file = output_path or (project_root / "data" / "processed" / "normalized_incidents.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    serialized = [rec.to_dict() for rec in all_normalized]
    out_file.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
    logger.info(f"Saved {len(all_normalized)} canonical records to {out_file}")

    # Save quality audit report
    rep_file = report_path or (project_root / "data" / "processed" / "data_quality_report.json")
    rep_file.write_text(json.dumps(overall_report.to_dict(), indent=2), encoding="utf-8")
    logger.info(f"Saved Data Quality Audit to {rep_file}")

    # Optionally populate database
    if load_db and all_normalized:
        logger.info("Loading records into active SQLite database...")
        from app.database import SessionLocal
        from app.models import Site
        from app.services import ingest_and_process, log_ingestion_run, rebuild_clusters

        db = SessionLocal()
        try:
            count = 0
            for inc in all_normalized:
                site_name = inc.site or "Central Facility"
                site = db.query(Site).filter(Site.name == site_name).first()
                if not site:
                    site = Site(name=site_name, region=inc.country or "Global")
                    db.add(site)
                    db.flush()

                # Ingest through NLP pipeline
                rep_date_iso = inc.date or "2026-01-01"
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(rep_date_iso)
                except Exception:
                    from datetime import datetime, timezone
                    dt = datetime.now(timezone.utc)

                try:
                    ingest_and_process(
                        db,
                        source_report_id=inc.report_id,
                        report_type="incident" if (inc.fatality or inc.injury_severity) else "near_miss",
                        site_id=site.id,
                        raw_text=inc.incident_description,
                        reported_at=dt,
                        department=inc.sector,
                        shift="Day",
                        equipment_type=inc.hazard,
                        job_type=inc.activity,
                    )
                    count += 1
                except Exception as e:
                    logger.warning(f"Error loading record {inc.report_id} into DB: {e}")

            rebuild_clusters(db)
            log_ingestion_run(db, source="public_datasets_batch", record_count=count)
            db.commit()
            logger.info(f"Successfully loaded {count} public records into database.")
        finally:
            db.close()

    return all_normalized, overall_report


def main() -> None:
    parser = argparse.ArgumentParser(description="HSE Multi-Source Data Ingestion & Quality Audit")
    parser.add_argument(
        "--source",
        choices=["all", "phmsa", "cer", "oisd", "osha", "synthetic"],
        default="all",
        help="Source dataset to ingest (default: all)",
    )
    parser.add_argument("--input", type=Path, default=None, help="Custom input file path")
    parser.add_argument("--output", type=Path, default=None, help="Output JSON path for normalized records")
    parser.add_argument("--report", type=Path, default=None, help="Output JSON path for quality audit report")
    parser.add_argument("--load-db", action="store_true", help="Insert records into the application database")
    parser.add_argument("--no-filter", action="store_true", help="Disable sector filter for OSHA")

    args = parser.parse_args()

    sources = ["phmsa", "cer", "oisd", "osha", "synthetic"] if args.source == "all" else [args.source]
    custom_inputs = {args.source: args.input} if args.input and args.source != "all" else None

    records, report = run_ingestion(
        sources=sources,
        custom_inputs=custom_inputs,
        filter_oil_gas=not args.no_filter,
        output_path=args.output,
        report_path=args.report,
        load_db=args.load_db,
    )

    print("\n" + report.summary_text() + "\n")


if __name__ == "__main__":
    main()
