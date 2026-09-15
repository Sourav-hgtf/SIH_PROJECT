"""No stack trace exposure and request-correlation response contracts."""

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.main import app


def test_request_id_is_returned_on_normal_requests():
    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Request-ID": "trace-phase-11"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "trace-phase-11"


def test_unexpected_error_never_exposes_stack_trace():
    router = APIRouter()

    @router.get("/_test-hardening-error")
    def test_error_route():
        raise RuntimeError("internal-only diagnostic details")

    app.include_router(router)
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/_test-hardening-error", headers={"X-Request-ID": "trace-error"})
        assert response.status_code == 500
        assert response.headers["X-Request-ID"] == "trace-error"
        assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
        assert "internal-only" not in response.text
    finally:
        app.router.routes.pop()
