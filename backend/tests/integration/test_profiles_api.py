"""Style Profile CRUD, archive/delete rules, status and coverage (API.md §3.3)."""

import pytest
from sqlalchemy import select

from app.db.engine import Database
from app.db.models import AuditEvent, Profile
from tests.factories import make_user
from tests.integration.conftest import Studio

API = "/api/v1/profiles"


def test_create_applies_defaults(studio: Studio) -> None:
    profile = studio.create_profile()

    assert profile["surface_type"] == "print"
    assert profile["charset"] == "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-/# "
    assert (profile["alignment"], profile["spacing_mode"]) == ("auto", "auto")
    assert profile["ready_threshold"] == 3 and profile["use_auto_glyphs"] is False
    assert profile["status"] == "draft"
    # Spaces need no glyph, so they are not part of coverage.
    assert profile["coverage"]["total_chars"] == 39
    assert " " not in profile["coverage"]["missing"]


def test_charset_is_deduplicated(studio: Studio) -> None:
    profile = studio.create_profile(charset="AABBA12")

    assert profile["charset"] == "AB12"


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"name": "", "surface_type": "print"}, "name"),
        ({"name": "X"}, "surface_type"),
        ({"name": "X", "surface_type": "neon"}, "surface_type"),
        ({"name": "X", "surface_type": "print", "charset": ""}, "charset"),
        ({"name": "X", "surface_type": "print", "charset": "AB\n"}, "charset"),
        ({"name": "X", "surface_type": "print", "token_pattern": "[A-"}, "token_pattern"),
        ({"name": "X", "surface_type": "print", "token_pattern": "(a+)+$"}, "token_pattern"),
        ({"name": "X", "surface_type": "print", "ready_threshold": 0}, "ready_threshold"),
        ({"name": "X", "surface_type": "print", "owner_id": "me"}, "owner_id"),
    ],
)
def test_create_validation(studio: Studio, body: dict[str, object], field: str) -> None:
    response = studio.client.post(API, json=body)

    assert response.status_code == 422
    paths = [f["path"] for f in response.json()["error"]["details"]["fields"]]
    assert field in paths


def test_names_are_unique(studio: Studio) -> None:
    studio.create_profile(name="Wall signs")

    response = studio.client.post(API, json={"name": "Wall signs", "surface_type": "paint"})

    assert response.status_code == 409


def test_update_and_clearing_the_pattern(studio: Studio) -> None:
    profile = studio.create_profile(token_pattern=r"^[A-Z]\d-\d{6}$", pattern_strict=True)

    renamed = studio.client.patch(
        f"{API}/{profile['id']}", json={"name": "Renamed", "surface_type": "engraved"}
    ).json()["data"]
    cleared = studio.client.patch(f"{API}/{profile['id']}", json={"token_pattern": None}).json()[
        "data"
    ]

    assert (renamed["name"], renamed["surface_type"]) == ("Renamed", "engraved")
    assert cleared["token_pattern"] is None and cleared["pattern_strict"] is False


def test_list_filters_archived(studio: Studio) -> None:
    active = studio.create_profile(name="Active")
    archived = studio.create_profile(name="Old")
    studio.client.post(f"{API}/{archived['id']}/archive")

    def names(query: str) -> list[str]:
        return sorted(p["name"] for p in studio.client.get(f"{API}?{query}").json()["data"])

    assert names("archived=false") == ["Active"]
    assert names("archived=true") == ["Old"]
    assert names("archived=all") == ["Active", "Old"]
    assert names("q=act") == ["Active"]
    assert active["archived_at"] is None


def test_archived_profiles_are_read_only_until_restored(studio: Studio) -> None:
    profile = studio.create_profile()
    studio.client.post(f"{API}/{profile['id']}/archive")

    blocked = studio.client.patch(f"{API}/{profile['id']}", json={"name": "New"})
    studio.client.post(f"{API}/{profile['id']}/unarchive")
    allowed = studio.client.patch(f"{API}/{profile['id']}", json={"name": "New"})

    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "PROFILE_ARCHIVED"
    assert allowed.status_code == 200


def test_permanent_delete_needs_archive_and_exact_name(studio: Studio) -> None:
    profile = studio.create_profile(name="Doomed")
    url = f"{API}/{profile['id']}"

    not_archived = studio.client.request("DELETE", url, json={"confirm_name": "Doomed"})
    studio.client.post(f"{url}/archive")
    wrong_name = studio.client.request("DELETE", url, json={"confirm_name": "doomed"})
    deleted = studio.client.request("DELETE", url, json={"confirm_name": "Doomed"})

    assert not_archived.status_code == 409
    assert wrong_name.status_code == 422
    assert deleted.status_code == 204
    assert studio.client.get(url).status_code == 404
    actions = [e["action"] for e in studio.client.get("/api/v1/audit").json()["data"]]
    assert {"profile.created", "profile.archived", "profile.deleted"} <= set(actions)


def test_profiles_of_other_users_are_invisible(studio: Studio) -> None:
    db: Database = studio.client.app.state.db  # type: ignore[attr-defined]
    stranger = make_user(db, "stranger")
    with db.session() as session:
        session.add(Profile(owner_id=stranger, name="Secret", surface_type="print"))
    with db.session_factory() as session:
        secret_id = session.scalar(select(Profile.id).where(Profile.name == "Secret"))

    assert studio.client.get(f"{API}/{secret_id}").status_code == 404
    assert studio.client.get(f"{API}/{secret_id}/coverage").status_code == 404
    assert studio.client.patch(f"{API}/{secret_id}", json={"name": "Mine"}).status_code == 404
    assert [p["name"] for p in studio.client.get(API).json()["data"]] == []
    with db.session_factory() as session:
        assert session.scalar(select(AuditEvent).where(AuditEvent.subject_id == secret_id)) is None
