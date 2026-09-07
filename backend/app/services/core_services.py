from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.nlp.calibration import load_active_calibration
from app.models import (
    AuditLog,
    ClusterMember,
    IngestionRun,
    LsrTag,
    PrecursorCluster,
    PrecursorTriple,
    Report,
    SifClassification,
    utcnow,
)
from app.nlp.mining import group_triples
from app.nlp.pipeline import process_report_text


def write_audit(
    db: Session,
    action_type: str,
    entity_type: str,
    entity_id: str | None = None,
    user_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action_type=action_type,
            entity_type=entity_type,
            entity_id=entity_id,
            before_value=before,
            after_value=after,
        )
    )


def ingest_and_process(
    db: Session,
    *,
    source_report_id: str,
    report_type: str,
    site_id: str,
    raw_text: str,
    reported_at: datetime,
    department: str | None = None,
    shift: str | None = None,
    equipment_type: str | None = None,
    job_type: str | None = None,
    user_id: str | None = None,
) -> Report:
    calibration = load_active_calibration(settings.sif_threshold)
    result = process_report_text(
        raw_text,
        equipment=equipment_type,
        job_type=job_type,
        threshold=calibration["threshold"],
    )
    result["classification"]["model_version"] = calibration["model_version"]
    report = Report(
        source_report_id=source_report_id,
        report_type=report_type,
        site_id=site_id,
        department=department,
        shift=shift,
        equipment_type=equipment_type,
        job_type=job_type,
        raw_text_redacted=result["raw_text_redacted"],
        processed_text=result["processed_text"],
        reported_at=reported_at,
        ingested_at=utcnow(),
    )
    db.add(report)
    db.flush()

    clf = result["classification"]
    db.add(
        SifClassification(
            report_id=report.id,
            sif_probability=clf["sif_probability"],
            sif_label=clf["sif_label"],
            model_version=clf["model_version"],
            contributing_phrases=clf["contributing_phrases"],
            features=clf["features"],
        )
    )
    for tag in result["lsr_tags"]:
        db.add(
            LsrTag(
                report_id=report.id,
                lsr_category=tag.get("rule_name") or tag["lsr_category"],
                rule_id=tag.get("rule_id"),
                rule_name=tag.get("rule_name") or tag["lsr_category"],
                confidence=tag["confidence"],
                source=tag["source"],
                evidence=tag.get("evidence", []),
            )
        )
    if result["triple"]:
        db.add(
            PrecursorTriple(
                report_id=report.id,
                activity=result["triple"]["activity"],
                location_asset=result["triple"]["location_asset"],
                barrier_failure=result["triple"]["barrier_failure"],
            )
        )
    write_audit(
        db,
        action_type="ingest_report",
        entity_type="report",
        entity_id=report.id,
        user_id=user_id,
        after={"source_report_id": source_report_id, "sif_label": clf["sif_label"]},
    )
    return report


def rebuild_clusters(db: Session) -> int:
    db.query(ClusterMember).delete()
    db.query(PrecursorCluster).delete()
    db.flush()

    rows = (
        db.query(PrecursorTriple, Report)
        .join(Report, Report.id == PrecursorTriple.report_id)
        .all()
    )
    payload = []
    for triple, report in rows:
        payload.append(
            {
                "triple_id": triple.id,
                "activity": triple.activity,
                "location_asset": triple.location_asset,
                "barrier_failure": triple.barrier_failure,
                "reported_at": report.reported_at,
            }
        )
    grouped = group_triples(payload)
    count = 0
    for group in grouped:
        cluster = PrecursorCluster(
            representative_activity=group["representative_activity"],
            representative_location=group["representative_location"],
            representative_barrier_failure=group["representative_barrier_failure"],
            cluster_size=group["cluster_size"],
            trend_status=group["trend_status"],
            first_seen_at=min((m["reported_at"] for m in group["members"]), default=utcnow()),
            last_updated_at=max((m["reported_at"] for m in group["members"]), default=utcnow()),
        )
        db.add(cluster)
        db.flush()
        for member in group["members"]:
            db.add(ClusterMember(cluster_id=cluster.id, triple_id=member["triple_id"]))
        count += 1
    return count


