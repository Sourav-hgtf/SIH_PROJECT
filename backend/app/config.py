import os
import secrets

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "OIL SIF Precursor Detection API"
    app_env: str = "development"
    demo_mode: bool = True
    api_prefix: str = "/v1"
    # Local development receives a process-local key; production must provide
    # SECRET_KEY explicitly and never inherits a source-controlled secret.
    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(48))
    access_token_expire_minutes: int = 480
    database_url: str = "sqlite:///./sif_sentinel.db"
    sif_threshold: float = 0.45
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    max_upload_size_mb: int = 10
    max_upload_rows: int = 5000
    model_manifest_path: str = "data/model_artifacts/model_manifest.json"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.app_env.lower() == "production":
            if not os.environ.get("SECRET_KEY") or len(self.secret_key) < 32:
                raise ValueError("In production, SECRET_KEY must be supplied via the environment and be at least 32 characters.")
            if self.demo_mode:
                raise ValueError("DEMO_MODE must be False in production environment.")
        return self


settings = Settings()
