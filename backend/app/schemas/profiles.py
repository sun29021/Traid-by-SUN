"""Profile, reference image, glyph and file schemas (API.md §2, §3.3-3.5, §3.9)."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints, field_validator

from app.db.models.enums import (
    Alignment,
    GlyphStatus,
    ReferenceStatus,
    SpacingMode,
    SurfaceType,
)
from app.schemas.common import ApiModel, UtcTimestamp
from app.schemas.tasks import TaskOut

ProfileName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
KnownText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)]

MAX_PATTERN_LENGTH = 200
# Nested quantifiers like (a+)+ can make regex matching take exponential time.
_NESTED_QUANTIFIER = re.compile(r"\([^)]*[+*}][^)]*\)\s*[+*{]")


def clean_charset(value: str) -> str:
    """Printable characters only, duplicates removed (order kept), 1-96 characters."""
    if any(not char.isprintable() for char in value):
        raise ValueError("Character set may only contain printable characters")
    unique = "".join(dict.fromkeys(value))
    if not 1 <= len(unique) <= 96:
        raise ValueError("Character set must have between 1 and 96 different characters")
    return unique


def clean_pattern(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    if len(value) > MAX_PATTERN_LENGTH:
        raise ValueError(f"Pattern must be at most {MAX_PATTERN_LENGTH} characters")
    if _NESTED_QUANTIFIER.search(value):
        raise ValueError("Nested quantifiers such as (a+)+ are not allowed")
    try:
        re.compile(value)
    except re.error as exc:
        raise ValueError(f"Not a valid regular expression: {exc.msg}") from exc
    return value


class ProfileFields(ApiModel):
    description: Annotated[str, StringConstraints(max_length=500)] | None = None
    charset: str | None = None
    token_pattern: str | None = None
    pattern_strict: bool | None = None
    alignment: Alignment | None = None
    spacing_mode: SpacingMode | None = None
    ready_threshold: int | None = Field(default=None, ge=1, le=20)
    use_auto_glyphs: bool | None = None

    @field_validator("charset")
    @classmethod
    def _charset(cls, value: str | None) -> str | None:
        return None if value is None else clean_charset(value)

    @field_validator("token_pattern")
    @classmethod
    def _pattern(cls, value: str | None) -> str | None:
        return clean_pattern(value)


class ProfileCreate(ProfileFields):
    name: ProfileName
    surface_type: SurfaceType


class ProfileUpdate(ProfileFields):
    name: ProfileName | None = None
    surface_type: SurfaceType | None = None


class ProfileDelete(ApiModel):
    confirm_name: str


class Coverage(ApiModel):
    ready_chars: int
    total_chars: int
    missing: list[str]


class ProfileStats(ApiModel):
    glyphs_confirmed: int
    glyphs_auto: int
    references: int
    jobs_accepted: int
    acceptance_rate: float | None


ProfileStatus = Literal["draft", "training", "needs_review", "ready"]


class ProfileOut(ApiModel):
    id: str
    name: str
    description: str | None
    surface_type: SurfaceType
    charset: str
    token_pattern: str | None
    pattern_strict: bool
    alignment: Alignment
    spacing_mode: SpacingMode
    ready_threshold: int
    use_auto_glyphs: bool
    engine: str
    status: ProfileStatus
    coverage: Coverage
    stats: ProfileStats
    learned_params: dict[str, Any]
    archived_at: UtcTimestamp | None
    created_at: UtcTimestamp
    updated_at: UtcTimestamp


class CoverageItem(ApiModel):
    char: str
    confirmed: int
    auto: int
    rejected: int
    best_quality: float
    ready: bool


class FileRef(ApiModel):
    id: str
    url: str
    thumb_url: str | None
    mime_type: str
    width: int | None
    height: int | None
    byte_size: int
    original_name: str | None


class ReferenceOut(ApiModel):
    id: str
    profile_id: str
    file: FileRef
    known_text: str | None
    status: ReferenceStatus
    error_code: str | None
    glyph_count: int
    conditions: dict[str, float] | None
    created_at: UtcTimestamp


class ReferenceUpdate(ApiModel):
    known_text: KnownText | None


class UploadIssue(ApiModel):
    name: str | None
    code: str
    message: str


class ReferenceUpload(ApiModel):
    created: list[ReferenceOut]
    skipped: list[UploadIssue]
    rejected: list[UploadIssue]
    task: TaskOut | None


class GlyphSource(ApiModel):
    type: Literal["reference", "job"]
    id: str | None


class GlyphMetricsOut(ApiModel):
    cap_height_px: float
    stroke_width_px: float
    blur_sigma: float
    noise_sigma: float
    ink_color: str
    bg_luma: float
    contrast: float
    angle_deg: float
    light_dir_deg: float | None


class GlyphOut(ApiModel):
    id: str
    profile_id: str
    char: str
    status: GlyphStatus
    crop_url: str
    source: GlyphSource
    metrics: GlyphMetricsOut
    ocr_confidence: float
    quality_score: float
    use_count: int
    accept_count: int
    reject_count: int
    created_at: UtcTimestamp


class GlyphUpdate(ApiModel):
    status: GlyphStatus | None = None
    char: Annotated[str, StringConstraints(min_length=1, max_length=1)] | None = None


class GlyphBulk(ApiModel):
    ids: list[str] = Field(min_length=1, max_length=500)
    action: Literal["confirm", "reject", "relabel"]
    char: Annotated[str, StringConstraints(min_length=1, max_length=1)] | None = None


class BulkResult(ApiModel):
    updated: int
