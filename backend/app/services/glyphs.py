"""Glyph review: list, confirm, reject, relabel (PRD US-13, API.md §3.5)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.errors import ErrorCode, NotFound, ValidationFailed
from app.core.pagination import decode_offset, encode_offset
from app.db.models.enums import GlyphStatus
from app.db.transaction import transaction
from app.repositories import profiles as repo
from app.schemas.profiles import GlyphBulk, GlyphOut, GlyphUpdate
from app.services import profiles as profiles_service
from app.services.mappers import glyph_out


def _check_char(char: str, charset: str) -> None:
    if char == " " or char not in charset:
        raise ValidationFailed(
            f"'{char}' is not in this profile's character set",
            code=ErrorCode.CHAR_NOT_IN_CHARSET,
        )


def list_glyphs(
    session: Session,
    owner_id: str,
    profile_id: str,
    *,
    char: str | None,
    statuses: Sequence[GlyphStatus] | None,
    min_quality: float | None,
    cursor: str | None,
    limit: int,
) -> tuple[list[GlyphOut], str | None]:
    """Character order, best first. The cursor is opaque (an offset inside)."""
    profiles_service.get_owned(session, owner_id, profile_id)
    offset = decode_offset(cursor) if cursor else 0
    rows = repo.list_glyphs(
        session,
        owner_id,
        profile_id,
        char=char,
        statuses=[s.value for s in statuses] if statuses else None,
        min_quality=min_quality,
        offset=offset,
        limit=limit,
    )
    page = list(rows[:limit])
    next_cursor = encode_offset(offset + limit) if len(rows) > limit else None
    return [glyph_out(g) for g in page], next_cursor


def update_glyph(session: Session, owner_id: str, glyph_id: str, data: GlyphUpdate) -> GlyphOut:
    with transaction(session):
        glyph = repo.get_glyph(session, owner_id, glyph_id)
        if glyph is None:
            raise NotFound("Glyph not found")
        if data.char is not None:
            profile = profiles_service.get_owned(session, owner_id, glyph.profile_id)
            _check_char(data.char, profile.charset)
            glyph.char = data.char
            # A relabel is a review decision unless the owner set a status explicitly.
            glyph.status = (data.status or GlyphStatus.CONFIRMED).value
        elif data.status is not None:
            glyph.status = data.status.value
        session.flush()
        return glyph_out(glyph)


def bulk_update(session: Session, owner_id: str, profile_id: str, data: GlyphBulk) -> int:
    with transaction(session):
        profile = profiles_service.get_owned(session, owner_id, profile_id)
        if data.action == "relabel":
            if data.char is None:
                raise ValidationFailed("Relabel needs a character")
            _check_char(data.char, profile.charset)
            return repo.relabel_glyphs(session, profile.id, data.ids, data.char)
        status = GlyphStatus.CONFIRMED if data.action == "confirm" else GlyphStatus.REJECTED
        return repo.set_glyph_status(session, profile.id, data.ids, status)
