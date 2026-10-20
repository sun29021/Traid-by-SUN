"""Make a real glyph look as if it had been captured in the target photo (PRD FR-E09).

Every glyph is turned into an *optical density* layer D = -ln(glyph / glyph background)
per channel. Ink on a surface multiplies the light the surface reflects, so the
rendered pixel is the target's own (inpainted) background times exp(-D):

* local illumination and shading come from the target for free (a shadow across the
  token darkens the new ink exactly as it darkens the paper);
* the glyph's real ink texture (toner speckle, paint density, brush edges) is kept;
* ink colour is matched by scaling each channel's density to the target ink's density
  (Beer-Lambert: thicker or darker ink = proportionally higher density);
* relief glyphs (laser marks, engraving) carry their highlights and shadows as signed
  density, scaled to the target's contrast.

Then the layer is scaled to the target cap height, its blur topped up to the target's
blur, and placed with sub-pixel accuracy. Only this layer is ever warped back into the
photo; the background itself is never resampled.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from app.engine.glyph_select import Choice, GlyphSample
from app.engine.layout import Placement, glyph_baseline, ink_bounds
from app.engine.segment import BlendMode

FloatArray = NDArray[np.float32]

_MIN_RATIO = 0.01  # darkest representable ink: 1 % of the background
_SUPPORT_ALPHA = 8  # alpha (0-255) above which a pixel belongs to the glyph


@dataclass(frozen=True)
class TargetLook:
    """Appearance of the original token, measured in the target photo."""

    density: tuple[float, float, float]  # per-channel optical density of full ink
    contrast: float
    blur_sigma: float
    ink_noise_sigma: float  # grain inside the original ink (grey levels)
    mode: BlendMode


@dataclass(frozen=True)
class Adjustments:
    """Owner adjustments that change appearance (API.md §3.6 ranges)."""

    weight: float = 0.0  # -1 thinner … +1 bolder
    blur: float = 0.0  # added blur sigma (px), negative = sharper (down to the glyph's own)
    ink_tone: float = 0.0  # -1 lighter … +1 darker


@dataclass(frozen=True, eq=False)
class DensityLayer:
    """Glyph layer on a canvas: D (H x W x 3) and support (H x W, 0..1)."""

    density: FloatArray
    support: FloatArray
    origin: tuple[int, int]  # canvas (0, 0) in strip coordinates


def _ellipse(size: int) -> NDArray[np.uint8]:
    size = max(1, size)
    return np.asarray(cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size)), np.uint8)


def glyph_density(sample: GlyphSample) -> tuple[FloatArray, FloatArray]:
    """(D, support) of a glyph crop in its own pixels."""
    rgb = sample.rgba[..., :3]
    alpha = sample.rgba[..., 3]
    own = (alpha > _SUPPORT_ALPHA).astype(np.uint8)
    hole = cv2.dilate(own, _ellipse(5))
    background = cv2.inpaint(rgb, hole * 255, 3, cv2.INPAINT_TELEA).astype(np.float32)
    ratio = (rgb.astype(np.float32) + 1.0) / (background + 1.0)
    density = -np.log(np.clip(ratio, _MIN_RATIO, 1 / _MIN_RATIO))
    support = cv2.GaussianBlur(cv2.dilate(own, _ellipse(3)).astype(np.float32), (0, 0), 0.8)
    support = np.clip(support, 0.0, 1.0)
    return np.asarray(density * support[..., None], np.float32), np.asarray(support, np.float32)


def full_density(density: FloatArray, alpha: NDArray[np.uint8]) -> NDArray[np.float64]:
    """Per-channel density of the solid ink (median over well-covered pixels)."""
    core = alpha >= 200
    if core.sum() < 8:
        core = alpha >= max(int(alpha.max()) // 2, 1)
    if not core.any():
        return np.zeros(3)
    return np.asarray(np.median(density[core], axis=0), dtype=np.float64)


def relief_contrast(density: FloatArray, support: FloatArray) -> float:
    values = density.mean(axis=2)[support > 0.5]
    if values.size < 8:
        return 0.0
    return float(np.percentile(values, 95) - np.percentile(values, 5))


def ink_coverage(density: FloatArray, full: NDArray[np.float64]) -> FloatArray:
    """Per-pixel ink coverage (1 = solid ink) from the summed channel density.

    Coverage keeps the glyph's real density variation (speckle, ragged paint edges)
    while the colour comes entirely from the target ink, so a glyph learned from blue
    paint renders correctly in red paint.
    """
    total = float(full.sum())
    if abs(total) < 0.05:
        return np.zeros(density.shape[:2], np.float32)
    return np.asarray(density.sum(axis=2) / total, np.float32)


def _weight(
    density: FloatArray, support: FloatArray, amount: float
) -> tuple[FloatArray, FloatArray]:
    """Grow (amount > 0) or shrink the strokes by up to ~1 px, blended fractionally."""
    if abs(amount) < 1e-3:
        return density, support
    kernel = _ellipse(3)
    darker = float(density.mean()) >= 0  # dark ink grows by spreading high density
    grow = amount > 0
    op = cv2.dilate if grow == darker else cv2.erode
    moved = np.asarray(op(density, kernel), np.float32)
    moved_support = np.asarray((cv2.dilate if grow else cv2.erode)(support, kernel), np.float32)
    t = min(abs(amount), 1.0)
    return (
        np.asarray((1 - t) * density + t * moved, np.float32),
        np.asarray(
            np.maximum(support, moved_support) if grow else (1 - t) * support + t * moved_support,
            np.float32,
        ),
    )


def render_layer(
    choices: Sequence[Choice],
    placements: Sequence[Placement],
    target: TargetLook,
    adjustments: Adjustments,
) -> DensityLayer | None:
    """All placed glyphs on one canvas in strip coordinates; None when nothing is placed."""
    by_position = {c.position: c for c in choices}
    pieces = []
    for placement in placements:
        choice = by_position[placement.position]
        density, support = glyph_density(choice.sample)
        sample = choice.sample
        if target.mode == "ink":
            coverage = ink_coverage(density, full_density(density, sample.rgba[..., 3]))
            ink = np.asarray(target.density, np.float32) * (1 + 0.5 * adjustments.ink_tone)
            density = np.asarray(coverage[..., None] * ink[None, None, :], np.float32)
        else:
            own = relief_contrast(density, support)
            want = target.contrast
            gain = float(np.clip(want / own, 0.5, 2.0)) if own > 1e-3 and want > 0 else 1.0
            density = np.asarray(density * gain * (1 + 0.5 * adjustments.ink_tone), np.float32)
        density, support = _weight(density, support, adjustments.weight)
        pieces.append((placement, choice, density, support))
    if not pieces:
        return None

    # Canvas bounds in strip coordinates.
    corners = []
    for placement, choice, density, _ in pieces:
        h, w = density.shape[:2]
        x0, _, x1, _ = ink_bounds(choice.sample.rgba)
        s = placement.scale
        left = placement.x_center - (x0 + x1) / 2 * s
        top = placement.baseline - glyph_baseline(choice) * s
        corners.append((left, top, left + w * s, top + h * s))
    pad = 4
    ox = math.floor(min(c[0] for c in corners)) - pad
    oy = math.floor(min(c[1] for c in corners)) - pad
    width = math.ceil(max(c[2] for c in corners)) - ox + pad
    height = math.ceil(max(c[3] for c in corners)) - oy + pad
    canvas = np.zeros((height, width, 3), np.float32)
    canvas_support = np.zeros((height, width), np.float32)

    for (placement, choice, density, support), (left, top, _, _) in zip(
        pieces, corners, strict=True
    ):
        s = placement.scale
        if s < 0.8:  # pre-filter before shrinking so edges do not alias
            pre = 0.5 * math.sqrt(1 / s**2 - 1)
            density = np.asarray(cv2.GaussianBlur(density, (0, 0), pre), np.float32)
            support = np.asarray(cv2.GaussianBlur(support, (0, 0), pre), np.float32)
        matrix = np.array([[s, 0, left - ox], [0, s, top - oy]], dtype=np.float64)
        warped = cv2.warpAffine(density, matrix, (width, height), flags=cv2.INTER_CUBIC)
        warped_support = cv2.warpAffine(support, matrix, (width, height), flags=cv2.INTER_LINEAR)

        # Blur top-up: the glyph's own blur scales with it; add what the target has more.
        own_blur = choice.sample.metrics.blur_sigma * s
        wanted = max(target.blur_sigma + adjustments.blur, 0.0)
        extra = math.sqrt(max(wanted**2 - own_blur**2, 0.0))
        if extra > 0.05:
            warped = cv2.GaussianBlur(warped, (0, 0), extra)
            warped_support = cv2.GaussianBlur(warped_support, (0, 0), extra)
        canvas += np.asarray(warped, np.float32)
        canvas_support = np.maximum(canvas_support, np.asarray(warped_support, np.float32))

    return DensityLayer(
        density=canvas,
        support=np.clip(canvas_support, 0.0, 1.0),
        origin=(ox, oy),
    )
