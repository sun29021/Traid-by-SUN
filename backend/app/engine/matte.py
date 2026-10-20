"""Glyph extraction: soft-masked RGBA crops of real characters plus metrics.

PRD FR-E05 / FR-E15, ARCHITECTURE.md §10.1.

Ink mode (print, paint): the background behind the ink is estimated by inpainting
the ink pixels; alpha is the projection of each pixel onto the background→ink colour
line, so anti-aliased edges and uneven ink density are kept.

Relief mode (laser marks, engraving): there is no single ink colour; the glyph is the
stroke plus its highlight/shadow rim, with a softened mask. The light direction (from
shadow side to highlight side) is measured so glyph selection can match lighting.

The RGB channels are always the original pixels: the texture of the real print is what
makes a transplanted glyph look natural.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

from app.engine.segment import BlendMode, CharBox, Segmentation
from app.engine.types import RGBImage

_SQRT_2PI = math.sqrt(2 * math.pi)
# A perfectly sharp sampled edge spreads over two central-difference taps, which reads
# as sigma = 2 / sqrt(2*pi) ~ 0.8 px of blur; remove that bias.
_INTRINSIC_BLUR = 2.0 / _SQRT_2PI


@dataclass(frozen=True)
class GlyphMetrics:
    cap_height_px: float
    stroke_width_px: float
    blur_sigma: float
    noise_sigma: float
    ink_color: str  # "#rrggbb"
    bg_luma: float  # 0..1
    contrast: float  # 0..1
    light_dir_deg: float | None  # relief only
    isolation: float  # 1 = no foreign ink in the crop
    clipped: bool  # touches the strip border (incomplete glyph)
    quality: float  # 0..1


@dataclass(frozen=True, eq=False)
class GlyphCrop:
    char: str
    rgba: NDArray[np.uint8]  # H x W x 4
    box: tuple[int, int, int, int]  # crop extent in strip coordinates (x0, y0, x1, y1)
    metrics: GlyphMetrics
    confidence: float  # recogniser confidence for this character position
    baseline_y: float  # text baseline in crop coordinates (px from the crop's top edge)


def _luma(rgb: NDArray[Any]) -> NDArray[np.float32]:
    weights = np.array([0.299, 0.587, 0.114], dtype=np.float32)
    return np.asarray(rgb.astype(np.float32) @ weights, dtype=np.float32)


def _hex(color: NDArray[np.floating]) -> str:
    r, g, b = (int(np.clip(round(float(v)), 0, 255)) for v in color)
    return f"#{r:02x}{g:02x}{b:02x}"


def _ellipse(size: int) -> NDArray[np.uint8]:
    size = max(1, size)
    return np.asarray(cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size)), np.uint8)


def estimate_background(strip: RGBImage, ink: NDArray[np.bool_]) -> NDArray[np.float32]:
    """The surface without the text: ink pixels (slightly dilated) filled by inpainting."""
    mask = cv2.dilate(ink.astype(np.uint8) * 255, _ellipse(3))
    filled = cv2.inpaint(strip, mask, 3, cv2.INPAINT_TELEA)
    return np.asarray(filled, dtype=np.float32)


def estimate_blur(gray: NDArray[np.float32], contrast_levels: float) -> float:
    """Gaussian sigma (px) from the steepest edges: for a blurred step of height c,
    max gradient = c / (sigma * sqrt(2 * pi))."""
    if contrast_levels < 8:
        return 0.0
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3) / 8.0
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3) / 8.0
    magnitude = np.hypot(gx, gy)
    steepest = float(np.percentile(magnitude, 99.5))
    if steepest <= 1e-3:
        return 0.0
    measured = contrast_levels / (_SQRT_2PI * steepest)
    return float(math.sqrt(max(measured**2 - _INTRINSIC_BLUR**2, 0.0)))


def estimate_noise(gray: NDArray[np.float32], background: NDArray[np.bool_]) -> float:
    """Robust sigma (grey levels) of the fine grain on plain background pixels."""
    residual = gray - cv2.GaussianBlur(gray, (0, 0), 1.5)
    values = residual[background]
    if values.size < 30:
        return 0.0
    median = float(np.median(values))
    return float(1.4826 * np.median(np.abs(values - median)))


def light_direction(gray: NDArray[np.float32], region: NDArray[np.bool_]) -> float | None:
    """Angle (deg) from the shadow centroid to the highlight centroid inside `region`."""
    values = gray[region]
    if values.size < 20:
        return None
    middle = float(np.median(values))
    spread = float(np.percentile(values, 90) - np.percentile(values, 10))
    if spread < 6:
        return None
    ys, xs = np.nonzero(region)
    bright = values > middle + 0.25 * spread
    dark = values < middle - 0.25 * spread
    if bright.sum() < 5 or dark.sum() < 5:
        return None
    dx = float(xs[bright].mean() - xs[dark].mean())
    dy = float(ys[bright].mean() - ys[dark].mean())
    if math.hypot(dx, dy) < 0.5:
        return None
    return math.degrees(math.atan2(dy, dx)) % 360.0


def _stroke_width(mask: NDArray[np.bool_]) -> float:
    if not mask.any():
        return 0.0
    distance = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 3)
    return float(2.0 * np.percentile(distance[mask], 90))


def extract_glyphs(strip: RGBImage, segmentation: Segmentation, mode: BlendMode) -> list[GlyphCrop]:
    """One RGBA crop + metrics per segmented character, left to right."""
    height, width = strip.shape[:2]
    cap = max(segmentation.cap_height, 1.0)
    gray = _luma(strip)
    background = estimate_background(strip, segmentation.ink)
    bg_gray = _luma(background)

    core = cv2.erode(segmentation.ink.astype(np.uint8), _ellipse(3)).astype(bool)
    ink_pixels = strip[core] if core.sum() >= 10 else strip[segmentation.ink]
    ink_color = (
        np.median(ink_pixels.astype(np.float32), axis=0)
        if ink_pixels.size
        else np.zeros(3, np.float32)
    )
    plain = ~cv2.dilate(segmentation.ink.astype(np.uint8), _ellipse(5)).astype(bool)
    noise = estimate_noise(gray, plain)

    crops: list[GlyphCrop] = []
    pad = max(2, round(0.2 * cap))
    for box in segmentation.chars:
        x0, y0 = max(box.x0 - pad, 0), max(box.y0 - pad, 0)
        x1, y1 = min(box.x1 + pad, width), min(box.y1 + pad, height)
        own = np.zeros((y1 - y0, x1 - x0), dtype=bool)
        own[box.y0 - y0 : box.y1 - y0, box.x0 - x0 : box.x1 - x0] = box.mask
        foreign = segmentation.ink[y0:y1, x0:x1] & ~own

        rgb = strip[y0:y1, x0:x1]
        alpha = _alpha(rgb, background[y0:y1, x0:x1], ink_color, own, foreign, mode, cap)
        rgba = np.dstack([rgb, np.round(alpha * 255).astype(np.uint8)])

        crops.append(
            GlyphCrop(
                char=box.char,
                rgba=np.ascontiguousarray(rgba, dtype=np.uint8),
                box=(x0, y0, x1, y1),
                metrics=_metrics(
                    box,
                    own,
                    foreign,
                    gray[y0:y1, x0:x1],
                    bg_gray[y0:y1, x0:x1],
                    ink_color,
                    mode,
                    cap,
                    noise,
                    clipped=box.x0 == 0 or box.y0 == 0 or box.x1 == width or box.y1 == height,
                ),
                confidence=box.confidence,
                baseline_y=round(float(segmentation.baseline) - y0, 2),
            )
        )
    return crops


def _alpha(
    rgb: NDArray[np.uint8],
    background: NDArray[np.float32],
    ink_color: NDArray[np.floating],
    own: NDArray[np.bool_],
    foreign: NDArray[np.bool_],
    mode: BlendMode,
    cap: float,
) -> NDArray[np.float32]:
    """Soft 0..1 coverage of this character only (neighbours' ink removed)."""
    reach = _ellipse(max(3, round(0.06 * cap)) | 1)
    allowed = cv2.dilate(own.astype(np.uint8), reach).astype(bool) & ~foreign
    if mode == "relief":
        filled = cv2.morphologyEx(
            own.astype(np.uint8), cv2.MORPH_CLOSE, _ellipse(max(3, round(0.12 * cap)) | 1)
        ).astype(np.float32)
        soft = cv2.GaussianBlur(filled, (0, 0), 1.0)
        return np.asarray(np.clip(soft, 0, 1) * allowed, dtype=np.float32)

    direction = background - ink_color.astype(np.float32)  # per pixel: background → ink
    denominator = np.maximum((direction * direction).sum(axis=2), 1.0)
    projection = ((background - rgb.astype(np.float32)) * direction).sum(axis=2) / denominator
    return np.asarray(np.clip(projection, 0, 1) * allowed, dtype=np.float32)


def _metrics(
    box: CharBox,
    own: NDArray[np.bool_],
    foreign: NDArray[np.bool_],
    gray: NDArray[np.float32],
    bg_gray: NDArray[np.float32],
    ink_color: NDArray[np.floating],
    mode: BlendMode,
    cap: float,
    noise: float,
    *,
    clipped: bool,
) -> GlyphMetrics:
    bg_luma = float(np.median(bg_gray)) / 255.0
    if mode == "relief":
        region = cv2.dilate(own.astype(np.uint8), _ellipse(3)).astype(bool)
        values = gray[region]
        contrast = float(np.percentile(values, 95) - np.percentile(values, 5)) / 255.0
        light = light_direction(gray, region)
    else:
        ink_luma = float(_luma(ink_color.reshape(1, 3))[0]) / 255.0
        contrast = abs(bg_luma - ink_luma)
        light = None

    own_area = max(int(own.sum()), 1)
    isolation = 1.0 - min(1.0, float(foreign.sum()) / own_area)
    contrast_factor = min(1.0, contrast / 0.12)
    quality = box.confidence * (0.5 + 0.5 * isolation) * contrast_factor
    if clipped:
        quality *= 0.5

    return GlyphMetrics(
        cap_height_px=round(cap, 2),
        stroke_width_px=round(_stroke_width(own), 2),
        blur_sigma=round(estimate_blur(gray, contrast * 255.0), 3),
        noise_sigma=round(noise, 3),
        ink_color=_hex(ink_color),
        bg_luma=round(bg_luma, 4),
        contrast=round(contrast, 4),
        light_dir_deg=None if light is None else round(light, 1),
        isolation=round(isolation, 4),
        clipped=clipped,
        quality=round(float(np.clip(quality, 0.0, 1.0)), 4),
    )
