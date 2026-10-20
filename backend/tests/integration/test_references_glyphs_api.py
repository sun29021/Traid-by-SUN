"""Reference upload → background extraction → glyph review (J2 end to end via the API)."""

from typing import Any

import pytest

from app.core.config import REPO_ROOT, Settings
from app.engine.detect import PaddleOcr
from app.engine.models import ModelRegistry
from tests.factories import image_bytes
from tests.integration.conftest import Studio

TOKEN = "A7-204913"
TOKEN_CHARS = "A7-204913"  # charset with exactly the token's characters


def _profile_with_two_references(studio: Studio, **fields: Any) -> tuple[dict[str, Any], Any]:
    profile = studio.create_profile(charset=TOKEN_CHARS, ready_threshold=2, **fields)
    response = studio.upload(
        profile["id"],
        ("one.png", studio.token_png(TOKEN, seed=1)),
        ("two.png", studio.token_png(TOKEN, seed=2)),
    )
    assert response.status_code == 202, response.text
    studio.run_tasks()
    return profile, response.json()["data"]


def _glyphs(studio: Studio, profile_id: str, query: str = "") -> list[dict[str, Any]]:
    response = studio.client.get(f"/api/v1/profiles/{profile_id}/glyphs?limit=200{query}")
    assert response.status_code == 200, response.text
    data: list[dict[str, Any]] = response.json()["data"]
    return data


def test_upload_reports_created_skipped_and_rejected(studio: Studio) -> None:
    profile = studio.create_profile()
    good = studio.token_png(TOKEN, seed=1)

    result = studio.upload(
        profile["id"],
        ("good.png", good),
        ("again.png", good),
        ("notes.txt", b"just text"),
    ).json()["data"]

    assert [r["file"]["original_name"] for r in result["created"]] == ["good.png"]
    assert [s["code"] for s in result["skipped"]] == ["DUPLICATE_FILE"]
    assert [r["code"] for r in result["rejected"]] == ["UNSUPPORTED_MEDIA_TYPE"]
    assert result["task"]["type"] == "extract_glyphs" and result["task"]["status"] == "queued"
    assert result["created"][0]["status"] == "pending"


def test_profile_is_training_while_extraction_is_queued(studio: Studio) -> None:
    profile = studio.create_profile()
    studio.upload(profile["id"], ("a.png", studio.token_png(TOKEN)))

    status = studio.client.get(f"/api/v1/profiles/{profile['id']}").json()["data"]["status"]

    assert status == "training"


def test_extraction_fills_the_glyph_bank(studio: Studio) -> None:
    profile, _ = _profile_with_two_references(studio)

    references = studio.client.get(f"/api/v1/profiles/{profile['id']}/references").json()["data"]
    glyphs = _glyphs(studio, profile["id"])
    detail = studio.client.get(f"/api/v1/profiles/{profile['id']}").json()["data"]

    assert [r["status"] for r in references] == ["processed", "processed"]
    assert all(r["glyph_count"] == 9 for r in references)
    assert references[0]["conditions"]["cap_height_px"] > 10
    assert len(glyphs) == 18
    assert sorted({g["char"] for g in glyphs}) == sorted(set(TOKEN))
    assert all(g["status"] == "auto" for g in glyphs)
    assert all(0 < g["quality_score"] <= 1 for g in glyphs)
    assert detail["status"] == "needs_review"
    assert detail["stats"] == {
        "glyphs_confirmed": 0,
        "glyphs_auto": 18,
        "references": 2,
        "jobs_accepted": 0,
        "acceptance_rate": None,
    }


def test_glyph_crops_are_served_as_png(studio: Studio) -> None:
    profile, upload = _profile_with_two_references(studio)
    glyph = _glyphs(studio, profile["id"])[0]

    crop = studio.client.get(glyph["crop_url"])
    thumb = studio.client.get(upload["created"][0]["file"]["thumb_url"])

    assert crop.status_code == 200 and crop.headers["content-type"] == "image/png"
    assert "immutable" in crop.headers["cache-control"]
    assert crop.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/jpeg"
    assert studio.client.get("/api/v1/files/not-a-file").status_code == 404


def test_reviewing_glyphs_makes_the_profile_ready(studio: Studio) -> None:
    profile, _ = _profile_with_two_references(studio)
    ids = [g["id"] for g in _glyphs(studio, profile["id"])]

    result = studio.client.post(
        f"/api/v1/profiles/{profile['id']}/glyphs/bulk", json={"ids": ids, "action": "confirm"}
    ).json()["data"]
    detail = studio.client.get(f"/api/v1/profiles/{profile['id']}").json()["data"]
    coverage = studio.client.get(f"/api/v1/profiles/{profile['id']}/coverage").json()["data"]

    assert result == {"updated": 18}
    assert detail["status"] == "ready"
    distinct = len(set(TOKEN))  # A 7 - 2 0 4 9 1 3
    assert detail["coverage"] == {"ready_chars": distinct, "total_chars": distinct, "missing": []}
    assert all(item["ready"] and item["confirmed"] >= 2 for item in coverage)


def test_glyph_filters_and_pagination(studio: Studio) -> None:
    profile, _ = _profile_with_two_references(studio)
    first = _glyphs(studio, profile["id"])[0]
    studio.client.patch(f"/api/v1/glyphs/{first['id']}", json={"status": "rejected"})

    rejected = _glyphs(studio, profile["id"], "&status=rejected")
    nines = _glyphs(studio, profile["id"], "&char=9")
    page = studio.client.get(f"/api/v1/profiles/{profile['id']}/glyphs?limit=5").json()
    rest = studio.client.get(
        f"/api/v1/profiles/{profile['id']}/glyphs?limit=50&cursor={page['meta']['next_cursor']}"
    ).json()

    assert [g["id"] for g in rejected] == [first["id"]]
    assert {g["char"] for g in nines} == {"9"} and len(nines) == 2
    assert page["meta"]["count"] == 5 and rest["meta"] == {"next_cursor": None, "count": 13}


