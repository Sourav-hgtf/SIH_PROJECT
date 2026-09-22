"""Ingest a JSON export of HSSE reports (A1 connector)."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Site
from app.services import ingest_and_process, log_ingestion_run, rebuild_clusters


def ingest_file(path: Path, db: Session) -> int:
    payload = json.loads(path.read_text())
    count = 0
    for row in payload:
        site = db.query(Site).filter(Site.name == row["site_name"]).first()
        if not site:
            site = Site(name=row["site_name"], region=row.get("region", "Assam"))
            db.add(site)
            db.flush()
        ingest_and_process(
            db,
            source_report_id=row["source_report_id"],
            report_type=row["report_type"],
            site_id=site.id,
            raw_text=row["raw_text"],
            reported_at=datetime.fromisoformat(row["reported_at"].replace("Z", "+00:00")),
            department=row.get("department"),
            shift=row.get("shift"),
            equipment_type=row.get("equipment_type"),
            job_type=row.get("job_type"),
        )
        count += 1
    rebuild_clusters(db)
    log_ingestion_run(db, source=str(path), record_count=count)
    db.commit()
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    db = SessionLocal()
    try:
        n = ingest_file(args.file, db)
        print(f"Ingested {n} reports from {args.file}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
