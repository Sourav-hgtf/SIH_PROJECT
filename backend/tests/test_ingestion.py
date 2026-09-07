import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_token
from app.database import Base, get_db
from app.main import app
from app.models import Report, Site, User, utcnow
from app.services import process_ingestion_batch, log_ingestion_run

from sqlalchemy.pool import StaticPool

TEST_DB_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module")
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    site1 = Site(id="site-ingest-1", name="Alpha Platform", region="Gulf")
    site2 = Site(id="site-ingest-2", name="Beta Refinery", region="Coast")
    db.add_all([site1, site2])
    admin = User(
        id="user-admin-1",
        username="admin_user",
        password_hash="hash",
        role="admin",
        site_scope=[],
    )
    db.add(admin)
    existing_rep = Report(
        id="rep-exist-1",
        source_report_id="EXISTING-001",
        report_type="near_miss",
        site_id="site-ingest-1",
        raw_text_redacted="Existing incident description for testing duplicates.",
        reported_at=utcnow(),
    )
    db.add(existing_rep)
    db.commit()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="module")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def admin_headers(db_session):
    token = create_token("user-admin-1", "access", 60)
    return {"Authorization": f"Bearer {token}"}


def test_validate_csv_file(client, admin_headers):
    csv_data = (
        "source_report_id,reported_at,site_name,department,shift,equipment_type,job_type,report_type,raw_text\n"
        "NEW-001,2026-03-01T08:30:00Z,Alpha Platform,Drilling,Day,BOP Stack,Well Operations,near_miss,\"High pressure gas leak observed at BOP flange. Contact John Doe at 9876543210 or email john@example.com for details.\"\n"
        "EXISTING-001,2026-03-01T10:00:00Z,Beta Refinery,Maintenance,Day,Crane,Lifting,incident,\"Heavy lifting load slipped from sling on deck.\"\n"
        "NEW-002,2026-03-01T12:00:00Z,Unknown Site,Electrical,Night,Transformer,Maintenance,ua_uc,\"Short\"\n"
    )
    files = {"file": ("test_reports.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
    resp = client.post("/v1/ingestion/validate-file", files=files, headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_rows"] == 3
    assert data["valid_rows"] == 2  # Row 3 is < 10 chars (invalid)
    assert data["invalid_rows"] == 1
    assert data["duplicate_rows"] == 1  # EXISTING-001 is duplicate
    assert data["pii_total_redactions"] >= 1  # John Doe, phone, email
    assert data["data_quality_score"] > 0
    assert len(data["preview_rows"]) == 3


def test_validate_json_payload(client, admin_headers):
    payload = [
        {
            "source_report_id": "JSON-001",
            "report_type": "near_miss",
            "site_name": "Alpha Platform",
            "department": "Drilling",
            "raw_text": "Scaffold worker detached safety harness while working 15 meters above ground.",
            "reported_at": "2026-03-02T10:00:00Z",
        }
    ]
    resp = client.post("/v1/ingestion/validate-json", json=payload, headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_rows"] == 1
    assert data["valid_rows"] == 1
    assert data["duplicate_rows"] == 0
    assert data["data_quality_score"] > 80.0


def test_confirm_ingestion_and_processing(client, admin_headers, db_session):
    payload = {
        "source_name": "Unit Test Import",
        "rows": [
            {
                "source_report_id": "BATCH-001",
                "report_type": "incident",
                "site_name": "Alpha Platform",
                "department": "Production",
                "equipment_type": "Flare Tip",
                "job_type": "Hot Work",
                "raw_text": "Worker sustained minor burn during torch ignition without proper face shield.",
                "reported_at": "2026-03-03T11:00:00Z",
            }
        ],
    }
    resp = client.post("/v1/ingestion/confirm", json=payload, headers=admin_headers)
    assert resp.status_code == 202
    job = resp.json()
    assert job["id"] is not None
    assert job["record_count"] == 1

    # Check job status endpoint
    status_resp = client.get(f"/v1/ingestion/jobs/{job['id']}", headers=admin_headers)
    assert status_resp.status_code == 200


def test_download_template(client):
    resp = client.get("/v1/ingestion/template")
    assert resp.status_code == 200
    assert "source_report_id" in resp.text
    assert "raw_text" in resp.text
