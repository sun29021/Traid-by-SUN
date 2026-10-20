"""Batches end to end through the API (IMPLEMENTATION_PLAN.md Phase 12)."""

import io
import zipfile
from typing import Any

from app.db.models import AppSetting, EditJob
from tests.integration.conftest import Studio
from tests.integration.test_jobs_api import _ready_profile, _rendered


def _batch(studio: Studio, template_id: str, values: list[str], **extra: Any) -> Any:
    return studio.client.post(
        "/api/v1/batches", json={"template_job_id": template_id, "values": values, **extra}
    )


def _batch_id(studio: Studio, template_id: str, values: list[str]) -> str:
    response = _batch(studio, template_id, values)
    assert response.status_code == 202, response.text
    return str(response.json()["data"]["batch"]["id"])


def test_validate_reports_invalid_values_and_duplicates(studio: Studio) -> None:
    profile = _ready_profile(studio)
    template = _rendered(studio, profile["id"])

    response = studio.client.post(
        "/api/v1/batches/validate",
        json={
            "profile_id": profile["id"],
            "template_job_id": template["id"],
            "values": ["A7-204914", " A7-204914 ", "", "A7-2049é", "QW-1", "ZX-58"],
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["valid"] == ["A7-204914", "ZX-58"]
    assert data["duplicates"] == ["A7-204914"]
    assert {(i["value"], i["code"]) for i in data["invalid"]} == {
        ("A7-2049é", "CHAR_NOT_IN_CHARSET"),
        ("QW-1", "GLYPH_MISSING"),
    }


def test_batch_renders_every_value_and_exports_a_zip(studio: Studio) -> None:
    profile = _ready_profile(studio)
    template = _rendered(studio, profile["id"])
    response = _batch(studio, template["id"], ["A7-204915", "A7-204916", "ZX-58"], name="Run 1")
    assert response.status_code == 202, response.text
    started = response.json()["data"]
    batch_id = started["batch"]["id"]
    assert started["batch"]["total_count"] == 3
    assert started["batch"]["counts"]["pending"] == 3
    assert started["task"]["type"] == "batch_run"

    studio.run_tasks()

    batch = studio.client.get(f"/api/v1/batches/{batch_id}").json()["data"]
    assert batch["status"] == "completed" and batch["finished_at"]
    assert batch["counts"]["pending"] == 0
    items = studio.client.get(f"/api/v1/batches/{batch_id}/items").json()["data"]
    assert sorted(i["new_text"] for i in items) == ["A7-204915", "A7-204916", "ZX-58"]
    assert all(i["status"] == "rendered" and i["batch_id"] == batch_id for i in items)
    assert all(i["selected_quad"] == template["selected_quad"] for i in items)
    # Batch items stay out of the default history list.
    history = studio.client.get("/api/v1/jobs").json()["data"]
    assert batch_id not in {j["batch_id"] for j in history}

    # Same file name for every item: collisions get suffixes.
    db = studio.client.app.state.db  # type: ignore[attr-defined]
    with db.session() as session:
        session.add(AppSetting(key="export.filename_pattern", value="{template}"))
    for item in items:
        assert studio.client.post(f"/api/v1/jobs/{item['id']}/accept").status_code == 200
    export = studio.client.post(f"/api/v1/batches/{batch_id}/export")
    assert export.status_code == 202, export.text
    studio.run_tasks()

    batch = studio.client.get(f"/api/v1/batches/{batch_id}").json()["data"]
    assert batch["export_file"]["original_name"] == "Run_1.zip"
    data = studio.client.get(batch["export_file"]["url"]).content
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert sorted(archive.namelist()) == ["receipt.png", "receipt_2.png", "receipt_3.png"]


def test_create_is_idempotent_and_one_batch_runs_at_a_time(studio: Studio) -> None:
    profile = _ready_profile(studio)
    template = _rendered(studio, profile["id"])

    first = _batch(studio, template["id"], ["A7-204915"], client_request_id="abc").json()["data"]
    again = _batch(studio, template["id"], ["A7-204915"], client_request_id="abc").json()["data"]
    other = _batch(studio, template["id"], ["A7-204916"])

    assert first["batch"]["id"] == again["batch"]["id"]
    assert first["task"]["id"] == again["task"]["id"]
    assert other.status_code == 409


def test_invalid_values_block_creation(studio: Studio) -> None:
    profile = _ready_profile(studio)
    template = _rendered(studio, profile["id"])

    response = _batch(studio, template["id"], ["A7-204915", "QW-1"])

    assert response.status_code == 422
    assert response.json()["error"]["details"]["invalid"][0]["value"] == "QW-1"


def test_cancel_keeps_finished_items(studio: Studio) -> None:
    profile = _ready_profile(studio)
    template = _rendered(studio, profile["id"])
    batch_id = _batch_id(studio, template["id"], ["A7-204915", "A7-204916"])
    items = studio.client.get(f"/api/v1/batches/{batch_id}/items").json()["data"]

    # Deleting an item of a running batch is refused.
    assert studio.client.delete(f"/api/v1/jobs/{items[0]['id']}").status_code == 409

    cancelled = studio.client.post(f"/api/v1/batches/{batch_id}/cancel").json()["data"]
    assert cancelled["status"] == "cancelled"
    assert studio.client.post(f"/api/v1/batches/{batch_id}/cancel").status_code == 200
    studio.run_tasks()

    after = studio.client.get(f"/api/v1/batches/{batch_id}").json()["data"]
    assert after["status"] == "cancelled" and after["counts"]["pending"] == 2


def test_accept_passed_and_warnings_first(studio: Studio) -> None:
    profile = _ready_profile(studio)
    template = _rendered(studio, profile["id"])
    batch_id = _batch_id(studio, template["id"], ["A7-204915", "A7-204916"])
    studio.run_tasks()
    items = studio.client.get(f"/api/v1/batches/{batch_id}/items").json()["data"]
    db = studio.client.app.state.db  # type: ignore[attr-defined]
    with db.session() as session:  # the fake OCR cannot read results: mark one as passed
        job = session.get(EditJob, items[0]["id"])
        assert job is not None
        job.quality_overall = "pass"

    ordered = studio.client.get(f"/api/v1/batches/{batch_id}/items").json()["data"]
    assert ordered[-1]["id"] == items[0]["id"]  # passed items come last
    result = studio.client.post(f"/api/v1/batches/{batch_id}/accept-passed").json()["data"]

    assert result == {"accepted": 1}
    counts = studio.client.get(f"/api/v1/batches/{batch_id}").json()["data"]["counts"]
    assert counts["accepted"] == 1 and counts["warn"] == 1
