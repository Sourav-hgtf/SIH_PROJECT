import logging
from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.migrations import (
    run_ingestion_migrations,
    run_labeling_migrations,
    run_lifecycle_migrations,
    run_lsr_migrations,
    run_recommendation_migrations,
)
from app.nlp.lsr import load_canonical_lsr_rules
from app.nlp.model import get_model_health_status, load_sif_model
from app.routers import (
    admin,
    auth,
    clusters,
    dashboard,
    feedback,
    ingestion,
    recommendations,
    reports,
)
from app.seed import seed_if_empty

logger = logging.getLogger(__name__)

# Run DB schema migrations
Base.metadata.create_all(bind=engine)
run_lsr_migrations(engine)
run_recommendation_migrations(engine)
run_ingestion_migrations(engine)
run_lifecycle_migrations(engine)

# Fail fast if canonical Life-Saving Rules config is missing or invalid
load_canonical_lsr_rules()

app = FastAPI(title=settings.app_name, version="0.1.0")

# Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

# CORS Middleware with strict origin control
origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if settings.app_env.lower() == "production" else (origins or ["*"]),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Router Registrations
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(reports.router, prefix=settings.api_prefix)
app.include_router(clusters.router, prefix=settings.api_prefix)
app.include_router(dashboard.router, prefix=settings.api_prefix)
app.include_router(feedback.router, prefix=settings.api_prefix)
app.include_router(admin.router, prefix=settings.api_prefix)
app.include_router(recommendations.router, prefix=settings.api_prefix)
app.include_router(ingestion.router, prefix=settings.api_prefix)


# Global Exception Handler to sanitize unexpected production errors
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled Exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    if settings.app_env.lower() == "production":
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An unexpected server error occurred."}},
        )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"code": "INTERNAL_SERVER_ERROR", "message": str(exc)}},
    )


@app.on_event("startup")
def startup():
    run_lsr_migrations(engine)
    run_recommendation_migrations(engine)
    run_ingestion_migrations(engine)
    run_lifecycle_migrations(engine)
    run_labeling_migrations(engine)
    db = SessionLocal()
    try:
        seed_if_empty(db)
        
        model_data = load_sif_model()
        if model_data.get("pipeline") is None and settings.demo_mode:
            logger.info("No model found on startup. Triggering initial training.")
            from app.training import run_ml_training
            try:
                run_ml_training(db)
            except Exception as e:
                logger.error(f"Failed to perform initial model training: {e}")
            load_sif_model()
            
    finally:
        db.close()


@app.get("/health")
def liveness():
    """Liveness check: Is the application process alive?"""
    return {"status": "ok"}


@app.get("/health/readiness")
def readiness():
    """Readiness check: Can the application safely serve production requests?"""
    db_ok = False
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        logger.error(f"Database readiness check failed: {e}")
    finally:
        db.close()

    model_health = get_model_health_status()
    is_ready = db_ok and model_health["valid"]

    status_payload = {
        "status": "ready" if is_ready else "not_ready",
        "database": "ok" if db_ok else "failed",
        "model": "ok" if model_health["artifact_exists"] else "missing",
        "model_integrity": "valid" if model_health["valid"] else "failed",
        "environment": settings.app_env,
    }

    if not is_ready:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=status_payload)

    return status_payload


@app.get("/model-info")
def model_info():
    """Model information endpoint: returns active version, calibration, threshold and integrity."""
    health = get_model_health_status()
    model_data = load_sif_model()
    opt_thresh = float(model_data.get("optimal_threshold", settings.sif_threshold))
    return {
        "model_version": model_data.get("model_version", "unknown"),
        "feature_version": model_data.get("feature_version", "tfidf-unigram-bigram-v1"),
        "preprocessing_version": model_data.get("preprocessing_version", "prep-pii-spell-abbr-v1"),
        "dataset_version": model_data.get("dataset_version", "sih-safety-ds-v1"),
        "label_schema_version": model_data.get("label_schema_version", "sif-binary-v1"),
        "calibration_version": model_data.get("calibration_version", "platt-sigmoid-v1"),
        "threshold_version": model_data.get("threshold_version", "thresh-recall-prioritized-v1"),
        "threshold": opt_thresh,
        "optimal_threshold": opt_thresh,
        "training_run_id": model_data.get("training_run_id", ""),
        "trained_at": model_data.get("trained_at"),
        "model_type": "Calibrated TF-IDF + Logistic Regression (Platt Scaling)",
        "integrity_status": health["status"],
        "artifact_exists": health["artifact_exists"],
        "manifest_exists": health["manifest_exists"],
        "sha256": health.get("sha256"),
        "status": "active" if health["valid"] else "degraded",
    }


@app.post("/predict")
def predict_adhoc(payload: dict):
    """Ad-hoc prediction endpoint for real-time safety text evaluation with calibrated probability."""
    from app.nlp.model import predict_sif_details
    text_content = payload.get("text", "")
    if not text_content:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Field 'text' is required."},
        )
    pred = predict_sif_details(text_content)
    return {
        "text": text_content,
        "processed_text": pred["processed_text"],
        "sif_probability": pred["sif_probability"],
        "sif_potential": pred["sif_potential"],
        "model_version": pred["model_version"],
        "feature_version": pred["feature_version"],
        "preprocessing_version": pred["preprocessing_version"],
        "calibration_version": pred["calibration_version"],
        "threshold_version": pred["threshold_version"],
        "threshold": pred["threshold"],
        "training_run_id": pred["training_run_id"],
    }
