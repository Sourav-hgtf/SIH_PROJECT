import csv
import io
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.database import get_db
from app.models import IngestionRun, Report, Site, User
from app.nlp.preprocess import redact_pii
from app.schemas import (
    IngestionConfirmRequest,
    IngestionJobOut,
    IngestionQualityReport,
    ReportUploadItem,
    ValidatedRowPreview,
    ValidationIssue,
)
from app.services import log_ingestion_run, process_ingestion_batch

router = APIRouter(prefix="/ingestion", tags=["Ingestion"])
logger = logging.getLogger(__name__)

# Column name mapping aliases
COLUMN_ALIASES = {
    "raw_text": ["raw_text", "description", "incident_description", "event_description", "narrative", "text", "incident_details", "details", "summary"],
    "source_report_id": ["source_report_id", "report_id", "id", "incident_id", "event_id", "reference_no", "ref_no"],
    "site_name": ["site_name", "site", "location", "facility", "plant", "asset_location"],
    "site_id": ["site_id"],
    "report_type": ["report_type", "type", "event_type", "incident_type", "classification", "category"],
    "department": ["department", "dept", "section", "area", "division"],
    "shift": ["shift", "shift_time", "work_shift"],
    "equipment_type": ["equipment_type", "equipment", "asset", "machinery", "system"],
    "job_type": ["job_type", "activity", "task", "operation", "work_type"],
    "reported_at": ["reported_at", "date", "incident_date", "event_date", "timestamp", "date_time", "occurrence_date"],
}


def _normalize_row_keys(row: dict[str, Any]) -> dict[str, Any]:
    """Map flexible header names to canonical schema fields."""
    normalized: dict[str, Any] = {}
    row_lower = {str(k).strip().lower().replace(" ", "_"): v for k, v in row.items()}

    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in row_lower and row_lower[alias] is not None:
                val = row_lower[alias]
                if isinstance(val, str):
                    val = val.strip()
                if val != "":
                    normalized[canonical] = val
                    break

    # If raw_text wasn't mapped, check if any column contains multi-word description
    if "raw_text" not in normalized:
        for k, v in row.items():
            if isinstance(v, str) and len(v.split()) >= 4:
                normalized["raw_text"] = v.strip()
                break

    return normalized


