"""Phase 12 security regression coverage for authentication controls."""

import uuid

from fastapi.testclient import TestClient

from app.auth import hash_password
from app.database import SessionLocal
from app.main import app
from app.models import RefreshToken, Site, User
from app.routers import auth as auth_router


def test_refresh_tokens_rotate_and_reject_replay():
    db = SessionLocal()
    username = f"refresh-{uuid.uuid4().hex}"
    user = User(username=username, password_hash=hash_password("safe-password"), role="analyst")
    db.add(user)
    db.commit()
    try:
        with TestClient(app) as client:
            login = client.post("/v1/auth/login", json={"username": username, "password": "safe-password"})
            assert login.status_code == 200
            old_refresh = login.json()["refresh_token"]
            rotated = client.post("/v1/auth/refresh", json={"refresh_token": old_refresh})
            assert rotated.status_code == 200
            assert rotated.json()["refresh_token"] != old_refresh
            replay = client.post("/v1/auth/refresh", json={"refresh_token": old_refresh})
            assert replay.status_code == 401
        tokens = db.query(RefreshToken).filter(RefreshToken.user_id == user.id).all()
        assert len(tokens) == 2
        assert any(token.revoked_at for token in tokens)
        assert all("." not in token.token_hash for token in tokens)
    finally:
        db.close()


def test_login_rate_limit_returns_safe_429():
    auth_router._ATTEMPTS.clear()
    try:
        with TestClient(app) as client:
            for _ in range(10):
                assert client.post("/v1/auth/login", json={"username": "missing", "password": "wrong-password"}).status_code == 401
            blocked = client.post("/v1/auth/login", json={"username": "missing", "password": "wrong-password"})
        assert blocked.status_code == 429
        assert "Retry-After" in blocked.headers
        assert "password" not in blocked.text.lower()
    finally:
        auth_router._ATTEMPTS.clear()


def test_site_scoped_user_cannot_submit_cross_site_ingestion():
    db = SessionLocal()
    suffix = uuid.uuid4().hex
    first = Site(name=f"Scoped A {suffix}", region="A")
    second = Site(name=f"Scoped B {suffix}", region="B")
    db.add_all([first, second])
    db.flush()
    user = User(username=f"scoped-{suffix}", password_hash=hash_password("safe-password"), role="analyst", site_scope=[first.id])
    db.add(user)
    db.commit()
    try:
        from app.auth import create_token
        headers = {"Authorization": f"Bearer {create_token(user.id, 'access', 60)}"}
        with TestClient(app) as client:
            response = client.post("/v1/ingestion/confirm", headers=headers, json={"rows": [{"raw_text": "A sufficiently detailed report narrative.", "site_id": second.id}]})
        assert response.status_code == 403
        assert "assigned site" in response.json()["detail"].lower()
    finally:
        db.close()
