"""Engine work for edit jobs: the `detect` and `render` tasks, OCR re-read, variants.

Decoded inputs, prepared regions and glyph crops are kept in small in-process caches,
and the synthesizer caches text removal, so a re-render after an adjustment only redoes
layout → harmonize → composite → verify (ARCHITECTURE §3.3).
"""

from __future__ import annotations

import io
import logging
import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable
from dataclasses import dataclass, field
from typing import Any, TypeVar

import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.db.engine import Database
from app.db.models import EditJob, EditJobGlyph, Glyph, Profile, Task
from app.db.models.enums import FileKind, JobStatus, MimeType, SurfaceType
from app.engine.candidates import score_regions
from app.engine.detect import TextDetector
from app.engine.geometry import clip_quad, expand_quad, quad_iou, rectify
from app.engine.glyph_select import GlyphMissingError, GlyphSample
from app.engine.io import decode_image
from app.engine.matte import GlyphMetrics
from app.engine.models import ModelUnavailableError
from app.engine.pipeline import (
    GlyphTransplantSynthesizer,
    PreparationError,
    PreparedRegion,
    RenderParams,
)
from app.engine.types import DecodedImage
from app.repositories import files as files_repo
from app.repositories import jobs as repo
from app.repositories import profiles as profiles_repo
from app.services.files import store_generated_file
from app.services.mappers import file_url
from app.storage.filestore import FileStore
from app.worker.runner import TaskContext

logger = logging.getLogger("traid.jobs")

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


class _Lru:
    """A tiny thread-safe LRU cache."""

    def __init__(self, size: int) -> None:
        self._items: OrderedDict[Hashable, Any] = OrderedDict()
        self._size = size
        self._lock = threading.Lock()

    def get(self, key: Hashable, build: Callable[[], V]) -> V:
        with self._lock:
            if key in self._items:
                self._items.move_to_end(key)
                return self._items[key]  # type: ignore[no-any-return]
        value = build()
        with self._lock:
            self._items[key] = value
            while len(self._items) > self._size:
                self._items.popitem(last=False)
        return value


@dataclass
class JobDeps:
    db: Database
    store: FileStore
    detector: TextDetector
    synthesizer: GlyphTransplantSynthesizer
    _images: _Lru = field(default_factory=lambda: _Lru(4))
    _prepared: _Lru = field(default_factory=lambda: _Lru(8))
    _crops: _Lru = field(default_factory=lambda: _Lru(4000))

    # ------------------------------------------------------------ loaders

    def decoded(self, storage_path: str) -> DecodedImage:
        return self._images.get(
            storage_path, lambda: decode_image(self.store.read_bytes(storage_path))
        )

    def crop(self, storage_path: str) -> np.ndarray:
        def load() -> np.ndarray:
            with Image.open(io.BytesIO(self.store.read_bytes(storage_path))) as image:
                return np.asarray(image.convert("RGBA")).copy()

        return self._crops.get(storage_path, load)

    def prepared(
        self, decoded: DecodedImage, key: tuple[Any, ...], quad: np.ndarray, text: str, mode: str
    ) -> PreparedRegion:
        return self._prepared.get(
            key,
            lambda: self.synthesizer.prepare(decoded.rgb, quad, text, mode),  # type: ignore[arg-type]
        )


def bank_samples(session: Session, deps: JobDeps, profile: Profile) -> list[GlyphSample]:
    samples = []
    for glyph in repo.usable_glyphs(session, profile.id, bool(profile.use_auto_glyphs)):
        stored = files_repo.get(session, profile.owner_id, glyph.crop_file_id)
        if stored is None:
            continue
        samples.append(_sample(glyph, deps.crop(stored.storage_path)))
    return samples


def _sample(glyph: Glyph, rgba: np.ndarray) -> GlyphSample:
    return GlyphSample(
        char=glyph.char,
        rgba=rgba,
        metrics=GlyphMetrics(
            cap_height_px=glyph.cap_height_px,
            stroke_width_px=glyph.stroke_width_px,
            blur_sigma=glyph.blur_sigma,
            noise_sigma=glyph.noise_sigma,
            ink_color=glyph.ink_color,
            bg_luma=glyph.bg_luma,
            contrast=glyph.contrast,
            light_dir_deg=glyph.light_dir_deg,
            isolation=1.0,
            clipped=False,
            quality=glyph.quality_score,
        ),
        angle_deg=glyph.angle_deg,
        baseline_y=glyph.baseline_y,
        source="bank",
        glyph_id=glyph.id,
        accept_count=glyph.accept_count,
        reject_count=glyph.reject_count,
    )


def _png(rgb: np.ndarray, alpha: np.ndarray | None = None) -> bytes:
    image = Image.fromarray(np.ascontiguousarray(rgb), "RGB")
    if alpha is not None:
        image.putalpha(Image.fromarray(np.ascontiguousarray(alpha), "L"))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", compress_level=3)
    return buffer.getvalue()


def _fail(deps: JobDeps, job_id: str, code: str) -> None:
    with deps.db.session() as session:
        job = repo.get_unscoped(session, job_id)
        if job is not None:
            job.status = JobStatus.FAILED.value
            job.error_code = code


