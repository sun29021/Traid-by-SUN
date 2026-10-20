"""Data access for profiles, reference images and glyphs.

Ownership: profiles carry `owner_id`; references and glyphs are always reached through
an owned profile (joins), so a foreign ID never resolves (DATABASE.md §7).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.orm import Session

from app.core.pagination import Cursor
from app.db.models import Glyph, Profile, ReferenceImage, Task
from app.db.models.enums import GlyphStatus, TaskStatus, TaskSubject
from app.repositories.pagination import before

# ---------------------------------------------------------------- profiles


def get_profile(session: Session, owner_id: str, profile_id: str) -> Profile | None:
    return session.scalar(
        select(Profile).where(Profile.id == profile_id, Profile.owner_id == owner_id)
    )


def get_profile_by_name(session: Session, owner_id: str, name: str) -> Profile | None:
    return session.scalar(select(Profile).where(Profile.owner_id == owner_id, Profile.name == name))


def list_profiles(
    session: Session, owner_id: str, *, archived: bool | None, query: str | None
) -> Sequence[Profile]:
    """Most recently updated first. `archived=None` returns both."""
    statement = select(Profile).where(Profile.owner_id == owner_id)
    if archived is True:
        statement = statement.where(Profile.archived_at.is_not(None))
    elif archived is False:
        statement = statement.where(Profile.archived_at.is_(None))
    if query:
        statement = statement.where(Profile.name.ilike(f"%{query}%"))
    return session.scalars(statement.order_by(Profile.updated_at.desc(), Profile.id)).all()


def add(session: Session, obj: Profile | ReferenceImage | Glyph) -> None:
    session.add(obj)
    session.flush()


@dataclass
class CharCounts:
    confirmed: int = 0
    auto: int = 0
    rejected: int = 0
    best_quality: float = 0.0  # best confirmed (or auto, if allowed) glyph


@dataclass
class ProfileCounts:
    chars: dict[str, CharCounts] = field(default_factory=dict)
    references: int = 0


def glyph_counts(
    session: Session, profile_ids: Sequence[str], *, include_auto_quality: bool = True
) -> dict[str, ProfileCounts]:
    """Per profile and character: glyph counts by status and best quality."""
    result = {pid: ProfileCounts() for pid in profile_ids}
    if not profile_ids:
        return result
    rows = session.execute(
        select(
            Glyph.profile_id,
            Glyph.char,
            Glyph.status,
            func.count(),
            func.max(Glyph.quality_score),
        )
        .where(Glyph.profile_id.in_(profile_ids))
        .group_by(Glyph.profile_id, Glyph.char, Glyph.status)
    ).all()
    for profile_id, char, status, count, best in rows:
        counts = result[profile_id].chars.setdefault(char, CharCounts())
        if status == GlyphStatus.CONFIRMED.value:
            counts.confirmed = int(count)
            counts.best_quality = max(counts.best_quality, float(best or 0.0))
        elif status == GlyphStatus.AUTO.value:
            counts.auto = int(count)
            if include_auto_quality:
                counts.best_quality = max(counts.best_quality, float(best or 0.0))
        else:
            counts.rejected = int(count)
    references = session.execute(
        select(ReferenceImage.profile_id, func.count())
        .where(ReferenceImage.profile_id.in_(profile_ids))
        .group_by(ReferenceImage.profile_id)
    ).all()
    for profile_id, count in references:
        result[profile_id].references = int(count)
    return result


def training_profile_ids(session: Session, profile_ids: Sequence[str]) -> set[str]:
    """Profiles with a queued or running extraction task."""
    if not profile_ids:
        return set()
    rows = session.scalars(
        select(Task.subject_id).where(
            Task.subject_type == TaskSubject.PROFILE.value,
            Task.subject_id.in_(profile_ids),
            Task.status.in_((TaskStatus.QUEUED.value, TaskStatus.RUNNING.value)),
        )
    ).all()
    return {row for row in rows if row}


# ---------------------------------------------------------------- reference images


def _owned_references(owner_id: str) -> Select[ReferenceImage]:
    return (
        select(ReferenceImage)
        .join(Profile, Profile.id == ReferenceImage.profile_id)
        .where(Profile.owner_id == owner_id)
    )


def get_reference(session: Session, owner_id: str, reference_id: str) -> ReferenceImage | None:
    return session.scalar(_owned_references(owner_id).where(ReferenceImage.id == reference_id))


def get_reference_unscoped(session: Session, reference_id: str) -> ReferenceImage | None:
    """Worker-only: the task already carries its owner."""
    return session.get(ReferenceImage, reference_id)


def find_reference(session: Session, profile_id: str, file_id: str) -> ReferenceImage | None:
    return session.scalar(
        select(ReferenceImage).where(
            ReferenceImage.profile_id == profile_id, ReferenceImage.file_id == file_id
        )
    )


def list_references(
    session: Session,
    owner_id: str,
    profile_id: str,
    *,
    statuses: Sequence[str] | None,
    cursor: Cursor | None,
    limit: int,
) -> Sequence[ReferenceImage]:
    statement = _owned_references(owner_id).where(ReferenceImage.profile_id == profile_id)
    if statuses:
        statement = statement.where(ReferenceImage.status.in_(statuses))
    if cursor is not None:
        statement = statement.where(before(ReferenceImage.created_at, ReferenceImage.id, cursor))
    statement = statement.order_by(
        ReferenceImage.created_at.desc(), ReferenceImage.id.desc()
    ).limit(limit + 1)
    return session.scalars(statement).all()


def glyph_counts_by_reference(session: Session, reference_ids: Sequence[str]) -> dict[str, int]:
    if not reference_ids:
        return {}
    rows = session.execute(
        select(Glyph.source_reference_id, func.count())
        .where(Glyph.source_reference_id.in_(reference_ids))
        .group_by(Glyph.source_reference_id)
    ).all()
    return {ref_id: int(count) for ref_id, count in rows if ref_id}


def delete_reference(session: Session, reference: ReferenceImage) -> None:
    session.delete(reference)
    session.flush()


# ---------------------------------------------------------------- glyphs


def _owned_glyphs(owner_id: str) -> Select[Glyph]:
    return (
        select(Glyph)
        .join(Profile, Profile.id == Glyph.profile_id)
        .where(Profile.owner_id == owner_id)
    )


def get_glyph(session: Session, owner_id: str, glyph_id: str) -> Glyph | None:
    return session.scalar(_owned_glyphs(owner_id).where(Glyph.id == glyph_id))


def list_glyphs(
    session: Session,
    owner_id: str,
    profile_id: str,
    *,
    char: str | None,
    statuses: Sequence[str] | None,
    min_quality: float | None,
    offset: int,
    limit: int,
) -> Sequence[Glyph]:
    """Grouped for review: character, then best quality first."""
    statement = _owned_glyphs(owner_id).where(Glyph.profile_id == profile_id)
    if char is not None:
        statement = statement.where(Glyph.char == char)
    if statuses:
        statement = statement.where(Glyph.status.in_(statuses))
    if min_quality is not None:
        statement = statement.where(Glyph.quality_score >= min_quality)
    statement = statement.order_by(Glyph.char, Glyph.quality_score.desc(), Glyph.id)
    return session.scalars(statement.offset(offset).limit(limit + 1)).all()


def set_glyph_status(
    session: Session, profile_id: str, glyph_ids: Sequence[str], status: GlyphStatus
) -> int:
    result = session.execute(
        update(Glyph)
        .where(Glyph.profile_id == profile_id, Glyph.id.in_(glyph_ids))
        .values(status=status.value)
    )
    return int(getattr(result, "rowcount", 0))


def relabel_glyphs(session: Session, profile_id: str, glyph_ids: Sequence[str], char: str) -> int:
    result = session.execute(
        update(Glyph)
        .where(Glyph.profile_id == profile_id, Glyph.id.in_(glyph_ids))
        .values(char=char, status=GlyphStatus.CONFIRMED.value)
    )
    return int(getattr(result, "rowcount", 0))


def reviewed_glyph_quads(session: Session, reference_id: str) -> list[list[list[float]]]:
    """Source quads of glyphs the owner already confirmed or rejected for a reference."""
    return list(
        session.scalars(
            select(Glyph.source_quad).where(
                Glyph.source_reference_id == reference_id,
                Glyph.status != GlyphStatus.AUTO.value,
            )
        ).all()
    )


def delete_auto_glyphs(session: Session, reference_id: str) -> int:
    result = session.execute(
        delete(Glyph).where(
            Glyph.source_reference_id == reference_id, Glyph.status == GlyphStatus.AUTO.value
        )
    )
    return int(getattr(result, "rowcount", 0))
