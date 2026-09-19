"""Integration tests covering all previously PENDING routes from QA_CHECKLIST.md.

Covers the remaining 22 routes in the API execution matrix:
1.  GET  /v1/auth/me
2.  GET  /v1/reports/{id}/classification
3.  GET  /v1/reports/{id}/tags
4.  GET  /v1/lsr-rules
5.  GET  /v1/clusters
6.  GET  /v1/clusters/{id}
7.  GET  /v1/clusters/{id}/recommendations
8.  GET  /v1/dashboard/sites
9.  GET  /v1/dashboard/filter-options
10. GET  /v1/dashboard/sif-density
11. GET  /v1/dashboard/lsr-distribution
12. GET  /v1/dashboard/trend
13. GET  /v1/dashboard/priority-summary
14. GET  /v1/dashboard/model-health
15. GET  /v1/dashboard/error-analysis
16. GET  /v1/dashboard/model-drift
17. GET  /v1/dashboard/intervention-effectiveness
18. POST /v1/admin/training-runs
19. GET  /v1/admin/training-runs
20. POST /v1/admin/users
21. GET  /v1/admin/audit-log
22. GET  /v1/admin/priority-config
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.auth import create_token, hash_password
from app.database import SessionLocal
from app.main import app
from app.models import (
    ClusterMember,
    LsrTag,
    PrecursorCluster,
    PrecursorTriple,
    Report,
    SifClassification,
    Site,
    User,
)

client = TestClient(app)


@pytest.fixture(scope="module")
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module")
def admin_user(db_session):
    admin = db_session.query(User).filter(User.role == "admin").first()
    if not admin:
        admin = User(
            id=str(uuid.uuid4()),
            username="qa_admin",
            password_hash=hash_password("admin123"),
            role="admin",
            site_scope=[],
        )
        db_session.add(admin)
        db_session.commit()
    return admin


@pytest.fixture(scope="module")
def analyst_user(db_session):
    analyst = db_session.query(User).filter(User.role == "analyst").first()
    if not analyst:
        analyst = User(
            id=str(uuid.uuid4()),
            username="qa_analyst",
            password_hash=hash_password("analyst123"),
            role="analyst",
            site_scope=[],
        )
        db_session.add(analyst)
        db_session.commit()
    return analyst


@pytest.fixture(scope="module")
def admin_headers(admin_user):
    token = create_token(admin_user.id, "access", 60)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def analyst_headers(analyst_user):
    token = create_token(analyst_user.id, "access", 60)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def sample_report_and_cluster(db_session):
    # Ensure site
    site = db_session.query(Site).first()
    if not site:
        site = Site(id=str(uuid.uuid4()), name="QA Test Site", region="Assam")
        db_session.add(site)
        db_session.flush()

    # Ensure report with classification and LSR tag
    report = db_session.query(Report).first()
    if not report:
        report = Report(
            id=f"rep-qa-{uuid.uuid4().hex[:6]}",
            report_type="INCIDENT",
            site_id=site.id,
            department="Drilling",
            raw_text="Worker fell from elevated platform without safety harness.",
            raw_text_redacted="Worker fell from elevated platform without safety harness.",
            reported_at=datetime.now(UTC),
        )
        db_session.add(report)
        db_session.flush()

    if not report.classification:
        clf = SifClassification(
            report_id=report.id,
            sif_probability=0.88,
            sif_label=True,
            classification_state="SIF_LIKELY",
            model_version="sif-logreg-v1.0",
        )
        db_session.add(clf)
        db_session.flush()

    if not report.lsr_tags:
        tag = LsrTag(
            report_id=report.id,
            rule_id="LSR11",
            lsr_category="Working at Height",
            confidence=0.92,
            source="rules",
        )
        db_session.add(tag)
        db_session.flush()

    # Ensure cluster
    cluster = db_session.query(PrecursorCluster).first()
    if not cluster:
        cluster = PrecursorCluster(
            id=f"psc-qa-{uuid.uuid4().hex[:6]}",
            representative_activity="Working at Height",
            representative_location="Drilling Derrick",
            representative_barrier_failure="Harness not tied off",
            cluster_size=1,
            trend_status="STABLE",
            semantic_cluster_key="qa_test_cluster",
            summary="Precursor cluster for QA checklist verification.",
            clustering_model_version="precursor-dbscan-v1",
            cluster_confidence=0.95,
        )
        db_session.add(cluster)
        db_session.flush()

    db_session.commit()
    return report, cluster


# ====================================================================
# 1. AUTH ROUTE: GET /v1/auth/me
# ====================================================================
def test_route_auth_me(analyst_headers, analyst_user):
    res = client.get("/v1/auth/me", headers=analyst_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == analyst_user.id
    assert data["username"] == analyst_user.username
    assert data["role"] == analyst_user.role


# ====================================================================
# 2. REPORT ROUTES: /v1/reports/{id}/classification, /v1/reports/{id}/tags, /v1/lsr-rules
# ====================================================================
def test_route_report_classification(analyst_headers, sample_report_and_cluster):
    report, _ = sample_report_and_cluster
    res = client.get(f"/v1/reports/{report.id}/classification", headers=analyst_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["report_id"] == report.id
    assert "sif_probability" in data
    assert "sif_label" in data


def test_route_report_tags(analyst_headers, sample_report_and_cluster):
    report, _ = sample_report_and_cluster
    res = client.get(f"/v1/reports/{report.id}/tags", headers=analyst_headers)
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "lsr_category" in data[0]


def test_route_lsr_rules(analyst_headers):
    res = client.get("/v1/lsr-rules", headers=analyst_headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 12
    assert any(r["is_iogp_canonical"] is True for r in data)
    assert any(r["is_iogp_canonical"] is False for r in data)


# ====================================================================
# 3. CLUSTERS ROUTES: /v1/clusters, /v1/clusters/{id}, /v1/clusters/{id}/recommendations
# ====================================================================
def test_route_clusters_list(analyst_headers):
    res = client.get("/v1/clusters", headers=analyst_headers)
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)


def test_route_cluster_detail(analyst_headers, sample_report_and_cluster):
    _, cluster = sample_report_and_cluster
    res = client.get(f"/v1/clusters/{cluster.id}", headers=analyst_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == cluster.id
    assert "representative_activity" in data


def test_route_cluster_recommendations(analyst_headers, sample_report_and_cluster):
    _, cluster = sample_report_and_cluster
    res = client.get(f"/v1/clusters/{cluster.id}/recommendations", headers=analyst_headers)
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)


# ====================================================================
# 4. DASHBOARD ROUTES:
#    /v1/dashboard/sites, /v1/dashboard/filter-options, /v1/dashboard/sif-density,
#    /v1/dashboard/lsr-distribution, /v1/dashboard/trend, /v1/dashboard/priority-summary,
#    /v1/dashboard/model-health, /v1/dashboard/error-analysis, /v1/dashboard/model-drift,
#    /v1/dashboard/intervention-effectiveness
# ====================================================================
def test_route_dashboard_sites(analyst_headers):
    res = client.get("/v1/dashboard/sites", headers=analyst_headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_route_dashboard_filter_options(analyst_headers):
    res = client.get("/v1/dashboard/filter-options", headers=analyst_headers)
    assert res.status_code == 200
    assert "departments" in res.json()


def test_route_dashboard_sif_density(analyst_headers):
    res = client.get("/v1/dashboard/sif-density?group_by=site", headers=analyst_headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_route_dashboard_lsr_distribution(analyst_headers):
    res = client.get("/v1/dashboard/lsr-distribution", headers=analyst_headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 12


def test_route_dashboard_trend(analyst_headers):
    res = client.get("/v1/dashboard/trend?interval=week", headers=analyst_headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_route_dashboard_priority_summary(analyst_headers):
    res = client.get("/v1/dashboard/priority-summary", headers=analyst_headers)
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 4  # CRITICAL, HIGH, MEDIUM, LOW


def test_route_dashboard_model_health(analyst_headers):
    res = client.get("/v1/dashboard/model-health", headers=analyst_headers)
    assert res.status_code == 200
    data = res.json()
    assert "insufficient_data" in data
    assert "total_reviewed" in data


def test_route_dashboard_error_analysis(analyst_headers):
    res = client.get("/v1/dashboard/error-analysis", headers=analyst_headers)
    assert res.status_code == 200
    data = res.json()
    assert "false_positives" in data
    assert "false_negatives" in data


def test_route_dashboard_model_drift(analyst_headers):
    res = client.get("/v1/dashboard/model-drift", headers=analyst_headers)
    assert res.status_code == 200
    data = res.json()
    assert "versions" in data
    assert "has_regression" in data


def test_route_dashboard_intervention_effectiveness(analyst_headers):
    res = client.get("/v1/dashboard/intervention-effectiveness", headers=analyst_headers)
    assert res.status_code == 200
    data = res.json()
    assert "acceptance_rate" in data


# ====================================================================
# 5. ADMIN ROUTES:
#    /v1/admin/training-runs (POST & GET), /v1/admin/users (POST),
#    /v1/admin/audit-log (GET), /v1/admin/priority-config (GET)
# ====================================================================
def test_route_admin_training_runs_post_and_get(admin_headers):
    # POST training run (runs calibration or validates minimum confirmed cases requirement)
    post_res = client.post("/v1/admin/training-runs", headers=admin_headers)
    assert post_res.status_code in (201, 400)

    # GET training runs
    get_res = client.get("/v1/admin/training-runs", headers=admin_headers)
    assert get_res.status_code == 200
    assert isinstance(get_res.json(), list)


def test_route_admin_create_user(admin_headers):
    unique_user = f"qa_user_{uuid.uuid4().hex[:8]}"
    payload = {
        "username": unique_user,
        "password": "SecurePassword123!",
        "role": "analyst",
        "site_scope": [],
        "email": f"{unique_user}@example.com",
    }
    res = client.post("/v1/admin/users", json=payload, headers=admin_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["username"] == unique_user
    assert data["role"] == "analyst"


def test_route_admin_audit_log(admin_headers):
    res = client.get("/v1/admin/audit-log", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)


def test_route_admin_priority_config(analyst_headers):
    res = client.get("/v1/admin/priority-config", headers=analyst_headers)
    assert res.status_code == 200
    data = res.json()
    assert "tiers" in data
    assert "weights" in data