def _analyze_rows(rows: list[dict[str, Any]], db: Session) -> IngestionQualityReport:
    """Perform schema validation, duplicate detection, PII extraction, and data quality scoring."""
    existing_ids = {r[0] for r in db.query(Report.source_report_id).all() if r[0]}
    all_sites = db.query(Site).all()
    site_names = {s.name.lower().strip(): s.id for s in all_sites}
    site_ids = {s.id for s in all_sites}

    total = len(rows)
    valid_count = 0
    duplicate_count = 0
    total_pii = 0
    previews: list[ValidatedRowPreview] = []

    issues_tally: dict[str, int] = {}
    field_counts: dict[str, int] = {k: 0 for k in COLUMN_ALIASES.keys()}

    seen_ids_in_batch = set()

    for idx, raw_row in enumerate(rows):
        normalized = _normalize_row_keys(raw_row)
        issues: list[ValidationIssue] = []
        is_valid = True
        is_duplicate = False

        # Check raw_text
        text = str(normalized.get("raw_text") or "").strip()
        if not text:
            is_valid = False
            issues.append(ValidationIssue(field="raw_text", severity="error", message="Missing incident description (raw_text)"))
            issues_tally["missing_raw_text"] = issues_tally.get("missing_raw_text", 0) + 1
        elif len(text) < 10:
            is_valid = False
            issues.append(ValidationIssue(field="raw_text", severity="error", message="Incident description is too brief (< 10 chars)"))
            issues_tally["short_raw_text"] = issues_tally.get("short_raw_text", 0) + 1
        else:
            field_counts["raw_text"] += 1

        # PII Detection
        pii_redacted, pii_count = redact_pii(text) if text else ("", 0)
        total_pii += pii_count
        if pii_count > 0:
            issues.append(ValidationIssue(field="raw_text", severity="info", message=f"Detected {pii_count} PII entity/entities (will be auto-redacted)"))
            issues_tally["pii_redacted"] = issues_tally.get("pii_redacted", 0) + pii_count

        # Source Report ID & duplicate check
        source_id = normalized.get("source_report_id")
        if source_id:
            field_counts["source_report_id"] += 1
            if source_id in existing_ids or source_id in seen_ids_in_batch:
                is_duplicate = True
                duplicate_count += 1
                issues.append(ValidationIssue(field="source_report_id", severity="warning", message=f"Duplicate report ID '{source_id}' already exists in database or batch"))
                issues_tally["duplicate_id"] = issues_tally.get("duplicate_id", 0) + 1
            seen_ids_in_batch.add(source_id)
        else:
            issues.append(ValidationIssue(field="source_report_id", severity="info", message="No report ID supplied; system will generate one"))

        # Site Check
        site_id = normalized.get("site_id")
        site_name = normalized.get("site_name")
        if site_id and site_id in site_ids:
            field_counts["site_id"] += 1
        elif site_name and site_name.lower().strip() in site_names:
            field_counts["site_name"] += 1
            normalized["site_id"] = site_names[site_name.lower().strip()]
        else:
            issues.append(ValidationIssue(field="site", severity="warning", message="Unrecognized or missing site; will default to primary site"))
            issues_tally["unmatched_site"] = issues_tally.get("unmatched_site", 0) + 1

        # Date Check
        rep_date = normalized.get("reported_at")
        if rep_date:
            field_counts["reported_at"] += 1
        else:
            issues.append(ValidationIssue(field="reported_at", severity="info", message="Missing reported_at timestamp; will default to current timestamp"))

        # Check optional fields completeness
        for f in ["department", "shift", "equipment_type", "job_type", "report_type"]:
            if normalized.get(f):
                field_counts[f] += 1

        if is_valid:
            valid_count += 1

        # Keep preview rows for UI (first 25 rows)
        if idx < 25:
            previews.append(
                ValidatedRowPreview(
                    row_index=idx + 1,
                    is_valid=is_valid,
                    is_duplicate=is_duplicate,
                    data=normalized,
                    pii_redacted_text=pii_redacted[:150] + ("..." if len(pii_redacted) > 150 else ""),
                    pii_count=pii_count,
                    issues=issues,
                )
            )

    # Calculate Data Quality Score (0 - 100)
    if total > 0:
        raw_text_score = (field_counts["raw_text"] / total) * 40.0
        site_score = (min(total, field_counts["site_name"] + field_counts["site_id"]) / total) * 20.0
        date_score = (field_counts["reported_at"] / total) * 15.0
        details_score = (
            (field_counts["department"] + field_counts["equipment_type"] + field_counts["job_type"]) / (total * 3.0)
        ) * 15.0
        duplicate_penalty = (duplicate_count / total) * 10.0
        dq_score = max(0.0, min(100.0, round(raw_text_score + site_score + date_score + details_score + (10.0 - duplicate_penalty), 1)))
        completeness = {k: round((v / total) * 100.0, 1) for k, v in field_counts.items()}
    else:
        dq_score = 0.0
        completeness = {}

    return IngestionQualityReport(
        total_rows=total,
        valid_rows=valid_count,
        invalid_rows=total - valid_count,
        duplicate_rows=duplicate_count,
        pii_total_redactions=total_pii,
        data_quality_score=dq_score,
        completeness_breakdown=completeness,
        issues_summary=issues_tally,
        preview_rows=previews,
    )


@router.post("/validate-file", response_model=IngestionQualityReport)
async def validate_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "analyst", "site_manager")),
):
    """Parses and validates an uploaded CSV or JSON file without writing to the database."""
    from app.config import settings
    import os

    # Sanitize filename & path traversal check
    raw_filename = file.filename or ""
    safe_filename = os.path.basename(raw_filename.replace("\\", "/")).lower()
    if "/" in raw_filename or "\\" in raw_filename or ".." in raw_filename:
        logger.warning(f"Path traversal attempt detected in uploaded filename: {raw_filename}")

    if not (safe_filename.endswith(".csv") or safe_filename.endswith(".json")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Only .csv and .json files are allowed.",
        )

    content = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds maximum allowed limit of {settings.max_upload_size_mb}MB.",
        )

    rows: list[dict[str, Any]] = []

    if safe_filename.endswith(".json"):
        try:
            parsed = json.loads(content.decode("utf-8"))
            if isinstance(parsed, list):
                rows = parsed
            elif isinstance(parsed, dict) and "reports" in parsed:
                rows = parsed["reports"]
            elif isinstance(parsed, dict) and "data" in parsed:
                rows = parsed["data"]
            else:
                rows = [parsed]
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid JSON format in uploaded file")
    else:
        # Default CSV parse
        try:
            text_data = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text_data = content.decode("latin-1")
            except Exception:
                raise HTTPException(status_code=400, detail="Unable to decode file text encoding")

        sample = text_data[:2048]
        delimiter = ","
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
            delimiter = dialect.delimiter
        except Exception:
            pass

        reader = csv.DictReader(io.StringIO(text_data), delimiter=delimiter)
        for row in reader:
            rows.append(dict(row))

    if not rows:
        raise HTTPException(status_code=400, detail="Uploaded file contains no data rows.")

    if len(rows) > settings.max_upload_rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Batch size exceeds maximum limit of {settings.max_upload_rows} rows per file.",
        )

    return _analyze_rows(rows, db)