# ---------------------------------------------------------------- detect


def handle_detect(deps: JobDeps, ctx: TaskContext) -> None:
    job_id = str(ctx.payload["job_id"])
    with deps.db.session() as session:
        job = repo.get_unscoped(session, job_id)
        if job is None:
            return
        profile = profiles_repo.get_profile(session, job.owner_id, job.profile_id)
        stored = files_repo.get(session, job.owner_id, job.input_file_id)
        if profile is None or stored is None:
            return
        job.status = JobStatus.DETECTING.value
        charset, pattern, typical = profile.charset, profile.token_pattern, profile.typical_region
        path = stored.storage_path

    ctx.report(0.1, "Finding text")
    try:
        decoded = deps.decoded(path)
        regions = deps.detector.detect(decoded.rgb)
    except ModelUnavailableError as exc:
        _fail(deps, job_id, ErrorCode.MODEL_UNAVAILABLE.value)
        raise AppError(str(exc), code=ErrorCode.MODEL_UNAVAILABLE) from exc
    except AppError as exc:
        _fail(deps, job_id, exc.code.value)
        raise
    except Exception:
        _fail(deps, job_id, ErrorCode.INTERNAL_ERROR.value)
        raise

    scored = score_regions(
        regions,
        (decoded.width, decoded.height),
        charset=charset,
        pattern=pattern,
        typical_region=typical,
    )
    with deps.db.session() as session:
        job = repo.get_unscoped(session, job_id)
        if job is None:
            return
        job.regions = [s.to_dict() for s in scored]
        if scored:
            best = scored[0].to_dict()
            job.selected_region_id = best["id"]
            job.selected_quad = best["quad"]
            job.original_text = best["text"].strip() or None
            job.error_code = None
        else:
            job.error_code = ErrorCode.NO_TEXT_FOUND.value
        job.status = JobStatus.DETECTED.value
    ctx.report(1.0, f"{len(scored)} text regions found")


def read_region_text(
    deps: JobDeps, session: Session, job: EditJob, quad: list[list[float]]
) -> str | None:
    """OCR of a drawn region: the line overlapping the quad most, or None."""
    stored = files_repo.get(session, job.owner_id, job.input_file_id)
    if stored is None:
        return None
    decoded = deps.decoded(stored.storage_path)
    points = np.asarray(quad, dtype=np.float32)
    area = clip_quad(expand_quad(points, 0.6), decoded.width, decoded.height)
    x0, y0 = np.floor(area.min(axis=0)).astype(int)
    x1, y1 = np.ceil(area.max(axis=0)).astype(int) + 1
    crop = np.ascontiguousarray(decoded.rgb[y0:y1, x0:x1])
    try:
        regions = deps.detector.detect(crop)
    except Exception:  # OCR is a convenience here; the owner can type the text
        logger.warning("OCR re-read failed", extra={"job_id": job.id})
        return None
    local = points - np.array([x0, y0], dtype=np.float32)
    best = max(regions, key=lambda r: quad_iou(r.quad, local), default=None)
    if best is None or quad_iou(best.quad, local) < 0.2:
        # A tight manual box may cut the detector's line; read the box itself.
        rect = rectify(
            decoded.rgb, clip_quad(expand_quad(points, 0.25), decoded.width, decoded.height)
        )
        regions = deps.detector.detect(rect.patch)
        best = max(regions, key=lambda r: len(r.text), default=None)
    return best.text if best is not None else None


# ---------------------------------------------------------------- render


@dataclass(frozen=True)
class _RenderInput:
    job_id: str
    owner_id: str
    task_created: Any
    path: str
    quad: list[list[float]]
    original_text: str
    mode: str
    alignment: str
    spacing_mode: str
    seed: int
    bank: list[GlyphSample]


def _load_render_input(deps: JobDeps, ctx: TaskContext) -> _RenderInput | None:
    job_id = str(ctx.payload["job_id"])
    with deps.db.session() as session:
        job = repo.get_unscoped(session, job_id)
        if job is None or not job.selected_quad or not job.original_text:
            return None
        profile = profiles_repo.get_profile(session, job.owner_id, job.profile_id)
        stored = files_repo.get(session, job.owner_id, job.input_file_id)
        if profile is None or stored is None:
            return None
        job.status = JobStatus.RENDERING.value
        task = session.get(Task, ctx.task_id)
        return _RenderInput(
            job_id=job.id,
            owner_id=job.owner_id,
            task_created=task.created_at if task else None,
            path=stored.storage_path,
            quad=job.selected_quad,
            original_text=job.original_text,
            mode=SurfaceType(profile.surface_type).blend_mode,
            alignment=profile.alignment,
            spacing_mode=profile.spacing_mode,
            seed=job.seed,
            bank=bank_samples(session, deps, profile),
        )