def log_ingestion_run(db: Session, source: str, record_count: int, status: str = "COMPLETED") -> IngestionRun:
    run = IngestionRun(
        source=source,
        record_count=record_count,
        processed_count=record_count,
        status=status,
        completed_at=utcnow() if status == "COMPLETED" else None,
    )
    db.add(run)
    db.flush()
    return run


def process_ingestion_batch(
    run_id: str,
    rows: list[dict],
    user_id: str | None = None,
) -> dict:
    """Asynchronous background worker function to process a batch of HSE reports."""
    from app.database import SessionLocal
    from app.models import Site
    from app.recommendations import generate_cluster_recommendations, generate_report_recommendations
    import dateutil.parser

    db: Session = SessionLocal()
    try:
        run = db.get(IngestionRun, run_id)
        if not run:
            return {"error": "IngestionRun not found"}

        run.status = "IN_PROGRESS"
        db.commit()

        # Cache sites map
        all_sites = db.query(Site).all()
        sites_by_id = {s.id: s for s in all_sites}
        sites_by_name = {s.name.lower().strip(): s for s in all_sites}
        default_site = all_sites[0] if all_sites else None

        processed = 0
        errors = []

        for idx, item in enumerate(rows):
            try:
                # Site resolution
                site_id = item.get("site_id")
                if not site_id or site_id not in sites_by_id:
                    s_name = (item.get("site_name") or "").lower().strip()
                    if s_name and s_name in sites_by_name:
                        site_id = sites_by_name[s_name].id
                    elif default_site:
                        site_id = default_site.id
                    else:
                        raise ValueError("No valid site found for report.")

                # Date resolution
                raw_date = item.get("reported_at")
                if isinstance(raw_date, str):
                    reported_at = dateutil.parser.parse(raw_date)
                elif isinstance(raw_date, datetime):
                    reported_at = raw_date
                else:
                    reported_at = utcnow()

                # Source report ID
                source_id = item.get("source_report_id") or f"INGEST-{run_id[:8]}-{idx+1:04d}"

                report = ingest_and_process(
                    db,
                    source_report_id=str(source_id),
                    report_type=item.get("report_type") or "near_miss",
                    site_id=site_id,
                    raw_text=item["raw_text"],
                    reported_at=reported_at,
                    department=item.get("department"),
                    shift=item.get("shift"),
                    equipment_type=item.get("equipment_type"),
                    job_type=item.get("job_type"),
                    user_id=user_id,
                )

                # Generate recommendations for SIF or tagged report
                try:
                    generate_report_recommendations(report, db)
                except Exception:
                    pass

                processed += 1
                run.processed_count = processed
                if processed % 10 == 0:
                    db.commit()
            except Exception as e:
                errors.append({"row_index": idx, "error": str(e), "data": item})

        # Rebuild clusters
        rebuild_clusters(db)

        # Generate cluster recommendations
        try:
            for cluster in db.query(PrecursorCluster).all():
                generate_cluster_recommendations(cluster, db)
        except Exception:
            pass

        run.processed_count = processed
        run.error_log = errors if errors else None
        run.completed_at = utcnow()
        if processed == 0 and errors:
            run.status = "FAILED"
        else:
            run.status = "COMPLETED"

        db.commit()
        return {"run_id": run_id, "processed": processed, "errors_count": len(errors)}
    except Exception as e:
        db.rollback()
        run = db.get(IngestionRun, run_id)
        if run:
            run.status = "FAILED"
            run.error_log = [{"error": str(e)}]
            run.completed_at = utcnow()
            db.commit()
        return {"error": str(e)}
    finally:
        db.close()
