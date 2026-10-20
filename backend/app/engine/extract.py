"""From one reference image to glyph candidates (IMPLEMENTATION_PLAN.md task 5.4).

detect → choose lines → pad and rectify → segment → matte. Pure engine code: the
caller stores the results. Spaces never become glyphs; characters outside the
profile's character set are segmented (they keep the alignment right) but skipped.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher

import numpy as np

from app.engine.detect import TextDetector
from app.engine.geometry import clip_quad, expand_quad, rectify, transform_points
from app.engine.matte import GlyphMetrics, extract_glyphs
from app.engine.segment import BlendMode, segment
from app.engine.types import Quad, Region, RGBImage

# Padding around a detected line before cutting the strip: characters must not touch
# the strip border (measured in Phase 5: tight boxes made segmentation drop letters).
STRIP_PADDING = 0.25
# A line is used when this share of its characters belongs to the profile's charset.
MIN_CHARSET_SHARE = 0.8
# Known text must match a detected line at least this well to choose that line.
MIN_KNOWN_TEXT_SIMILARITY = 0.5


@dataclass(frozen=True, eq=False)
class GlyphCandidate:
    char: str
    rgba: np.ndarray
    source_quad: Quad  # crop corners in image coordinates
    metrics: GlyphMetrics
    ocr_confidence: float
    angle_deg: float
    baseline_y: float  # text baseline inside the crop (px from its top)


@dataclass(frozen=True, eq=False)
class ExtractionResult:
    glyphs: list[GlyphCandidate] = field(default_factory=list)
    lines: int = 0
    conditions: dict[str, float] = field(default_factory=dict)
    error_code: str | None = None  # NO_TEXT_FOUND / SEGMENTATION_FAILED


def line_angle(quad: Quad) -> float:
    """Angle of the text baseline in degrees, folded into [-90, 90]."""
    dx, dy = (quad[1] - quad[0]).astype(float)
    angle = math.degrees(math.atan2(dy, dx))
    return ((angle + 90.0) % 180.0) - 90.0


def _normalise(text: str) -> str:
    return text.replace(" ", "").upper()


def choose_lines(
    regions: Sequence[Region], charset: str, known_text: str | None
) -> list[tuple[Region, str]]:
    """(region, labels without spaces) for every line worth extracting."""
    if known_text:
        target = _normalise(known_text)
        scored = [(SequenceMatcher(None, _normalise(r.text), target).ratio(), r) for r in regions]
        best = max(scored, key=lambda pair: pair[0], default=None)
        if best is None or best[0] < MIN_KNOWN_TEXT_SIMILARITY:
            return []
        return [(best[1], known_text.replace(" ", ""))]

    allowed = set(charset)
    chosen = []
    for region in regions:
        labels = region.text.replace(" ", "")
        if labels and sum(c in allowed for c in labels) / len(labels) >= MIN_CHARSET_SHARE:
            chosen.append((region, labels))
    return chosen


def _positions_without_spaces(region: Region) -> list[float]:
    if len(region.char_positions) != len(region.text):
        return []
    return [p for c, p in zip(region.text, region.char_positions, strict=True) if c != " "]


def _confidences_without_spaces(region: Region, count: int) -> list[float]:
    if len(region.char_confidences) == len(region.text):
        kept = [c for ch, c in zip(region.text, region.char_confidences, strict=True) if ch != " "]
        if len(kept) == count:
            return kept
    return [region.confidence] * count


def extract_from_image(
    image: RGBImage,
    detector: TextDetector,
    *,
    charset: str,
    mode: BlendMode,
    known_text: str | None = None,
) -> ExtractionResult:
    regions = detector.detect(image)
    if not regions:
        return ExtractionResult(error_code="NO_TEXT_FOUND")
    lines = choose_lines(regions, charset, known_text)
    if not lines:
        return ExtractionResult(error_code="NO_TEXT_FOUND")

    height, width = image.shape[:2]
    allowed = set(charset) - {" "}
    glyphs: list[GlyphCandidate] = []
    for region, labels in lines:
        quad = clip_quad(expand_quad(region.quad, STRIP_PADDING), width, height)
        rect = rectify(image, quad)
        confidences = _confidences_without_spaces(region, len(labels))
        result = segment(
            rect.patch,
            labels,
            _positions_without_spaces(region),
            mode=mode,
            confidences=confidences,
        )
        angle = line_angle(region.quad)
        for crop in extract_glyphs(rect.patch, result, mode):
            if crop.char not in allowed:
                continue
            x0, y0, x1, y1 = crop.box
            corners = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float32)
            glyphs.append(
                GlyphCandidate(
                    char=crop.char,
                    rgba=crop.rgba,
                    source_quad=transform_points(corners, rect.to_image),
                    metrics=crop.metrics,
                    ocr_confidence=float(np.clip(crop.confidence, 0.0, 1.0)),
                    angle_deg=angle,
                    baseline_y=crop.baseline_y,
                )
            )

    if not glyphs:
        return ExtractionResult(lines=len(lines), error_code="SEGMENTATION_FAILED")
    return ExtractionResult(glyphs=glyphs, lines=len(lines), conditions=_conditions(glyphs))


def _conditions(glyphs: Sequence[GlyphCandidate]) -> dict[str, float]:
    """Median capture conditions of an image, shown on the References tab."""

    def median(values: Sequence[float]) -> float:
        return round(float(np.median(values)), 4)

    return {
        "blur_sigma": median([g.metrics.blur_sigma for g in glyphs]),
        "noise_sigma": median([g.metrics.noise_sigma for g in glyphs]),
        "contrast": median([g.metrics.contrast for g in glyphs]),
        "bg_luma": median([g.metrics.bg_luma for g in glyphs]),
        "angle_deg": median([g.angle_deg for g in glyphs]),
        "cap_height_px": median([g.metrics.cap_height_px for g in glyphs]),
    }
