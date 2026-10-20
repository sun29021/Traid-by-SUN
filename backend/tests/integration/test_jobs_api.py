"""Edit jobs end to end through the API (IMPLEMENTATION_PLAN.md Phase 9)."""

import io
from typing import Any

import numpy as np
import pytest
from PIL import Image

from app.db.models import AppSetting, Glyph
from tests.factories import png_bytes
from tests.fixtures.generate import make_token_image
from tests.integration.conftest import Studio

TOKEN = "A7-204913"
REFERENCE_TEXTS = ("0123456789", "A7-204913", "ZX-58BK")


def _ready_profile(studio: Studio, **fields: Any) -> dict[str, Any]:
    profile = studio.create_profile(ready_threshold=1, **fields)
    files = [
        (f"ref{i}.png", studio.token_png(text, seed=40 + i))
        for i, text in enumerate(REFERENCE_TEXTS)
    ]
    assert studio.upload(profile["id"], *files).status_code == 202
    studio.run_tasks()
    glyphs = studio.client.get(f"/api/v1/profiles/{profile['id']}/glyphs?limit=200").json()
    ids = [g["id"] for g in glyphs["data"]]
    response = studio.client.post(
        f"/api/v1/profiles/{profile['id']}/glyphs/bulk", json={"ids": ids, "action": "confirm"}
    )
    assert response.status_code == 200, response.text
    return profile


def _create_job(studio: Studio, profile_id: str, text: str = TOKEN, seed: int = 8) -> Any:
    response = studio.client.post(
        "/api/v1/jobs",
        data={"profile_id": profile_id},
        files={"file": ("receipt.png", studio.token_png(text, seed=seed), "image/png")},
    )
    assert response.status_code == 202, response.text
    return response.json()["data"]


def _job(studio: Studio, job_id: str) -> dict[str, Any]:
    response = studio.client.get(f"/api/v1/jobs/{job_id}")
    assert response.status_code == 200, response.text
    data: dict[str, Any] = response.json()["data"]
    return data


def _detected(studio: Studio, profile_id: str, **kwargs: Any) -> dict[str, Any]:
    created = _create_job(studio, profile_id, **kwargs)
    studio.run_tasks()
    return _job(studio, created["job"]["id"])


def _rendered(studio: Studio, profile_id: str, new_text: str = "A7-204914") -> dict[str, Any]:
    job = _detected(studio, profile_id)
    response = studio.client.post(f"/api/v1/jobs/{job['id']}/render", json={"new_text": new_text})
    assert response.status_code == 202, response.text
    studio.run_tasks()
    return _job(studio, job["id"])


def _download(studio: Studio, url: str) -> bytes:
    response = studio.client.get(url)
    assert response.status_code == 200
    return response.content


# ---------------------------------------------------------------- the happy path


def test_upload_detect_render_accept_export(studio: Studio) -> None:
    profile = _ready_profile(studio)
    created = _create_job(studio, profile["id"])
    assert created["job"]["status"] == "uploaded"
    assert created["task"]["type"] == "detect"

    studio.run_tasks()
    job = _job(studio, created["job"]["id"])
    assert job["status"] == "detected"
    assert job["selected_region_id"] == "r1"
    assert job["original_text"] == TOKEN
    assert job["regions"][0]["text"] == TOKEN

    render = studio.client.post(f"/api/v1/jobs/{job['id']}/render", json={"new_text": "A7-204914"})
    assert render.status_code == 202
    assert render.json()["data"]["type"] == "render"
    assert _job(studio, job["id"])["status"] == "rendering"
    studio.run_tasks()

    job = _job(studio, job["id"])
    assert job["status"] == "rendered", job["error_code"]
    assert job["new_text"] == "A7-204914"
    assert job["layout_mode"] == "slots"
    assert [u["source"] for u in job["glyphs_used"]].count("kept") == 8
    assert job["engine_version"] == "glyph_transplant@1.0.0"
    assert {c["id"] for c in job["quality"]["checks"]} >= {"seam", "outside_unchanged"}
    assert job["result"]["mime_type"] == "image/png"

    accepted = studio.client.post(f"/api/v1/jobs/{job['id']}/accept").json()["data"]
    assert accepted["status"] == "accepted" and accepted["accepted_at"]
    again = studio.client.post(f"/api/v1/jobs/{job['id']}/accept")
    assert again.status_code == 200  # idempotent

    export = studio.client.post(f"/api/v1/jobs/{job['id']}/export", json={})
    assert export.status_code == 201, export.text
    out = export.json()["data"]
    assert out["download_name"] == "receipt_A7-204914.png"
    data = _download(studio, out["file"]["url"])
    with Image.open(io.BytesIO(data)) as image:
        assert image.info.get("Software", "").startswith("Traid")
        exported = np.asarray(image.convert("RGB"))
    original = make_token_image(TOKEN, "print", seed=8).image
    mask = np.asarray(Image.open(io.BytesIO(_download(studio, job["mask"]["url"]))))[..., 0] > 0
    assert exported.shape == original.shape
    assert np.array_equal(exported[~mask], original[~mask])  # PNG: bit-identical outside
    assert not np.array_equal(exported[mask], original[mask])

    events = studio.client.get("/api/v1/audit").json()["data"]
    assert {"job.accepted", "job.exported"} <= {e["action"] for e in events}


