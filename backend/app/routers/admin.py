from datetime import date, datetime
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import hash_password, require_roles
from app.database import get_db
from app.models import AuditLog, ModelTrainingRun, User
from app.priority.config import PriorityConfig, load_priority_config
from app.schemas import AuditLogEntry, ModelEvaluationDashboardOut, ModelEvaluationRecordOut, ModelTrainingRunOut, UserCreate, UserOut
from app.services import write_audit
from app.training import run_feedback_calibration

router = APIRouter(prefix="/admin", tags=["Admin"])


def _training_run_out(run: ModelTrainingRun) -> ModelTrainingRunOut:
    return ModelTrainingRunOut(
        id=run.id,
        model_version=run.model_version,
        feedback_count=run.feedback_count,
        metrics_before=run.metrics_before or {},
        metrics_after=run.metrics_after or {},
        created_at=run.created_at,
    )


@router.post("/training-runs", response_model=ModelTrainingRunOut, status_code=status.HTTP_201_CREATED)
def create_training_run(db: Session = Depends(get_db), admin: User = Depends(require_roles("admin"))):
    try:
        run = run_feedback_calibration(db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    write_audit(
        db,
        "model_retrained",
        "model_training_run",
        run.id,
        user_id=admin.id,
        after={"model_version": run.model_version, "feedback_count": run.feedback_count, "metrics_after": run.metrics_after},
    )
    db.commit()
    db.refresh(run)
    return _training_run_out(run)


@router.get("/model-evaluation", response_model=ModelEvaluationDashboardOut)
def get_model_evaluation_dashboard(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin", "leadership")),
):
    """Read stored model evaluation artifacts and immutable calibration runs.

    This endpoint is deliberately read-only. Model promotion/calibration remains
    admin-only at ``POST /training-runs``; normal analysts receive 403 here.
    """
    project_root = Path(__file__).resolve().parents[3]
    semantic_path = project_root / "SEMANTIC_MODEL.json"
    manifest_path = project_root / "backend" / "data" / "model_artifacts" / "model_manifest.json"
    if not semantic_path.exists():
        raise HTTPException(status_code=404, detail="Semantic model evaluation artifact is unavailable")

    semantic = json.loads(semantic_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    dataset = semantic.get("dataset", {})
    test = semantic.get("test", {})
    models = semantic.get("models", {})
    manifest_version = manifest.get("model_version")
    manifest_date = manifest.get("training_date")
    parsed_manifest_date = None
    if manifest_date:
        try:
            parsed_manifest_date = datetime.fromisoformat(manifest_date)
        except ValueError:
            parsed_manifest_date = None

    definitions = (
        ("Baseline", "rule_baseline", models.get("rule_baseline"), "EXPERIMENTAL"),
        ("TF-IDF model", "tfidf_baseline", (models.get("tfidf_baseline") or {}).get("version"), "EXPERIMENTAL"),
        ("Semantic model", "semantic_model", (models.get("semantic_model") or {}).get("version"), "EXPERIMENTAL"),
    )
    records: list[ModelEvaluationRecordOut] = []
    for name, metric_key, version, default_lifecycle in definitions:
        metrics = test.get(metric_key, {})
        # Only values contained in the artifact are presented; missing source
        # metadata intentionally stays null instead of being guessed.
        is_production = bool(version and version == manifest_version)
        records.append(
            ModelEvaluationRecordOut(
                model_name=name,
                model_version=version if isinstance(version, str) else None,
                lifecycle="PRODUCTION" if is_production else default_lifecycle,
                training_date=parsed_manifest_date if is_production else None,
                dataset_version=dataset.get("provenance") or semantic.get("evaluation_name"),
                training_samples=dataset.get("train_size"),
                validation_samples=dataset.get("val_size"),
                test_samples=dataset.get("test_size"),
                metrics={key: metrics.get(key) for key in ("precision", "recall", "f1", "accuracy", "roc_auc", "pr_auc", "specificity", "brier_score")},
                confusion_matrix=metrics.get("confusion_matrix") or {},
                calibration={key: metrics.get(key) for key in ("expected_calibration_error", "log_loss", "brier_score")},
                false_positives=metrics.get("false_positive_count"),
                false_negatives=metrics.get("false_negative_count"),
            )
        )
    for run in db.query(ModelTrainingRun).order_by(ModelTrainingRun.created_at.desc()).limit(50):
        metrics = run.metrics_after or {}
        records.append(
            ModelEvaluationRecordOut(
                model_name="Calibration candidate",
                model_version=run.model_version,
                lifecycle="PRODUCTION" if run.model_version == manifest_version else "CANDIDATE",
                training_date=run.created_at,
                dataset_version=metrics.get("dataset_version"),
                training_samples=metrics.get("train_size"),
                validation_samples=metrics.get("val_size"),
                test_samples=metrics.get("test_size"),
                metrics={key: metrics.get(key) for key in ("precision", "recall", "f1", "accuracy", "roc_auc", "pr_auc", "specificity", "brier_score")},
                confusion_matrix=metrics.get("confusion_matrix") or {},
                calibration=metrics.get("calibration_diagnostics") or {},
                false_positives=(metrics.get("confusion_matrix") or {}).get("fp"),
                false_negatives=(metrics.get("confusion_matrix") or {}).get("fn"),
            )
        )
    return ModelEvaluationDashboardOut(records=records, artifact_status="AVAILABLE")
@router.get("/training-runs", response_model=list[ModelTrainingRunOut])
def list_training_runs(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    return [_training_run_out(run) for run in db.query(ModelTrainingRun).order_by(ModelTrainingRun.created_at.desc()).limit(50).all()]


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [
        UserOut(
            id=u.id,
            username=u.username,
            role=u.role,  # type: ignore[arg-type]
            site_scope=u.site_scope or [],
            email=u.email,
            is_active=u.is_active,
        )
        for u in users
    ]


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("admin")),
):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        role=body.role,
        site_scope=body.site_scope,
        email=body.email,
    )
    db.add(user)
    db.flush()
    write_audit(db, "user_created", "user", user.id, user_id=admin.id, after={"username": user.username, "role": user.role})
    db.commit()
    db.refresh(user)
    return UserOut(
        id=user.id,
        username=user.username,
        role=user.role,  # type: ignore[arg-type]
        site_scope=user.site_scope or [],
        email=user.email,
        is_active=user.is_active,
    )


@router.get("/audit-log", response_model=list[AuditLogEntry])
def audit_log(
    user_id: str | None = None,
    action_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    q = db.query(AuditLog)
    if user_id:
        q = q.filter(AuditLog.user_id == user_id)
    if action_type:
        q = q.filter(AuditLog.action_type == action_type)
    if date_from:
        q = q.filter(func.date(AuditLog.created_at) >= date_from)
    if date_to:
        q = q.filter(func.date(AuditLog.created_at) <= date_to)
    rows = q.order_by(AuditLog.created_at.desc()).limit(500).all()
    return [
        AuditLogEntry(
            id=r.id,
            user_id=r.user_id,
            action_type=r.action_type,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            before_value=r.before_value,
            after_value=r.after_value,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/priority-config", response_model=PriorityConfig)
def get_priority_configuration(_: User = Depends(require_roles("admin", "analyst"))):
    """Returns the active Pydantic-validated priority business rules configuration."""
    return load_priority_config()