def test_relabel_must_use_the_charset(studio: Studio) -> None:
    profile, _ = _profile_with_two_references(studio)
    glyph = _glyphs(studio, profile["id"])[0]

    bad = studio.client.patch(f"/api/v1/glyphs/{glyph['id']}", json={"char": "Z"})
    good = studio.client.patch(f"/api/v1/glyphs/{glyph['id']}", json={"char": "4"})

    assert bad.status_code == 422 and bad.json()["error"]["code"] == "CHAR_NOT_IN_CHARSET"
    assert good.json()["data"]["char"] == "4" and good.json()["data"]["status"] == "confirmed"


def test_reextraction_keeps_review_decisions(studio: Studio) -> None:
    profile, upload = _profile_with_two_references(studio)
    reference_id = upload["created"][0]["id"]
    own = [g for g in _glyphs(studio, profile["id"]) if g["source"]["id"] == reference_id]
    studio.client.patch(f"/api/v1/glyphs/{own[0]['id']}", json={"status": "confirmed"})
    studio.client.patch(f"/api/v1/glyphs/{own[1]['id']}", json={"status": "rejected"})

    task = studio.client.post(f"/api/v1/references/{reference_id}/reextract")
    studio.run_tasks()
    after = [g for g in _glyphs(studio, profile["id"]) if g["source"]["id"] == reference_id]

    assert task.status_code == 202
    assert len(after) == 9  # 2 kept decisions + 7 fresh auto glyphs, no duplicates
    statuses = {g["id"]: g["status"] for g in after}
    assert statuses[own[0]["id"]] == "confirmed" and statuses[own[1]["id"]] == "rejected"


def test_known_text_reruns_extraction(studio: Studio) -> None:
    profile, upload = _profile_with_two_references(studio)
    reference_id = upload["created"][0]["id"]

    change = studio.client.patch(
        f"/api/v1/references/{reference_id}", json={"known_text": TOKEN}
    ).json()["data"]

    assert change["reference"]["known_text"] == TOKEN
    assert change["task"]["type"] == "extract_glyphs"
    studio.run_tasks()
    assert len(_glyphs(studio, profile["id"])) == 18


def test_deleting_a_reference_removes_its_glyphs(studio: Studio) -> None:
    profile, upload = _profile_with_two_references(studio)

    response = studio.client.delete(f"/api/v1/references/{upload['created'][0]['id']}")

    assert response.status_code == 204
    assert len(_glyphs(studio, profile["id"])) == 9


def test_images_without_text_fail_individually(studio: Studio) -> None:
    profile = studio.create_profile(charset=TOKEN_CHARS)
    studio.upload(
        profile["id"],
        ("blank.png", image_bytes("PNG", size=(200, 100))),
        ("token.png", studio.token_png(TOKEN, seed=3)),
    )

    studio.run_tasks()
    references = studio.client.get(f"/api/v1/profiles/{profile['id']}/references").json()["data"]

    by_name = {r["file"]["original_name"]: r for r in references}
    assert (by_name["blank.png"]["status"], by_name["blank.png"]["error_code"]) == (
        "failed",
        "NO_TEXT_FOUND",
    )
    assert by_name["token.png"]["status"] == "processed"


def test_engine_crash_marks_the_reference_failed(studio: Studio) -> None:
    profile = studio.create_profile()
    studio.upload(profile["id"], ("a.png", studio.token_png(TOKEN)))
    studio.detector.fail = True

    studio.run_tasks()
    reference = studio.client.get(f"/api/v1/profiles/{profile['id']}/references").json()["data"][0]

    assert (reference["status"], reference["error_code"]) == ("failed", "INTERNAL_ERROR")


def test_archived_profiles_reject_uploads(studio: Studio) -> None:
    profile = studio.create_profile()
    studio.client.post(f"/api/v1/profiles/{profile['id']}/archive")

    response = studio.upload(profile["id"], ("a.png", studio.token_png(TOKEN)))

    assert response.status_code == 409 and response.json()["error"]["code"] == "PROFILE_ARCHIVED"


@pytest.mark.models
def test_real_models_extract_glyphs_through_the_api(settings: Settings) -> None:
    from fastapi.testclient import TestClient

    from app.core.http_security import CLIENT_HEADER, CLIENT_HEADER_VALUE
    from app.main import create_app
    from tests.factories import png_bytes
    from tests.fixtures.generate import make_token_image

    registry = ModelRegistry.from_manifest(REPO_ROOT / "models", device="cpu")
    if not registry.ready:
        pytest.skip("OCR models not installed")
    app = create_app(settings, start_worker=False, detector=PaddleOcr(registry))
    with TestClient(app, headers={CLIENT_HEADER: CLIENT_HEADER_VALUE}) as client:
        client.post("/api/v1/system/welcome", json={"accept_aup": True})
        profile = client.post(
            "/api/v1/profiles", json={"name": "Plates", "surface_type": "engraved"}
        ).json()["data"]
        image = png_bytes(make_token_image(TOKEN, "engraved", seed=5).image)
        client.post(
            f"/api/v1/profiles/{profile['id']}/references",
            files=[("files", ("plate.png", image, "image/png"))],
        )
        while app.state.task_runner.run_once():
            pass
        glyphs = client.get(f"/api/v1/profiles/{profile['id']}/glyphs").json()["data"]

    assert "".join(sorted(g["char"] for g in glyphs)) == "".join(sorted(TOKEN))
    assert all(g["metrics"]["light_dir_deg"] is not None for g in glyphs[:3])