def test_accept_counts_bank_glyph_usage(studio: Studio) -> None:
    profile = _ready_profile(studio)
    job = _rendered(studio, profile["id"], "ZX-58")
    bank_ids = [u["glyph_id"] for u in job["glyphs_used"] if u["source"] == "bank"]
    assert bank_ids

    studio.client.post(f"/api/v1/jobs/{job['id']}/accept")

    db = studio.client.app.state.db  # type: ignore[attr-defined]
    with db.session() as session:
        glyphs = [session.get(Glyph, glyph_id) for glyph_id in bank_ids]
        assert all(g is not None and g.accept_count >= 1 and g.use_count >= 1 for g in glyphs)


def test_export_jpeg_with_and_without_marker(studio: Studio) -> None:
    profile = _ready_profile(studio)
    job = _rendered(studio, profile["id"])
    studio.client.post(f"/api/v1/jobs/{job['id']}/accept")

    first = studio.client.post(f"/api/v1/jobs/{job['id']}/export", json={"format": "jpeg"})
    with Image.open(io.BytesIO(_download(studio, first.json()["data"]["file"]["url"]))) as image:
        assert image.format == "JPEG"
        assert image.info.get("comment", b"").startswith(b"Traid")

    db = studio.client.app.state.db  # type: ignore[attr-defined]
    with db.session() as session:
        session.add(AppSetting(key="export.metadata_marker", value=False))
    second = studio.client.post(
        f"/api/v1/jobs/{job['id']}/export",
        json={"format": "jpeg", "filename_pattern": "{token}_{n}"},
    )
    out = second.json()["data"]
    assert out["download_name"] == "A7-204914_1.jpg"
    with Image.open(io.BytesIO(_download(studio, out["file"]["url"]))) as image:
        assert "comment" not in image.info


# ---------------------------------------------------------------- state machine


def test_invalid_transitions_answer_409(studio: Studio) -> None:
    profile = _ready_profile(studio)
    job = _detected(studio, profile["id"])
    job_url = f"/api/v1/jobs/{job['id']}"

    for path in ("accept", "reject", "export"):
        response = studio.client.post(f"{job_url}/{path}", json={})
        assert response.status_code == 409, path
        assert response.json()["error"]["code"] == "INVALID_STATE"

    studio.client.post(f"{job_url}/render", json={"new_text": "A7-204914"})
    studio.run_tasks()
    studio.client.post(f"{job_url}/accept")
    for method, path, body in (
        ("post", "render", {"new_text": "A7-204915"}),
        ("put", "region", {"region_id": "r1"}),
        ("post", "reject", {}),
    ):
        response = getattr(studio.client, method)(f"{job_url}/{path}", json=body)
        assert response.status_code == 409, path


def test_reject_then_render_again(studio: Studio) -> None:
    profile = _ready_profile(studio)
    job = _rendered(studio, profile["id"], "ZX-58")
    bank_ids = [u["glyph_id"] for u in job["glyphs_used"] if u["source"] == "bank"]

    rejected = studio.client.post(
        f"/api/v1/jobs/{job['id']}/reject", json={"reason": "  Z looks too bold "}
    ).json()["data"]
    assert rejected["status"] == "rejected" and rejected["reject_reason"] == "Z looks too bold"
    db = studio.client.app.state.db  # type: ignore[attr-defined]
    with db.session() as session:
        assert all(session.get(Glyph, g).reject_count == 1 for g in bank_ids)  # type: ignore[union-attr]

    again = studio.client.post(f"/api/v1/jobs/{job['id']}/render", json={"new_text": "ZX-85"})
    assert again.status_code == 202
    studio.run_tasks()
    assert _job(studio, job["id"])["status"] == "rendered"