@router.post("/validate-json", response_model=IngestionQualityReport)
def validate_json_rows(
    payload: list[ReportUploadItem],
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "analyst", "site_manager")),
):
    """Validates raw JSON items."""
    rows = [item.model_dump() for item in payload]
    if not rows:
        raise HTTPException(status_code=400, detail="Empty rows payload")
    return _analyze_rows(rows, db)


@router.post("/confirm", response_model=IngestionJobOut, status_code=status.HTTP_202_ACCEPTED)
def confirm_ingestion(
    body: IngestionConfirmRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "analyst", "site_manager")),
):
    """Enqueues confirmed rows for asynchronous processing."""
    if not body.rows:
        raise HTTPException(status_code=400, detail="No rows supplied for ingestion.")

    # Create IngestionRun record
    run = log_ingestion_run(
        db,
        source=body.source_name,
        record_count=len(body.rows),
        status="PENDING",
    )
    db.commit()

    rows_dict = [r.model_dump() for r in body.rows]
    if body.default_site_id:
        for r in rows_dict:
            if not r.get("site_id"):
                r["site_id"] = body.default_site_id

    # Enqueue background task
    background_tasks.add_task(process_ingestion_batch, run.id, rows_dict, user.id)

    return IngestionJobOut(
        id=run.id,
        source=run.source,
        record_count=run.record_count,
        processed_count=run.processed_count,
        status=run.status,
        error_log=run.error_log,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


@router.get("/jobs", response_model=list[IngestionJobOut])
def list_jobs(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Lists recent ingestion jobs."""
    runs = db.query(IngestionRun).order_by(IngestionRun.created_at.desc()).limit(limit).all()
    return [
        IngestionJobOut(
            id=r.id,
            source=r.source,
            record_count=r.record_count,
            processed_count=r.processed_count or 0,
            status=r.status or "COMPLETED",
            error_log=r.error_log,
            created_at=r.created_at,
            completed_at=r.completed_at,
        )
        for r in runs
    ]


@router.get("/jobs/{job_id}", response_model=IngestionJobOut)
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retrieves status for an ingestion job."""
    run = db.get(IngestionRun, job_id)
    if not run:
        raise HTTPException(status_code=404, detail="Ingestion job not found")

    return IngestionJobOut(
        id=run.id,
        source=run.source,
        record_count=run.record_count,
        processed_count=run.processed_count or 0,
        status=run.status or "COMPLETED",
        error_log=run.error_log,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


@router.get("/template")
def download_sample_template():
    """Returns sample CSV template for HSE ingestion."""
    csv_content = (
        "source_report_id,reported_at,site_name,department,shift,equipment_type,job_type,report_type,raw_text\n"
        "INC-2026-001,2026-03-01T08:30:00Z,Alpha Platform,Drilling,Day,BOP Stack,Well Operations,near_miss,\"Technician observed high pressure hydraulic fluid spraying from BOP accumulator valve during pre-tour check. Emergency isolation activated.\"\n"
        "INC-2026-002,2026-03-01T14:15:00Z,Beta Refinery,Maintenance,Day,Scaffolding,Working at Height,ua_uc,\"Worker on level 4 scaffolding unclipped harness lanyard while reaching across handrail to adjust temporary lighting.\"\n"
        "INC-2026-003,2026-03-02T22:00:00Z,Gamma Terminal,Logistics,Night,Forklift,Material Handling,near_miss,\"Forklift operator reversed around blind corner at high speed, nearly striking pedestrian technician in designated walkway.\"\n"
    )
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=hse_report_ingestion_template.csv"},
    )
