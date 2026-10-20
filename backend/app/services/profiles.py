"""Style Profiles: CRUD, archive, derived status and coverage (PRD FR-P01, FR-P04)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.errors import Conflict, ErrorCode, NotFound, ValidationFailed
from app.db.models import Profile
from app.db.transaction import transaction
from app.repositories import profiles as repo
from app.schemas.profiles import (
    Coverage,
    CoverageItem,
    ProfileCreate,
    ProfileOut,
    ProfileStats,
    ProfileStatus,
    ProfileUpdate,
)
from app.services import audit, learning
from app.services.audit import AuditAction

# Spaces never need glyphs: the renderer leaves a gap.
NO_GLYPH_CHARS = frozenset(" ")


def coverage_chars(charset: str) -> list[str]:
    return [c for c in charset if c not in NO_GLYPH_CHARS]


def get_owned(session: Session, owner_id: str, profile_id: str) -> Profile:
    profile = repo.get_profile(session, owner_id, profile_id)
    if profile is None:
        raise NotFound("Profile not found")
    return profile


def _usable(counts: repo.CharCounts, use_auto: bool) -> int:
    return counts.confirmed + (counts.auto if use_auto else 0)


def coverage_items(profile: Profile, counts: repo.ProfileCounts) -> list[CoverageItem]:
    items = []
    for char in coverage_chars(profile.charset):
        c = counts.chars.get(char, repo.CharCounts())
        items.append(
            CoverageItem(
                char=char,
                confirmed=c.confirmed,
                auto=c.auto,
                rejected=c.rejected,
                best_quality=round(c.best_quality, 4),
                ready=_usable(c, bool(profile.use_auto_glyphs)) >= profile.ready_threshold,
            )
        )
    return items


def _status(items: Sequence[CoverageItem], training: bool) -> ProfileStatus:
    if training:
        return "training"
    if items and all(item.ready for item in items):
        return "ready"
    if any(item.auto for item in items):
        return "needs_review"
    return "draft"


def to_out(
    profile: Profile,
    counts: repo.ProfileCounts,
    training: bool,
    decisions: tuple[int, int] = (0, 0),
) -> ProfileOut:
    items = coverage_items(profile, counts)
    return ProfileOut(
        id=profile.id,
        name=profile.name,
        description=profile.description,
        surface_type=profile.surface_type,  # type: ignore[arg-type]
        charset=profile.charset,
        token_pattern=profile.token_pattern,
        pattern_strict=bool(profile.pattern_strict),
        alignment=profile.alignment,  # type: ignore[arg-type]
        spacing_mode=profile.spacing_mode,  # type: ignore[arg-type]
        ready_threshold=profile.ready_threshold,
        use_auto_glyphs=bool(profile.use_auto_glyphs),
        engine=profile.engine,
        status=_status(items, training),
        coverage=Coverage(
            ready_chars=sum(i.ready for i in items),
            total_chars=len(items),
            missing=[i.char for i in items if not i.ready],
        ),
        stats=ProfileStats(
            glyphs_confirmed=sum(c.confirmed for c in counts.chars.values()),
            glyphs_auto=sum(c.auto for c in counts.chars.values()),
            references=counts.references,
            jobs_accepted=decisions[0],
            acceptance_rate=learning.acceptance_rate(*decisions),
        ),
        learned_params=profile.learned_params,
        archived_at=profile.archived_at,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def describe(session: Session, profiles: Sequence[Profile]) -> list[ProfileOut]:
    ids = [p.id for p in profiles]
    counts = repo.glyph_counts(session, ids)
    training = repo.training_profile_ids(session, ids)
    decisions = learning.decision_counts(session, ids)
    return [
        to_out(p, counts[p.id], p.id in training, decisions.get(p.id, (0, 0))) for p in profiles
    ]


def list_profiles(
    session: Session, owner_id: str, *, archived: bool | None, query: str | None
) -> list[ProfileOut]:
    return describe(session, repo.list_profiles(session, owner_id, archived=archived, query=query))


def get_profile(session: Session, owner_id: str, profile_id: str) -> ProfileOut:
    return describe(session, [get_owned(session, owner_id, profile_id)])[0]


def coverage(session: Session, owner_id: str, profile_id: str) -> list[CoverageItem]:
    profile = get_owned(session, owner_id, profile_id)
    return coverage_items(profile, repo.glyph_counts(session, [profile.id])[profile.id])


def _apply(profile: Profile, fields: dict[str, Any]) -> None:
    for key, value in fields.items():
        if key in ("pattern_strict", "use_auto_glyphs"):
            value = int(bool(value))
        elif hasattr(value, "value"):
            value = value.value
        setattr(profile, key, value)


def _name_taken(session: Session, owner_id: str, name: str, except_id: str | None) -> bool:
    existing = repo.get_profile_by_name(session, owner_id, name)
    return existing is not None and existing.id != except_id


def create_profile(session: Session, owner_id: str, data: ProfileCreate) -> ProfileOut:
    with transaction(session):
        if _name_taken(session, owner_id, data.name, None):
            raise Conflict("A profile with this name already exists")
        profile = Profile(owner_id=owner_id, learned_params={})
        _apply(profile, data.model_dump(exclude_none=True))
        try:
            repo.add(session, profile)
        except IntegrityError as exc:  # concurrent create with the same name
            raise Conflict("A profile with this name already exists") from exc
        audit.record(
            session,
            user_id=owner_id,
            action=AuditAction.PROFILE_CREATED,
            subject=("profile", profile.id),
            details={"surface_type": profile.surface_type},
        )
    return get_profile(session, owner_id, profile.id)


def update_profile(
    session: Session, owner_id: str, profile_id: str, data: ProfileUpdate
) -> ProfileOut:
    with transaction(session):
        profile = get_owned(session, owner_id, profile_id)
        if profile.archived_at is not None:
            raise Conflict("Archived profiles cannot be edited", code=ErrorCode.PROFILE_ARCHIVED)
        fields = data.model_dump(exclude_unset=True)
        if "token_pattern" in fields and fields["token_pattern"] is None:
            fields["pattern_strict"] = False  # clearing the pattern clears strictness
        for key in ("name", "surface_type", "charset", "alignment", "spacing_mode"):
            if key in fields and fields[key] is None:
                raise ValidationFailed(f"{key} cannot be empty")
        if "name" in fields and _name_taken(session, owner_id, fields["name"], profile.id):
            raise Conflict("A profile with this name already exists")
        _apply(profile, fields)
        session.flush()
    return get_profile(session, owner_id, profile_id)


def set_archived(session: Session, owner_id: str, profile_id: str, archived: bool) -> ProfileOut:
    with transaction(session):
        profile = get_owned(session, owner_id, profile_id)
        if archived and profile.archived_at is None:
            profile.archived_at = utcnow()
            audit.record(
                session,
                user_id=owner_id,
                action=AuditAction.PROFILE_ARCHIVED,
                subject=("profile", profile.id),
            )
        elif not archived:
            profile.archived_at = None
    return get_profile(session, owner_id, profile_id)


def delete_profile(session: Session, owner_id: str, profile_id: str, confirm_name: str) -> None:
    """Permanent delete of an archived profile; references and glyphs go with it."""
    with transaction(session):
        profile = get_owned(session, owner_id, profile_id)
        if profile.archived_at is None:
            raise Conflict("Archive the profile before deleting it", code=ErrorCode.INVALID_STATE)
        if confirm_name != profile.name:
            raise ValidationFailed(
                "Type the profile name exactly to confirm",
                details={"fields": [{"path": "confirm_name", "code": "VALIDATION_FAILED",
                                     "message": "Does not match the profile name"}]},
            )  # fmt: skip
        if repo.training_profile_ids(session, [profile.id]):
            raise Conflict("Wait for glyph extraction to finish", code=ErrorCode.INVALID_STATE)
        counts = repo.glyph_counts(session, [profile.id])[profile.id]
        audit.record(
            session,
            user_id=owner_id,
            action=AuditAction.PROFILE_DELETED,
            subject=("profile", profile.id),
            details={
                "references": counts.references,
                "glyphs": sum(c.confirmed + c.auto + c.rejected for c in counts.chars.values()),
            },
        )
        session.delete(profile)
        session.flush()


def require_active(profile: Profile) -> None:
    if profile.archived_at is not None:
        raise Conflict("This profile is archived", code=ErrorCode.PROFILE_ARCHIVED)
