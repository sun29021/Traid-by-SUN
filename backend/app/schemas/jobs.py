"""Edit job schemas (API.md §2 EditJob, §3.6)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from app.db.models.enums import JobStatus
from app.schemas.common import ApiModel, UtcTimestamp
from app.schemas.profiles import FileRef
from app.schemas.tasks import TaskOut

Point = Annotated[list[float], Field(min_length=2, max_length=2)]
QuadIn = Annotated[list[Point], Field(min_length=4, max_length=4)]
TokenText = Annotated[str, StringConstraints(min_length=1, max_length=64)]
QualityStatus = Literal["pass", "warn", "fail"]


class RegionOut(ApiModel):
    id: str
    quad: list[list[float]]
    text: str
    confidence: float
    score: float
    reasons: list[str]


class GlyphUseOut(ApiModel):
    position: int
    char: str
    source: Literal["same_image", "bank", "kept"]
    glyph_id: str | None
    score: float | None


class QualityCheckOut(ApiModel):
    id: str
    status: QualityStatus
    value: float | str | bool | None
    threshold: float | None = None


class QualityOut(ApiModel):
    overall: QualityStatus
    checks: list[QualityCheckOut]


class RenderParamsIn(ApiModel):
    """Owner adjustments; ranges from API.md §3.6 (distances in rectified pixels)."""

    dx: float = Field(0.0, ge=-50, le=50)
    dy: float = Field(0.0, ge=-50, le=50)
    scale: float = Field(1.0, ge=0.8, le=1.2)
    spacing: float = Field(0.0, ge=-10, le=10)
    weight: float = Field(0.0, ge=-1, le=1)
    blur: float = Field(0.0, ge=-2, le=2)
    ink_tone: float = Field(0.0, ge=-1, le=1)
    grain: float = Field(1.0, ge=0, le=3)
    glyph_overrides: dict[str, str] = Field(default_factory=dict, max_length=64)


class EditJobOut(ApiModel):
    id: str
    profile_id: str
    batch_id: str | None
    status: JobStatus
    input: FileRef
    result: FileRef | None
    mask: FileRef | None
    regions: list[RegionOut]
    selected_region_id: str | None
    selected_quad: list[list[float]] | None
    original_text: str | None
    new_text: str | None
    params: RenderParamsIn
    glyphs_used: list[GlyphUseOut]
    quality: QualityOut | None
    layout_mode: Literal["slots", "relayout"] | None
    warnings: list[str]
    engine_version: str | None
    seed: int
    reject_reason: str | None
    error_code: str | None
    accepted_at: UtcTimestamp | None
    exported_at: UtcTimestamp | None
    created_at: UtcTimestamp
    updated_at: UtcTimestamp


class JobCreated(ApiModel):
    job: EditJobOut
    task: TaskOut


class RegionUpdate(ApiModel):
    """Choose a detected region or draw one; optionally correct the old text."""

    region_id: Annotated[str, StringConstraints(max_length=16)] | None = None
    quad: QuadIn | None = None
    original_text: TokenText | None = None


class RenderRequest(ApiModel):
    new_text: TokenText
    params: RenderParamsIn | None = None


class RejectRequest(ApiModel):
    reason: Annotated[str, StringConstraints(max_length=300)] | None = None


ShortText = Annotated[str, StringConstraints(max_length=300)]
LongText = Annotated[str, StringConstraints(max_length=2000)]
Keyword = Annotated[str, StringConstraints(min_length=1, max_length=64)]


class ExportMetadata(ApiModel):
    """Descriptive metadata for the exported file. Capture data (camera, date taken,
    location, serial numbers) is deliberately not offered (engine/metadata.py)."""

    title: ShortText | None = None
    description: LongText | None = None
    author: ShortText | None = None
    copyright: ShortText | None = None
    keywords: Annotated[list[Keyword], Field(max_length=30)] | None = None
    comment: LongText | None = None


class ExportRequest(ApiModel):
    format: Literal["original", "jpeg", "png", "tiff"] | None = None
    filename_pattern: (
        Annotated[str, StringConstraints(max_length=120, pattern=r"^[A-Za-z0-9_{}.\-]+$")] | None
    ) = None
    metadata: ExportMetadata | None = None


class ExportOut(ApiModel):
    file: FileRef
    download_name: str


class GlyphVariantOut(ApiModel):
    glyph_id: str | None
    source: Literal["same_image", "bank"]
    score: float
    crop_url: str | None
