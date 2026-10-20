from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import ErrorCode, NotFound, register_error_handlers


class _Body(BaseModel):
    name: str


def _app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/app-error")
    def app_error() -> None:
        raise NotFound("Profile not found", details={"id": "x"})

    @app.post("/validate")
    def validate(body: _Body) -> _Body:
        return body

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internals")

    return app


def test_app_error_maps_to_envelope() -> None:
    response = TestClient(_app()).get("/app-error")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == ErrorCode.NOT_FOUND
    assert error["message"] == "Profile not found"
    assert error["details"] == {"id": "x"}


def test_validation_error_lists_fields() -> None:
    response = TestClient(_app()).post("/validate", json={})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_FAILED"
    assert error["details"]["fields"][0]["path"] == "name"


def test_unexpected_error_hides_internals() -> None:
    response = TestClient(_app(), raise_server_exceptions=False).get("/boom")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret internals" not in response.text
