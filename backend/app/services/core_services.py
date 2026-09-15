from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config import settings
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
from app.nlp.calibration import load_active_calibration
from app.nlp.pipeline import process_report_text
from app.nlp.precursor_clustering import semantic_cluster_triples
from app.nlp.preprocess import redact_pii

# Audit and operational error records are often retained longer and exported more
# broadly than report data.  They must never become a second, unredacted report
# store.  Keep opaque identifiers and structured values, but remove report-body
# fields entirely and redact free-form strings defensively.
_OBSERVABILITY_TEXT_KEYS = frozenset(
    {
        "raw_text",
        "text_content",
        "report_text",
        "incident_description",
        "description",
        "processed_text",
        "raw",
        "data",
        "payload",
        "body",
    }
)


def redact_for_observability(value):
    """Return an audit/log-safe representation without retaining raw report text.

    This deliberately preserves record IDs and normal structured state needed for
    an audit trail, while omitting known report-content fields and applying the
    PII redactor to other user-provided strings such as analyst comments.
    """
    if isinstance(value, dict):
        safe = {}
        for key, item in value.items():
            if str(key).lower() in _OBSERVABILITY_TEXT_KEYS:
                safe[str(key)] = "[omitted]"
            else:
                safe[str(key)] = redact_for_observability(item)
        return safe
    if isinstance(value, (list, tuple, set)):
        return [redact_for_observability(item) for item in value]
    if isinstance(value, str):
        return redact_pii(value)[0]
    return value


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
            before_value=redact_for_observability(before or {}),
            after_value=redact_for_observability(after or {}),
        )
    )


def _utc_timestamp(value: datetime) -> datetime:
    """Normalize SQLite's naïve datetimes before cross-record comparisons."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


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
        lifecycle_status="HSE_REVIEW" if result["classification"]["requires_analyst_review"] else "AI_ANALYZED",
    )
    db.add(report)
    db.flush()

    clf = result["classification"]
    safe_feature_metadata = {
        **clf["features"],
        "privacy": {
            "pii_redacted": bool(result.get("pii_redacted", True)),
            "pii_entities_redacted": int(result.get("pii_replacements", 0)),
            "preprocessing_version": result.get("preprocessing_version", "prep-pii-spell-abbr-v1"),
        },
    }
    db.add(
        SifClassification(
            report_id=report.id,
            sif_probability=clf["sif_probability"],
            sif_label=clf["sif_label"],
            classification_state=clf["classification_state"],
            requires_analyst_review=clf["requires_analyst_review"],
            model_version=clf["model_version"],
            contributing_phrases=clf["contributing_phrases"],
            features=safe_feature_metadata,
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
    if result.get("precursor"):
        p = result["precursor"]
        # Preserve field-specific evidence, confidence, and provenance with the
        # persisted precursor record. Existing evidence keys stay unchanged for
        # backwards-compatible consumers; metadata uses reserved names.
        precursor_evidence = {
            **(p.evidence or {}),
            "_field_confidence": p.field_confidence,
            "_field_methods": p.field_methods,
            "_extraction_version": p.extraction_method,
        }
        db.add(
            PrecursorTriple(
                report_id=report.id,
                activity=p.activity or "unspecified activity",
                location_asset=p.location or "unspecified location",
                barrier_failure=p.barrier_failure or "barrier not identified",
                # Evidence records the source wording; canonical taxonomy
                # values are the normalized representation used for grouping.
                original_activity=(p.evidence or {}).get("activity") or p.activity,
                original_location_asset=(p.evidence or {}).get("location") or p.location,
                original_barrier_failure=(p.evidence or {}).get("barrier_failure") or p.barrier_failure,
                normalized_activity=p.activity or "unspecified activity",
                normalized_location_asset=p.location or "unspecified location",
                normalized_barrier_failure=p.barrier_failure or "barrier not identified",
                hazard_exposure=p.hazard_exposure,
                relevant_lsr=p.relevant_lsr,
                relevant_lsr_id=p.relevant_lsr_id,
                evidence_phrase=p.evidence_phrase,
                evidence=precursor_evidence,
                confidence=p.confidence,
                extraction_method=p.extraction_method,
            )
        )
    elif result.get("triple"):
        # Fallback: legacy triple dict (activity/location_asset/barrier_failure only)
        db.add(
            PrecursorTriple(
                report_id=report.id,
                activity=result["triple"]["activity"],
                location_asset=result["triple"]["location_asset"],
                barrier_failure=result["triple"]["barrier_failure"],
                original_activity=result["triple"]["activity"],
                original_location_asset=result["triple"]["location_asset"],
                original_barrier_failure=result["triple"]["barrier_failure"],
                normalized_activity=result["triple"]["activity"],
                normalized_location_asset=result["triple"]["location_asset"],
                normalized_barrier_failure=result["triple"]["barrier_failure"],
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
                "normalized_activity": triple.normalized_activity or triple.activity,
                "normalized_location_asset": triple.normalized_location_asset or triple.location_asset,
                "normalized_barrier_failure": triple.normalized_barrier_failure or triple.barrier_failure,
                "reported_at": report.reported_at,
            }
        )
    grouped, _noise = semantic_cluster_triples(payload)
    count = 0
    for group in grouped:
        cluster = PrecursorCluster(
            semantic_cluster_key=group["semantic_cluster_key"],
            representative_activity=group["representative_activity"],
            representative_location=group["representative_location"],
            representative_barrier_failure=group["representative_barrier_failure"],
            summary=group["summary"],
            clustering_model_version=group["clustering_model_version"],
            cluster_confidence=group["cluster_confidence"],
            cluster_size=group["cluster_size"],
            trend_status=group["trend_status"],
            first_seen_at=min((_utc_timestamp(m["reported_at"]) for m in group["members"]), default=utcnow()),
            last_updated_at=max((_utc_timestamp(m["reported_at"]) for m in group["members"]), default=utcnow()),
        )
        db.add(cluster)
        db.flush()
        for member in group["members"]:
            db.add(
                ClusterMember(
                    cluster_id=cluster.id,
                    triple_id=member["triple_id"],
                    similarity=group["member_similarities"].get(member["triple_id"]),
                    clustering_model_version=group["clustering_model_version"],
                )
            )
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
    import dateutil.parser

    from app.database import SessionLocal
    from app.models import Site
    from app.recommendations import (
        generate_cluster_recommendations,
        generate_report_recommendations,
    )

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
            except Exception as exc:
                # Do not persist the input row or exception message: either can
                # contain a complete raw report or user-provided PII.
                errors.append(
                    {
                        "row_index": idx,
                        "source_report_id": str(item.get("source_report_id") or ""),
                        "error_code": type(exc).__name__,
                    }
                )

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
    except Exception as exc:
        db.rollback()
        run = db.get(IngestionRun, run_id)
        if run:
            run.status = "FAILED"
            run.error_log = [{"error_code": type(exc).__name__}]
            run.completed_at = utcnow()
            db.commit()
        return {"error": "INGESTION_BATCH_FAILED"}
    finally:
        db.close()
