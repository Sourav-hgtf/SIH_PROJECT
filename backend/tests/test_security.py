import hashlib
import json

from fastapi.testclient import TestClient

from app.auth import create_token, hash_password
from app.database import SessionLocal
from app.main import app
from app.models import User
from app.nlp import model as nlp_model

client = TestClient(app)


def test_unauthenticated_access_denied():
    res = client.get("/v1/dashboard/kpis")
    assert res.status_code == 401


def test_predict_requires_authentication():
    res = client.post("/predict", json={"text": "Worker entered a confined space without gas testing."})
    assert res.status_code in (401, 403)


def test_invalid_jwt_token_denied():
    res = client.get("/v1/dashboard/kpis", headers={"Authorization": "Bearer invalid.jwt.token"})
    assert res.status_code == 401


def test_expired_jwt_token_denied():
    token = create_token("user-id-123", "access", minutes=-10)
    res = client.get("/v1/dashboard/kpis", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


def test_rbac_analyst_blocked_from_admin_route():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.role == "analyst").first()
        if not user:
            user = User(username="analyst_test", password_hash=hash_password("pass"), role="analyst")
            db.add(user)
            db.commit()

        token = create_token(user.id, "access", minutes=60)
        res = client.get("/v1/admin/users", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 403
    finally:
        db.close()


def test_path_traversal_and_file_format_rejection():
    db = SessionLocal()
    try:
        admin_user = db.query(User).filter(User.role == "admin").first()
        if not admin_user:
            admin_user = User(username="admin_test_sec", password_hash=hash_password("pass"), role="admin")
            db.add(admin_user)
            db.commit()
        token = create_token(admin_user.id, "access", minutes=60)

        # Test invalid extension
        res = client.post(
            "/v1/ingestion/validate-file",
            files={"file": ("../../etc/passwd.txt", b"malicious content", "text/plain")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 400
        assert "Unsupported file format" in res.json()["detail"]
    finally:
        db.close()


def test_oversized_file_upload_rejection():
    db = SessionLocal()
    try:
        admin_user = db.query(User).filter(User.role == "admin").first()
        if not admin_user:
            admin_user = User(username="admin_test_sec2", password_hash=hash_password("pass"), role="admin")
            db.add(admin_user)
            db.commit()
        token = create_token(admin_user.id, "access", minutes=60)

        # Create dummy 11MB file
        large_content = b"a" * (11 * 1024 * 1024)
        res = client.post(
            "/v1/ingestion/validate-file",
            files={"file": ("large.csv", large_content, "text/csv")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 400
        assert "exceeds maximum allowed limit" in res.json()["detail"]
    finally:
        db.close()


def test_model_integrity_verification_success_and_failure(tmp_path, monkeypatch):
    # Setup dummy model & manifest in temp directory
    test_artifact = tmp_path / "sif_model.joblib"
    test_manifest = tmp_path / "model_manifest.json"

    dummy_bytes = b"dummy scikit learn model artifact bytes"
    test_artifact.write_bytes(dummy_bytes)

    correct_hash = hashlib.sha256(dummy_bytes).hexdigest()
    test_manifest.write_text(json.dumps({"model_file": "sif_model.joblib", "sha256": correct_hash}))

    monkeypatch.setattr(nlp_model, "ARTIFACT_PATH", test_artifact)
    monkeypatch.setattr(nlp_model, "MANIFEST_PATH", test_manifest)

    # Valid integrity check
    valid, status = nlp_model.verify_model_integrity()
    assert valid is True
    assert status == "MODEL_INTEGRITY_VALID"

    # Modify model file to trigger integrity failure
    test_artifact.write_bytes(b"tampered content")
    valid_corrupt, status_corrupt = nlp_model.verify_model_integrity()
    assert valid_corrupt is False
    assert status_corrupt == "MODEL_INTEGRITY_FAILED"


def test_health_and_readiness_endpoints():
    liveness_res = client.get("/health")
    assert liveness_res.status_code == 200
    assert liveness_res.json()["status"] == "ok"

    readiness_res = client.get("/health/readiness")
    assert readiness_res.status_code in (200, 503)
    data = readiness_res.json()
    assert "database" in data
    assert "model_integrity" in data


def test_admin_user_management_crud_and_audit():
    db = SessionLocal()
    try:
        admin_user = db.query(User).filter(User.role == "admin").first()
        if not admin_user:
            admin_user = User(username="admin_test_mgr", password_hash=hash_password("admin123"), role="admin")
            db.add(admin_user)
            db.commit()
        admin_token = create_token(admin_user.id, "access", minutes=60)
        auth_header = {"Authorization": f"Bearer {admin_token}"}

        # 1. Create a user
        create_res = client.post(
            "/v1/admin/users",
            json={
                "username": "test_field_lead",
                "password": "password123",
                "role": "site_manager",
                "site_scope": ["Duliajan GCS"],
                "email": "lead@oilindia.example",
            },
            headers=auth_header,
        )
        assert create_res.status_code == 201
        created_data = create_res.json()
        user_id = created_data["id"]
        assert created_data["username"] == "test_field_lead"
        assert created_data["role"] == "site_manager"
        assert created_data["site_scope"] == ["Duliajan GCS"]

        # 2. Update user role and site_scope
        update_res = client.patch(
            f"/v1/admin/users/{user_id}",
            json={
                "role": "analyst",
                "site_scope": ["Duliajan GCS", "Digboi Refinery Area"],
                "email": "analyst.lead@oilindia.example",
            },
            headers=auth_header,
        )
        assert update_res.status_code == 200
        updated_data = update_res.json()
        assert updated_data["role"] == "analyst"
        assert len(updated_data["site_scope"]) == 2

        # 3. Toggle active status
        toggle_res = client.post(
            f"/v1/admin/users/{user_id}/toggle-active",
            json={"is_active": False},
            headers=auth_header,
        )
        assert toggle_res.status_code == 200
        assert toggle_res.json()["is_active"] is False

        # 4. Self-deactivation and self-deletion protections
        self_toggle = client.post(
            f"/v1/admin/users/{admin_user.id}/toggle-active",
            json={"is_active": False},
            headers=auth_header,
        )
        assert self_toggle.status_code == 400
        assert "Cannot deactivate your own" in self_toggle.json()["detail"]

        self_delete = client.delete(f"/v1/admin/users/{admin_user.id}", headers=auth_header)
        assert self_delete.status_code == 400
        assert "Cannot delete your own" in self_delete.json()["detail"]

        # 5. Delete created user
        delete_res = client.delete(f"/v1/admin/users/{user_id}", headers=auth_header)
        assert delete_res.status_code == 200

        # Verify user is deleted
        get_users = client.get("/v1/admin/users", headers=auth_header)
        assert not any(u["id"] == user_id for u in get_users.json())
    finally:
        db.close()

