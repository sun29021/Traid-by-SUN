"""ORM → API schema mapping shared by services (keeps URL shapes in one place)."""

from __future__ import annotations

from app.db.models import Glyph, ReferenceImage, StoredFile
from app.schemas.profiles import FileRef, GlyphMetricsOut, GlyphOut, GlyphSource, ReferenceOut

API_PREFIX = "/api/v1"
_THUMB_MIME = frozenset({"image/jpeg", "image/png", "image/tiff"})


def file_url(file_id: str) -> str:
    return f"{API_PREFIX}/files/{file_id}"


def file_ref(stored: StoredFile) -> FileRef:
    return FileRef(
        id=stored.id,
        url=file_url(stored.id),
        thumb_url=f"{file_url(stored.id)}/thumb" if stored.mime_type in _THUMB_MIME else None,
        mime_type=stored.mime_type,
        width=stored.width,
        height=stored.height,
        byte_size=stored.byte_size,
        original_name=stored.original_name,
    )


def reference_out(reference: ReferenceImage, stored: StoredFile, glyph_count: int) -> ReferenceOut:
    return ReferenceOut(
        id=reference.id,
        profile_id=reference.profile_id,
        file=file_ref(stored),
        known_text=reference.known_text,
        status=reference.status,  # type: ignore[arg-type]
        error_code=reference.error_code,
        glyph_count=glyph_count,
        conditions=reference.conditions,
        created_at=reference.created_at,
    )


def glyph_out(glyph: Glyph) -> GlyphOut:
    return GlyphOut(
        id=glyph.id,
        profile_id=glyph.profile_id,
        char=glyph.char,
        status=glyph.status,  # type: ignore[arg-type]
        crop_url=file_url(glyph.crop_file_id),
        source=GlyphSource(type="reference", id=glyph.source_reference_id),
        metrics=GlyphMetricsOut(
            cap_height_px=glyph.cap_height_px,
            stroke_width_px=glyph.stroke_width_px,
            blur_sigma=glyph.blur_sigma,
            noise_sigma=glyph.noise_sigma,
            ink_color=glyph.ink_color,
            bg_luma=glyph.bg_luma,
            contrast=glyph.contrast,
            angle_deg=glyph.angle_deg,
            light_dir_deg=glyph.light_dir_deg,
        ),
        ocr_confidence=glyph.ocr_confidence,
        quality_score=glyph.quality_score,
        use_count=glyph.use_count,
        accept_count=glyph.accept_count,
        reject_count=glyph.reject_count,
        created_at=glyph.created_at,
    )
