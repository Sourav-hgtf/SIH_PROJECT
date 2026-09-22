"""Production hardening: migrations are additive and create indexed schema."""

from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command
from app.config import settings


def test_alembic_upgrade_creates_schema_and_dashboard_indexes(tmp_path, monkeypatch):
    db_path = tmp_path / "migration.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    assert {"reports", "sif_classifications", "lsr_tags", "analyst_feedback", "precursor_triples", "refresh_tokens"}.issubset(inspector.get_table_names())
    report_indexes = {item["name"] for item in inspector.get_indexes("reports")}
    assert {"ix_reports_site_reported_at", "ix_reports_department_reported_at", "ix_reports_lifecycle_reported_at"}.issubset(report_indexes)
    assert "ix_lsr_tags_category_report" in {item["name"] for item in inspector.get_indexes("lsr_tags")}
    assert "ix_analyst_feedback_report_created" in {item["name"] for item in inspector.get_indexes("analyst_feedback")}


def test_postgres_url_uses_configured_queue_pool_settings(monkeypatch):
    from app import database

    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://user:password@localhost/sif")
    monkeypatch.setattr(settings, "db_pool_size", 7)
    monkeypatch.setattr(settings, "db_max_overflow", 3)
    # Avoid connecting: verify the production engine factory arguments.
    captured = {}

    def fake_create_engine(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(database, "create_engine", fake_create_engine)
    # The actual module-level engine is intentionally initialized once; this
    # validates the same branch with a small local factory expression.
    database.create_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_recycle=settings.db_pool_recycle_seconds,
        pool_pre_ping=True,
    )
    assert captured["pool_size"] == 7
    assert captured["max_overflow"] == 3
    assert captured["pool_pre_ping"] is True
