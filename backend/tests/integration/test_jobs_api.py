"""Edit jobs end to end through the API (IMPLEMENTATION_PLAN.md Phase 9)."""

import io
from typing import Any

import cv2
import numpy as np
import pytest
from PIL import Image

from app.db.models import AppSetting, Glyph
from app.engine.extract import STRIP_PADDING
from app.engine.geometry import clip_quad, expand_quad, rectify
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


# ---------------------------------------------------------------- learning (Phase 11)


def _accept_with(studio: Studio, profile_id: str, params: dict[str, Any]) -> dict[str, Any]:
    job = _detected(studio, profile_id)
    studio.client.post(
        f"/api/v1/jobs/{job['id']}/render", json={"new_text": "A7-204914", "params": params}
    )
    studio.run_tasks()
    response = studio.client.post(f"/api/v1/jobs/{job['id']}/accept")
    assert response.status_code == 200, response.text
    data: dict[str, Any] = response.json()["data"]
    return data


def test_accepts_teach_starting_adjustments_and_position(studio: Studio) -> None:
    profile = _ready_profile(studio)
    for _ in range(3):
        _accept_with(studio, profile["id"], {"dx": 4, "ink_tone": 0.5})

    learning = studio.client.get(f"/api/v1/profiles/{profile['id']}/learning").json()["data"]
    assert learning["accepted"] == 3 and learning["acceptance_rate"] == 1.0
    assert learning["learned_params"]["dx"] == pytest.approx(4 * (1 - 0.8**3), abs=1e-3)
    assert learning["typical_region"]["count"] == 3
    assert 0.3 < learning["typical_region"]["cx"] < 0.7
    assert sum(day["accepted"] for day in learning["history"]) == 3

    detail = studio.client.get(f"/api/v1/profiles/{profile['id']}").json()["data"]
    assert detail["stats"]["jobs_accepted"] == 3
    assert detail["learned_params"]["dx"] > 0

    # The next job starts from what was learned.
    fresh = _create_job(studio, profile["id"], seed=12)
    assert fresh["job"]["params"]["dx"] == pytest.approx(learning["learned_params"]["dx"], abs=1e-3)
    assert fresh["job"]["params"]["ink_tone"] > 0


def test_accepted_jobs_add_their_original_characters_for_review(studio: Studio) -> None:
    profile = _ready_profile(studio)
    before = studio.client.get(f"/api/v1/profiles/{profile['id']}/glyphs?limit=200").json()
    job = _accept_with(studio, profile["id"], {})

    after = studio.client.get(f"/api/v1/profiles/{profile['id']}/glyphs?limit=200").json()
    harvested = [g for g in after["data"] if g["source"]["type"] == "job"]

    assert len(after["data"]) > len(before["data"])
    assert {g["source"]["id"] for g in harvested} == {job["id"]}
    assert all(g["status"] == "auto" for g in harvested)
    assert "".join(sorted(g["char"] for g in harvested)) == "".join(sorted(TOKEN.replace(" ", "")))

    # Crops come from the input photo, never from the result: the harvested "3" (the
    # character this edit replaced) is found in the original strip (up to warp rounding),
    # not in the result.
    original = make_token_image(TOKEN, "print", seed=8).image
    result = np.asarray(
        Image.open(io.BytesIO(_download(studio, job["result"]["url"]))).convert("RGB")
    )
    quad = np.asarray(job["selected_quad"], dtype=np.float32)
    strip_quad = clip_quad(expand_quad(quad, STRIP_PADDING), original.shape[1], original.shape[0])
    three = next(g for g in harvested if g["char"] == "3")
    crop = np.asarray(Image.open(io.BytesIO(_download(studio, three["crop_url"]))))[..., :3]

    def best_match(image: np.ndarray) -> float:
        strip = rectify(image, strip_quad).patch
        scores = cv2.matchTemplate(strip.astype(np.float32), crop.astype(np.float32), cv2.TM_SQDIFF)
        return float(scores.min())

    in_original, in_result = best_match(original), best_match(result)
    assert in_original / crop.size < 0.05  # mean squared difference per value
    assert in_result > 100 * in_original

    # Accepting again does not harvest twice.
    studio.client.post(f"/api/v1/jobs/{job['id']}/accept")
    again = studio.client.get(f"/api/v1/profiles/{profile['id']}/glyphs?limit=200").json()
    assert len(again["data"]) == len(after["data"])


def test_rejections_push_a_glyph_down_the_ranking(studio: Studio) -> None:
    profile = _ready_profile(studio)
    job = _rendered(studio, profile["id"], "ZX-58")
    first = studio.client.get(f"/api/v1/jobs/{job['id']}/glyph-variants?position=0").json()["data"]
    top = first[0]["glyph_id"]

    studio.client.post(f"/api/v1/jobs/{job['id']}/reject", json={})
    db = studio.client.app.state.db  # type: ignore[attr-defined]
    with db.session() as session:
        glyph = session.get(Glyph, top)
        assert glyph is not None
        glyph.reject_count = 5

    later = studio.client.get(f"/api/v1/jobs/{job['id']}/glyph-variants?position=0").json()["data"]
    if len(later) > 1:
        assert later[0]["glyph_id"] != top
    assert next(v for v in later if v["glyph_id"] == top)["score"] < first[0]["score"]


def test_export_writes_descriptive_metadata_with_saved_defaults(studio: Studio) -> None:
    profile = _ready_profile(studio)
    job = _rendered(studio, profile["id"])
    studio.client.post(f"/api/v1/jobs/{job['id']}/accept")
    saved = studio.client.patch(
        "/api/v1/settings",
        json={
            "export.default_author": "Xavier Sun",
            "export.default_copyright": "© 2026 Xavier Sun",
        },
    )
    assert saved.status_code == 200, saved.text

    response = studio.client.post(
        f"/api/v1/jobs/{job['id']}/export",
        json={
            "format": "jpeg",
            "metadata": {
                "title": "Receipt mock-up",
                "description": "Edited from receipt.png",
                "keywords": ["traid", " receipt ", "traid"],
            },
        },
    )

    assert response.status_code == 201, response.text
    data = _download(studio, response.json()["data"]["file"]["url"])
    with Image.open(io.BytesIO(data)) as image:
        exif = image.getexif()
        xmp = image.info["xmp"].decode("utf-8")
    assert exif[315] == "Xavier Sun"  # default author applied
    assert exif[33432] == "(c) 2026 Xavier Sun"
    assert exif[270] == "Edited from receipt.png"
    assert "© 2026 Xavier Sun" in xmp and xmp.count("<rdf:li>traid</rdf:li>") == 1
    assert not set(exif) & {271, 272, 306, 0x8769, 0x8825}  # never camera, date or GPS

    # An explicit empty author overrides the default; unknown fields are rejected.
    empty = studio.client.post(
        f"/api/v1/jobs/{job['id']}/export", json={"format": "jpeg", "metadata": {"author": ""}}
    )
    with Image.open(io.BytesIO(_download(studio, empty.json()["data"]["file"]["url"]))) as image:
        assert 315 not in image.getexif()
    spoof = studio.client.post(
        f"/api/v1/jobs/{job['id']}/export", json={"metadata": {"camera_model": "Canon EOS"}}
    )
    assert spoof.status_code == 422