def test_changing_the_region_clears_the_result(studio: Studio) -> None:
    profile = _ready_profile(studio)
    job = _rendered(studio, profile["id"])
    quad = job["selected_quad"]

    moved = studio.client.put(
        f"/api/v1/jobs/{job['id']}/region",
        json={"quad": quad, "original_text": TOKEN},
    )

    assert moved.status_code == 200, moved.text
    data = moved.json()["data"]
    assert data["status"] == "detected"
    assert data["result"] is None and data["quality"] is None
    assert data["selected_region_id"] is None
    assert data["original_text"] == TOKEN


def test_region_validation(studio: Studio) -> None:
    profile = _ready_profile(studio)
    job = _detected(studio, profile["id"])
    url = f"/api/v1/jobs/{job['id']}/region"

    both = studio.client.put(url, json={"region_id": "r1", "quad": job["selected_quad"]})
    unknown = studio.client.put(url, json={"region_id": "r9"})
    outside = studio.client.put(url, json={"quad": [[-50, 0], [10, 0], [10, 10], [-50, 10]]})
    tiny = studio.client.put(url, json={"quad": [[10, 10], [12, 10], [12, 12], [10, 12]]})

    assert [r.status_code for r in (both, unknown, outside, tiny)] == [422, 422, 422, 422]


def test_drawn_region_without_readable_text_needs_the_old_text(studio: Studio) -> None:
    profile = _ready_profile(studio)
    job = _detected(studio, profile["id"])
    drawn = studio.client.put(
        f"/api/v1/jobs/{job['id']}/region", json={"quad": job["selected_quad"]}
    ).json()["data"]
    assert drawn["original_text"] is None  # the fake OCR cannot read crops

    response = studio.client.post(f"/api/v1/jobs/{job['id']}/render", json={"new_text": "A7-1"})

    assert response.status_code == 409
    assert response.json()["error"]["details"]["field"] == "original_text"


def test_no_text_found_leaves_a_manual_path(studio: Studio) -> None:
    profile = _ready_profile(studio)
    blank = make_token_image(TOKEN, "print", seed=3, blank=True).image
    response = studio.client.post(
        "/api/v1/jobs",
        data={"profile_id": profile["id"]},
        files={"file": ("blank.png", png_bytes(blank), "image/png")},
    )
    studio.run_tasks()

    job = _job(studio, response.json()["data"]["job"]["id"])

    assert job["status"] == "detected"
    assert job["regions"] == [] and job["error_code"] == "NO_TEXT_FOUND"


# ---------------------------------------------------------------- render validation


def test_render_validation_codes(studio: Studio) -> None:
    profile = _ready_profile(studio, token_pattern="^[A-Z0-9]{2}-[0-9]{4,6}$", pattern_strict=True)
    job = _detected(studio, profile["id"])
    url = f"/api/v1/jobs/{job['id']}/render"

    charset = studio.client.post(url, json={"new_text": "A7-2049é"})
    pattern = studio.client.post(url, json={"new_text": "A7204914"})
    missing = studio.client.post(url, json={"new_text": "QW-204913"})
    params = studio.client.post(url, json={"new_text": "A7-204914", "params": {"scale": 2}})
    override = studio.client.post(
        url, json={"new_text": "A7-204914", "params": {"glyph_overrides": {"20": "x"}}}
    )

    assert (charset.status_code, charset.json()["error"]["code"]) == (422, "CHAR_NOT_IN_CHARSET")
    assert (pattern.status_code, pattern.json()["error"]["code"]) == (422, "PATTERN_MISMATCH")
    assert (missing.status_code, missing.json()["error"]["code"]) == (409, "PROFILE_NOT_READY")
    assert missing.json()["error"]["details"]["missing"] == ["Q", "W"]
    assert params.status_code == 422
    assert override.status_code == 422


