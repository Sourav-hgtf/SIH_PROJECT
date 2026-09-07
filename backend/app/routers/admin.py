from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import hash_password, require_roles
from app.database import get_db
from app.models import AuditLog, ModelTrainingRun, User
from app.priority.config import PriorityConfig, load_priority_config
from app.schemas import AuditLogEntry, ModelTrainingRunOut, UserCreate, UserOut
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


@router.get("/model-evaluation", response_model=ModelTrainingRunOut)
def get_latest_model_evaluation(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    run = db.query(ModelTrainingRun).order_by(ModelTrainingRun.created_at.desc()).first()
    if not run:
        raise HTTPException(status_code=404, detail="No model training runs found")
    return ModelTrainingRunOut(
        id=run.id,
        model_version=run.model_version,
        feedback_count=run.feedback_count,
        metrics_before=run.metrics_before or {},
        metrics_after=run.metrics_after or {},
        created_at=run.created_at,
    )
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