def handle_render(deps: JobDeps, ctx: TaskContext) -> None:
    data = _load_render_input(deps, ctx)
    if data is None:
        return
    new_text = str(ctx.payload["new_text"])
    params_data = dict(ctx.payload.get("params") or {})
    try:
        params = RenderParams.from_dict(params_data)
        ctx.report(0.1, "Measuring the old token")
        decoded = deps.decoded(data.path)
        quad = np.asarray(data.quad, dtype=np.float32)
        key = (data.path, tuple(map(tuple, data.quad)), data.original_text, data.mode)
        prepared = deps.prepared(decoded, key, quad, data.original_text, data.mode)
        ctx.report(0.3, "Removing and rendering")
        result = deps.synthesizer.render(
            decoded.rgb,
            prepared,
            new_text,
            data.bank,
            params,
            seed=data.seed,
            alignment=data.alignment,  # type: ignore[arg-type]
            spacing_mode=data.spacing_mode,  # type: ignore[arg-type]
        )
    except GlyphMissingError as exc:
        _fail(deps, data.job_id, ErrorCode.GLYPH_MISSING.value)
        raise AppError(
            str(exc), code=ErrorCode.GLYPH_MISSING, details={"missing": exc.missing}
        ) from exc
    except PreparationError as exc:
        _fail(deps, data.job_id, exc.code)
        raise AppError(str(exc), code=ErrorCode(exc.code)) from exc
    except ModelUnavailableError as exc:
        _fail(deps, data.job_id, ErrorCode.MODEL_UNAVAILABLE.value)
        raise AppError(str(exc), code=ErrorCode.MODEL_UNAVAILABLE) from exc
    except MemoryError as exc:
        _fail(deps, data.job_id, ErrorCode.OUT_OF_MEMORY.value)
        raise AppError("Not enough memory for this image", code=ErrorCode.OUT_OF_MEMORY) from exc
    except AppError as exc:
        _fail(deps, data.job_id, exc.code.value)
        raise
    except Exception:
        logger.exception("Render failed", extra={"job_id": data.job_id})
        _fail(deps, data.job_id, ErrorCode.INTERNAL_ERROR.value)
        raise

    ctx.report(0.9, "Saving the result")
    with deps.db.session() as session:
        job = repo.get_unscoped(session, data.job_id)
        if job is None:
            return
        if data.task_created is not None and repo.newer_render_queued(
            session, job.id, ctx.task_id, data.task_created
        ):
            return  # a newer adjustment is queued; it will write the result
        height, width = result.image.shape[:2]
        result_file = store_generated_file(
            session,
            deps.store,
            owner_id=data.owner_id,
            data=_png(result.image, decoded.alpha),
            kind=FileKind.RESULT,
            mime_type=MimeType.PNG,
            width=width,
            height=height,
        )
        mask_file = store_generated_file(
            session,
            deps.store,
            owner_id=data.owner_id,
            data=_png(np.repeat(result.changed_mask[..., None], 3, axis=2)),
            kind=FileKind.MASK,
            mime_type=MimeType.PNG,
            width=width,
            height=height,
        )
        uses = [u.to_dict() for u in result.glyphs_used]
        repo.replace_job_glyphs(
            session,
            job.id,
            [
                EditJobGlyph(
                    job_id=job.id, position=u.position, glyph_id=u.glyph_id, source=u.source
                )
                for u in result.glyphs_used
                if u.source in ("same_image", "bank")
            ],
        )
        repo.bump_use_counts(
            session, [u.glyph_id for u in result.glyphs_used if u.glyph_id and u.source == "bank"]
        )
        job.result_file_id = result_file.id
        job.mask_file_id = mask_file.id
        job.quality = result.quality.to_dict()
        job.quality_overall = result.quality.overall
        job.geometry = {
            "render": {
                "layout_mode": result.layout_mode,
                "glyphs_used": uses,
                "warnings": list(result.warnings),
                "timings_ms": result.timings_ms,
            }
        }
        job.engine_version = deps.synthesizer.version
        job.error_code = None
        job.status = JobStatus.RENDERED.value
    ctx.report(1.0, f"Rendered ({result.quality.overall})")


def glyph_variants(
    deps: JobDeps, session: Session, job: EditJob, profile: Profile, position: int
) -> list[dict[str, Any]]:
    """Top alternatives for one character of the job's new text."""
    if not job.new_text or not 0 <= position < len(job.new_text) or job.new_text[position] == " ":
        return []
    if not job.selected_quad or not job.original_text:
        return []
    stored = files_repo.get(session, job.owner_id, job.input_file_id)
    if stored is None:
        return []
    decoded = deps.decoded(stored.storage_path)
    mode = SurfaceType(profile.surface_type).blend_mode
    key = (stored.storage_path, tuple(map(tuple, job.selected_quad)), job.original_text, mode)
    try:
        prepared = deps.prepared(
            decoded, key, np.asarray(job.selected_quad, np.float32), job.original_text, mode
        )
    except PreparationError:
        return []
    bank = bank_samples(session, deps, profile)
    crops = {g.id: g.crop_file_id for g in repo.usable_glyphs(session, profile.id, True)}
    return [
        {
            "glyph_id": sample.glyph_id,
            "source": sample.source,
            "score": round(score, 4),
            "crop_url": file_url(crops[sample.glyph_id]) if sample.glyph_id in crops else None,
        }
        for score, sample in deps.synthesizer.variants(prepared, bank, job.new_text[position])
    ]
