"""Local mode without sign-in: owner bootstrap, request guard, Acceptable Use gate."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import Settings
from app.db.engine import Database
from app.db.models import AuditEvent, User
from app.main import create_app


def _users(settings: Settings) -> list[User]:
    db = Database.from_settings(settings)
    try:
        with db.session_factory() as session:
            return list(session.scalars(select(User)).all())
    finally:
        db.dispose()


def test_startup_creates_exactly_one_local_owner(client: TestClient, settings: Settings) -> None:
    with TestClient(create_app(settings, start_worker=False)):
        pass  # second startup on the same data directory

    users = _users(settings)
    assert len(users) == 1
    assert (users[0].username, users[0].role, users[0].password_hash) == ("owner", "owner", None)
    assert users[0].display_name == "Xavier Sun"


# ---------------------------------------------------------------- request guard


def test_write_without_client_header_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/system/welcome", json={"accept_aup": True}, headers={"X-Traid-Client": ""}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_FAILED"


def test_cross_site_form_post_is_rejected(settings: Settings) -> None:
    # What a malicious page can send: a simple form post, no custom headers.
    with TestClient(create_app(settings, start_worker=False)) as bare:
        response = bare.post(
            "/api/v1/system/welcome",
            content="accept_aup=true",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://evil.example",
            },
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_FAILED"


@pytest.mark.parametrize("origin", ["https://evil.example", "null", "http://localhost:9999"])
def test_foreign_origins_are_rejected_even_for_reads(client: TestClient, origin: str) -> None:
    response = client.get("/api/v1/system/welcome", headers={"Origin": origin})

    assert response.status_code == 403


@pytest.mark.parametrize("origin", ["http://127.0.0.1:8765", "http://localhost:5173"])
def test_traid_origins_are_allowed(client: TestClient, origin: str) -> None:
    response = client.post(
        "/api/v1/system/welcome", json={"accept_aup": True}, headers={"Origin": origin}
    )

    assert response.status_code == 200


def test_reads_do_not_need_the_client_header(settings: Settings) -> None:
    with TestClient(create_app(settings, start_worker=False)) as bare:
        assert bare.get("/api/v1/health").status_code == 200


# ---------------------------------------------------------------- Acceptable Use gate


def test_aup_gate_blocks_until_accepted(client: TestClient) -> None:
    welcome = client.get("/api/v1/system/welcome").json()["data"]
    assert welcome == {"aup_accepted": False, "owner": {"display_name": "Xavier Sun"}}

    blocked = client.get("/api/v1/tasks")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["details"] == {"reason": "aup_required"}

    accepted = client.post("/api/v1/system/welcome", json={"accept_aup": True})
    assert accepted.json()["data"]["aup_accepted"] is True
    assert client.get("/api/v1/tasks").status_code == 200


def test_accept_must_be_true(client: TestClient) -> None:
    response = client.post("/api/v1/system/welcome", json={"accept_aup": False})

    assert response.status_code == 422


def test_acceptance_is_audited_once(client: TestClient, settings: Settings) -> None:
    client.post("/api/v1/system/welcome", json={"accept_aup": True})
    client.post("/api/v1/system/welcome", json={"accept_aup": True})

    db = Database.from_settings(settings)
    try:
        with db.session_factory() as session:
            count = session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "system.aup_accepted")
            )
    finally:
        db.dispose()
    assert count == 1


def test_system_status_is_available_before_acceptance(client: TestClient) -> None:
    data = client.get("/api/v1/system/status").json()["data"]

    assert data["schema_revision"] == "0004_profiles_glyphs"
    assert data["worker"] == {"running": False, "queued": 0}
    assert data["storage"]["disk_total_bytes"] > 0
    # Test settings point at an empty model folder: engine reported, but not ready.
    engine = data["engine"]
    assert (engine["ready"], engine["models"]) == (False, [])
    assert "cpu" in engine["available_devices"]
    assert engine["device"] in engine["available_devices"]


def test_system_status_lists_installed_models(settings: Settings) -> None:
    from app.core.config import REPO_ROOT

    real_models = settings.model_copy(update={"model_dir": REPO_ROOT / "models"})
    with TestClient(create_app(real_models, start_worker=False)) as client:
        engine = client.get("/api/v1/system/status").json()["data"]["engine"]

    names = {m["name"] for m in engine["models"]}
    assert names == {"ppocr-det", "ppocr-rec", "lama-inpaint"}
    if not engine["ready"]:
        pytest.skip("OCR models not installed")
    ocr = [m for m in engine["models"] if m["name"].startswith("ppocr")]
    assert all(m["present"] and m["checksum_ok"] and not m["loaded"] for m in ocr)
