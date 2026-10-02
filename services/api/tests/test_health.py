from fastapi.testclient import TestClient
from helpers import make_settings

from app.main import create_app


def test_health_answers() -> None:
    with TestClient(create_app(make_settings())) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/healthz").json() == {"status": "ok"}


def test_security_headers_are_present() -> None:
    with TestClient(create_app(make_settings())) as client:
        response = client.get("/health")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        # No HSTS in local development.
        assert "Strict-Transport-Security" not in response.headers


def test_production_emits_hsts() -> None:
    settings = make_settings(
        environment="production",
        session_secret="a-real-session-secret",
        recovery_code_pepper="a-real-pepper",
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")
        assert "Strict-Transport-Security" in response.headers


def test_correlation_id_is_echoed() -> None:
    with TestClient(create_app(make_settings())) as client:
        response = client.get("/health", headers={"X-Request-ID": "req-123"})
        assert response.headers["X-Request-ID"] == "req-123"


def test_unknown_route_uses_the_error_envelope() -> None:
    with TestClient(create_app(make_settings())) as client:
        response = client.get("/v1/does-not-exist")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


def test_openapi_is_served() -> None:
    with TestClient(create_app(make_settings())) as client:
        assert client.get("/openapi.json").status_code == 200
