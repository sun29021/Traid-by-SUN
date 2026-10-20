import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.http_security import hostname
from app.db.engine import DB_FILENAME


def test_startup_creates_and_migrates_the_database(client: TestClient, settings: Settings) -> None:
    assert (settings.data_dir / DB_FILENAME).is_file()
    assert client.app.state.db is not None  # type: ignore[attr-defined]


def test_security_headers_on_api_responses(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("host", ["evil.example", "192.168.1.5:8765", "localhost.evil.com"])
def test_foreign_host_headers_are_rejected(client: TestClient, host: str) -> None:
    response = client.get("/api/v1/health", headers={"Host": host})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert response.headers["X-Request-ID"]


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("127.0.0.1:8765", "127.0.0.1"),
        ("LOCALHOST:5173", "localhost"),
        ("[::1]:8765", "[::1]"),
        ("localhost", "localhost"),
    ],
)
def test_hostname_parsing(header: str, expected: str) -> None:
    assert hostname(header) == expected