def test_identical_render_requests_share_one_task(studio: Studio) -> None:
    profile = _ready_profile(studio)
    job = _detected(studio, profile["id"])
    url = f"/api/v1/jobs/{job['id']}/render"

    first = studio.client.post(url, json={"new_text": "A7-204914"}).json()["data"]
    same = studio.client.post(url, json={"new_text": "A7-204914"}).json()["data"]
    adjusted = studio.client.post(url, json={"new_text": "A7-204914", "params": {"dx": 2}}).json()[
        "data"
    ]

    assert first["id"] == same["id"] == adjusted["id"]  # still queued: payload updated
    studio.run_tasks()
    assert _job(studio, job["id"])["params"]["dx"] == 2


def test_glyph_variants_for_a_position(studio: Studio) -> None:
    profile = _ready_profile(studio)
    job = _rendered(studio, profile["id"], "ZX-58")

    response = studio.client.get(f"/api/v1/jobs/{job['id']}/glyph-variants?position=0")

    assert response.status_code == 200, response.text
    variants = response.json()["data"]
    assert variants and all(v["source"] == "bank" for v in variants)
    assert variants == sorted(variants, key=lambda v: -v["score"])
    outside = studio.client.get(f"/api/v1/jobs/{job['id']}/glyph-variants?position=30")
    assert outside.status_code == 422


# ---------------------------------------------------------------- other operations


def test_reopen_copies_the_job(studio: Studio) -> None:
    profile = _ready_profile(studio)
    job = _rendered(studio, profile["id"])
    studio.client.post(f"/api/v1/jobs/{job['id']}/accept")

    response = studio.client.post(f"/api/v1/jobs/{job['id']}/reopen")

    assert response.status_code == 201
    copy = response.json()["data"]
    assert copy["id"] != job["id"] and copy["status"] == "detected"
    assert copy["selected_quad"] == job["selected_quad"]
    assert copy["new_text"] == job["new_text"] and copy["seed"] == job["seed"]
    assert copy["result"] is None


def test_delete_and_ownership(studio: Studio) -> None:
    profile = _ready_profile(studio)
    job = _detected(studio, profile["id"])

    assert studio.client.delete(f"/api/v1/jobs/{job['id']}").status_code == 204
    assert studio.client.get(f"/api/v1/jobs/{job['id']}").status_code == 404
    assert studio.client.post("/api/v1/jobs/nope/accept").status_code == 404


def test_history_filters(studio: Studio) -> None:
    profile = _ready_profile(studio)
    rendered = _rendered(studio, profile["id"], "B8-551067")
    _detected(studio, profile["id"], text="ZX-58BK", seed=9)

    def ids(query: str) -> list[str]:
        response = studio.client.get(f"/api/v1/jobs{query}")
        assert response.status_code == 200, response.text
        return [j["id"] for j in response.json()["data"]]

    assert len(ids("")) == 2
    assert ids("?status=rendered") == [rendered["id"]]
    assert ids("?q=B8-55") == [rendered["id"]]
    assert ids(f"?profile_id={profile['id']}&limit=1") != []
    assert studio.client.get("/api/v1/jobs?sort=new").status_code == 422
    assert studio.client.get("/api/v1/jobs?status=done").status_code == 422


@pytest.mark.parametrize("surface", ["paint", "engraved"])
def test_relief_and_ink_profiles_render(studio: Studio, surface: str) -> None:
    profile = studio.create_profile(name=f"P {surface}", surface_type=surface, ready_threshold=1)
    files = [
        (f"r{i}.png", studio.token_png(text, surface, seed=60 + i))  # type: ignore[arg-type]
        for i, text in enumerate(REFERENCE_TEXTS)
    ]
    studio.upload(profile["id"], *files)
    studio.run_tasks()
    ids = [
        g["id"]
        for g in studio.client.get(f"/api/v1/profiles/{profile['id']}/glyphs?limit=200").json()[
            "data"
        ]
    ]
    studio.client.post(
        f"/api/v1/profiles/{profile['id']}/glyphs/bulk", json={"ids": ids, "action": "confirm"}
    )
    response = studio.client.post(
        "/api/v1/jobs",
        data={"profile_id": profile["id"]},
        files={"file": ("t.png", studio.token_png(TOKEN, surface, seed=8), "image/png")},  # type: ignore[arg-type]
    )
    studio.run_tasks()
    job_id = response.json()["data"]["job"]["id"]
    studio.client.post(f"/api/v1/jobs/{job_id}/render", json={"new_text": "A7-204914"})
    studio.run_tasks()

    assert _job(studio, job_id)["status"] == "rendered"
