from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import APIError, ErrorCode, register_exception_handlers


class Body(BaseModel):
    amount: int


def build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/conflict")
    def conflict() -> None:
        raise APIError(409, ErrorCode.CONFLICT, "Already registered.", {"field": "channel"})

    @app.get("/missing")
    def missing() -> None:
        raise HTTPException(status_code=404, detail="No such service.")

    @app.post("/amount")
    def amount(body: Body) -> dict:
        return {"amount": body.amount}

    @app.get("/crash")
    def crash() -> None:
        raise RuntimeError("boom with a secret token=abc123")

    @app.get("/limited")
    def limited() -> None:
        raise APIError(
            429,
            ErrorCode.RATE_LIMITED,
            "Too many requests.",
            headers={"Retry-After": "30"},
        )

    return app


def test_api_error_uses_envelope() -> None:
    client = TestClient(build_app())
    response = client.get("/conflict")
    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "conflict",
            "message": "Already registered.",
            "details": {"field": "channel"},
        }
    }


def test_http_exception_maps_to_code() -> None:
    response = TestClient(build_app()).get("/missing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_rate_limit_headers_survive() -> None:
    response = TestClient(build_app()).get("/limited")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"
    assert response.json()["error"]["code"] == "rate_limited"


def test_validation_error_does_not_echo_input() -> None:
    response = TestClient(build_app()).post("/amount", json={"amount": "not-a-number"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_failed"
    assert "fields" in body["error"]["details"]
    assert "not-a-number" not in response.text


def test_unhandled_error_hides_details() -> None:
    client = TestClient(build_app(), raise_server_exceptions=False)
    response = client.get("/crash")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "abc123" not in response.text
    assert "Traceback" not in response.text
