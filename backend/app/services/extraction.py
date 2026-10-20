"""`extract_glyphs` task: reference images → glyph bank (IMPLEMENTATION_PLAN.md 5.4).

Each reference is processed independently: one unreadable photo marks only that
reference as failed. Re-extraction replaces the reference's `auto` glyphs but keeps
the owner's decisions: a new candidate overlapping an already confirmed or rejected
glyph is not added again.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import numpy as np
from PIL import Image

from app.core.errors import AppError, ErrorCode
from app.db.engine import Database
from app.db.models import Glyph
from app.db.models.enums import FileKind, GlyphStatus, ReferenceStatus, SurfaceType
from app.engine.detect import TextDetector
from app.engine.extract import ExtractionResult, GlyphCandidate, extract_from_image
from app.engine.geometry import quad_iou
from app.engine.io import decode_image
from app.engine.models import ModelUnavailableError
from app.repositories import files as files_repo
from app.repositories import profiles as repo
from app.services.files import store_generated_png
from app.storage.filestore import FileStore
from app.worker.runner import TaskContext

logger = logging.getLogger("traid.extraction")

# A new candidate this similar to a reviewed glyph is the same character again.
SAME_GLYPH_IOU = 0.5


@dataclass(frozen=True)
class ExtractionDeps:
    db: Database
    store: FileStore
    detector: TextDetector


def _png(rgba: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(rgba), "RGBA").save(buffer, format="PNG")
    return buffer.getvalue()


def _set_status(
    deps: ExtractionDeps, reference_id: str, status: ReferenceStatus, error: str | None = None
) -> None:
    with deps.db.session() as session:
        reference = repo.get_reference_unscoped(session, reference_id)
        if reference is not None:
            reference.status = status.value
            reference.error_code = error


def _is_reviewed(candidate: GlyphCandidate, reviewed: list[np.ndarray]) -> bool:
    return any(quad_iou(candidate.source_quad, quad) > SAME_GLYPH_IOU for quad in reviewed)


def _store(
    deps: ExtractionDeps,
    owner_id: str,
    profile_id: str,
    reference_id: str,
    result: ExtractionResult,
) -> int:
    """Replace the reference's auto glyphs with `result` in one transaction."""
    with deps.db.session() as session:
        reference = repo.get_reference_unscoped(session, reference_id)
        if reference is None:  # deleted while we worked
            return 0
        repo.delete_auto_glyphs(session, reference_id)
        reviewed = [
            np.asarray(q, dtype=np.float32)
            for q in repo.reviewed_glyph_quads(session, reference_id)
        ]
        added = 0
        for candidate in result.glyphs:
            if _is_reviewed(candidate, reviewed):
                continue
            stored = store_generated_png(
                session,
                deps.store,
                owner_id=owner_id,
                data=_png(candidate.rgba),
                kind=FileKind.GLYPH,
                width=int(candidate.rgba.shape[1]),
                height=int(candidate.rgba.shape[0]),
            )
            m = candidate.metrics
            repo.add(
                session,
                Glyph(
                    profile_id=profile_id,
                    source_reference_id=reference_id,
                    crop_file_id=stored.id,
                    char=candidate.char,
                    status=GlyphStatus.AUTO.value,
                    source_quad=[
                        [round(float(x), 2), round(float(y), 2)] for x, y in candidate.source_quad
                    ],
                    cap_height_px=max(m.cap_height_px, 0.01),
                    stroke_width_px=m.stroke_width_px,
                    blur_sigma=m.blur_sigma,
                    noise_sigma=m.noise_sigma,
                    ink_color=m.ink_color,
                    bg_luma=float(np.clip(m.bg_luma, 0, 1)),
                    contrast=float(np.clip(m.contrast, 0, 1)),
                    angle_deg=float(np.clip(candidate.angle_deg, -90, 90)),
                    light_dir_deg=m.light_dir_deg % 360 if m.light_dir_deg is not None else None,
                    ocr_confidence=candidate.ocr_confidence,
                    quality_score=m.quality,
                ),
            )
            added += 1
        reference.status = ReferenceStatus.PROCESSED.value
        reference.error_code = None
        reference.conditions = result.conditions
        return added


def handle_extract_glyphs(deps: ExtractionDeps, ctx: TaskContext) -> None:
    profile_id = str(ctx.payload["profile_id"])
    reference_ids = [str(r) for r in ctx.payload["reference_ids"]]
    with deps.db.session() as session:
        profile = repo.get_profile(session, ctx.owner_id, profile_id)
        if profile is None:
            return  # deleted after the task was queued
        charset = profile.charset
        mode = SurfaceType(profile.surface_type).blend_mode

    failed = 0
    total = len(reference_ids)
    for index, reference_id in enumerate(reference_ids):
        ctx.report(index / max(total, 1), f"Extracting glyphs {index + 1}/{total}")
        with deps.db.session() as session:
            reference = repo.get_reference_unscoped(session, reference_id)
            if reference is None or reference.profile_id != profile_id:
                continue
            reference.status = ReferenceStatus.PROCESSING.value
            stored = files_repo.get(session, ctx.owner_id, reference.file_id)
            known_text = reference.known_text
        if stored is None:
            _set_status(deps, reference_id, ReferenceStatus.FAILED, ErrorCode.STORAGE_ERROR.value)
            failed += 1
            continue

        try:
            image = decode_image(deps.store.read_bytes(stored.storage_path)).rgb
            result = extract_from_image(
                image,
                deps.detector,
                charset=charset,
                mode=mode,  # type: ignore[arg-type]
                known_text=known_text,
            )
        except ModelUnavailableError as exc:
            # Every remaining image would fail the same way: stop the whole task.
            for pending in reference_ids[index:]:
                _set_status(
                    deps, pending, ReferenceStatus.FAILED, ErrorCode.MODEL_UNAVAILABLE.value
                )
            raise AppError(str(exc), code=ErrorCode.MODEL_UNAVAILABLE) from exc
        except AppError as exc:
            _set_status(deps, reference_id, ReferenceStatus.FAILED, exc.code.value)
            failed += 1
            continue
        except Exception:
            logger.exception("Glyph extraction failed", extra={"reference_id": reference_id})
            _set_status(deps, reference_id, ReferenceStatus.FAILED, ErrorCode.INTERNAL_ERROR.value)
            failed += 1
            continue

        if result.error_code is not None:
            _set_status(deps, reference_id, ReferenceStatus.FAILED, result.error_code)
            failed += 1
            continue
        _store(deps, ctx.owner_id, profile_id, reference_id, result)

    done = total - failed
    ctx.report(
        1.0, f"{done} of {total} images processed" + (f", {failed} failed" if failed else "")
    )
