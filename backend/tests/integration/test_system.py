from fastapi.testclient import TestClient

from app import __version__


def test_health_returns_ok_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"data": {"status": "ok", "version": __version__}}


def test_every_response_has_request_id(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert len(response.headers["X-Request-ID"]) == 32


def test_unknown_api_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]
