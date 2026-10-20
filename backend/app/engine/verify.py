"""Automatic quality report for a result (PRD FR-E12, US-25).

Checks, each pass / warn / fail with its number (DESIGN: numbers are shown):

* ocr_readback: the same OCR reads the result region; must equal the new token.
* seam: gradient energy just inside the changed area's edge relative to the ring just
  outside it (0 = the edge is as smooth as the surroundings).
* noise: grain of the cleaned background inside the changed area / grain around it.
* sharpness: blur of the new glyphs minus blur of the original glyphs (px sigma).
* colour: colour difference (CIE76 delta E) between new and original ink (ink mode),
  or relative contrast change (relief mode).
* outside_unchanged: every pixel outside the changed mask equals the original.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

import cv2
import numpy as np
from numpy.typing import NDArray

from app.engine.composite import Composite
from app.engine.detect import TextDetector
from app.engine.geometry import clip_quad, expand_quad, quad_iou
from app.engine.segment import BlendMode
from app.engine.types import Quad, RGBImage

Status = Literal["pass", "warn", "fail"]
_ORDER: dict[Status, int] = {"pass": 0, "warn": 1, "fail": 2}

SEAM_WARN = 0.35
NOISE_RANGE = (0.7, 1.4)
SHARPNESS_WARN = 0.6  # px sigma
COLOUR_WARN = 10.0  # delta E
RELIEF_CONTRAST_WARN = 0.35  # relative


@dataclass(frozen=True)
class Check:
    id: str
    status: Status
    value: float | str | None
    threshold: float | None = None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {"id": self.id, "status": self.status, "value": self.value}
        if self.threshold is not None:
            data["threshold"] = self.threshold
        return data


@dataclass(frozen=True)
class QualityReport:
    overall: Status
    checks: tuple[Check, ...]

    def to_dict(self) -> dict[str, object]:
        return {"overall": self.overall, "checks": [c.to_dict() for c in self.checks]}

    def check(self, check_id: str) -> Check | None:
        return next((c for c in self.checks if c.id == check_id), None)


@dataclass(frozen=True)
class OriginalLook:
    """Statistics of the original token to compare the result against."""

    blur_sigma: float
    ink_rgb: tuple[float, float, float]
    contrast: float
    mode: BlendMode


def _gray(image: NDArray[np.uint8]) -> NDArray[np.float32]:
    return np.asarray(cv2.cvtColor(image, cv2.COLOR_RGB2GRAY), np.float32)


def _normalise(text: str) -> str:
    return text.replace(" ", "")


def ocr_readback(detector: TextDetector, image: RGBImage, quad: Quad, new_text: str) -> Check:
    height, width = image.shape[:2]
    area = clip_quad(expand_quad(quad, 0.8), width, height)
    x0, y0 = (int(v) for v in np.floor(area.min(axis=0)))
    x1, y1 = (int(v) + 1 for v in np.ceil(area.max(axis=0)))
    crop = np.ascontiguousarray(image[y0:y1, x0:x1])
    local = (quad - np.array([x0, y0], np.float32)).astype(np.float32)
    regions = detector.detect(crop)
    if not regions:
        return Check("ocr_readback", "fail", "")
    best = max(regions, key=lambda r: quad_iou(r.quad, local))
    read = best.text
    if _normalise(read) == _normalise(new_text):
        return Check("ocr_readback", "pass", read)
    similarity = SequenceMatcher(None, _normalise(read), _normalise(new_text)).ratio()
    return Check("ocr_readback", "warn" if similarity >= 0.5 else "fail", read)


def _bands(changed: NDArray[np.bool_], width: int) -> tuple[NDArray[np.bool_], NDArray[np.bool_]]:
    kernel = np.ones((2 * width + 1, 2 * width + 1), np.uint8)
    inner = changed & ~cv2.erode(changed.astype(np.uint8), kernel).astype(bool)
    outer = cv2.dilate(changed.astype(np.uint8), kernel).astype(bool) & ~changed
    return inner, outer


def seam_check(result: RGBImage, comp: Composite) -> Check:
    changed = comp.changed > 0
    if not changed.any():
        return Check("seam", "pass", 0.0, SEAM_WARN)
    inner, outer = _bands(changed, 2)
    # Ignore the new glyphs' own edges: they are meant to be sharp.
    x0, y0, x1, y1 = comp.roi
    if comp.support.size:
        glyph = np.zeros(changed.shape, bool)
        glyph[y0:y1, x0:x1] = comp.support > 0.05
        inner &= ~glyph
    gray = cv2.GaussianBlur(_gray(result), (0, 0), 0.7)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = np.hypot(gx, gy)
    if inner.sum() < 10 or outer.sum() < 10:
        return Check("seam", "pass", 0.0, SEAM_WARN)
    ratio = float(magnitude[inner].mean()) / max(float(magnitude[outer].mean()), 1e-3)
    value = round(max(ratio - 1.0, 0.0), 3)
    return Check("seam", "pass" if value <= SEAM_WARN else "warn", value, SEAM_WARN)


def _grain(gray: NDArray[np.float32], region: NDArray[np.bool_]) -> float:
    residual = gray - cv2.GaussianBlur(gray, (0, 0), 1.5)
    values = residual[region]
    if values.size < 30:
        return 0.0
    return float(1.4826 * np.median(np.abs(values - np.median(values))))


def noise_check(result: RGBImage, comp: Composite) -> Check:
    changed = comp.changed > 0
    plain = changed.copy()
    x0, y0, x1, y1 = comp.roi
    if comp.support.size:
        plain[y0:y1, x0:x1] &= comp.support < 0.02
    plain = cv2.erode(plain.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    _, outer = _bands(changed, 6)
    gray = _gray(result)
    inside, around = _grain(gray, plain), _grain(gray, outer)
    if inside == 0.0 or around == 0.0:
        return Check("noise", "pass", 1.0)
    ratio = round(inside / around, 3)
    low, high = NOISE_RANGE
    return Check("noise", "pass" if low <= ratio <= high else "warn", ratio)


_SQRT_2PI = math.sqrt(2 * math.pi)
_INTRINSIC_BLUR = 2.0 / _SQRT_2PI


def measure_blur(gray: NDArray[np.float32], region: NDArray[np.bool_]) -> float:
    """Edge blur sigma (px) of the text inside `region`, from its steepest edges.

    The same measurement is applied to the original token and to the result, so the
    sharpness check compares like with like.
    """
    values = gray[region]
    if values.size < 30:
        return 0.0
    contrast = float(np.percentile(values, 97) - np.percentile(values, 3))
    if contrast < 8:
        return 0.0
    smooth = cv2.GaussianBlur(gray, (0, 0), 0.5)
    gx = cv2.Sobel(smooth, cv2.CV_32F, 1, 0, ksize=3) / 8.0
    gy = cv2.Sobel(smooth, cv2.CV_32F, 0, 1, ksize=3) / 8.0
    steepest = float(np.percentile(np.hypot(gx, gy)[region], 99))
    if steepest <= 1e-3:
        return 0.0
    measured = contrast / (_SQRT_2PI * steepest)
    return float(math.sqrt(max(measured**2 - _INTRINSIC_BLUR**2 - 0.25, 0.0)))


def text_region(support: NDArray[np.bool_]) -> NDArray[np.bool_]:
    return np.asarray(cv2.dilate(support.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0)


def sharpness_check(result: RGBImage, comp: Composite, original: OriginalLook) -> Check:
    if not comp.support.size or not (comp.support > 0.5).any():
        return Check("sharpness", "pass", 0.0, SHARPNESS_WARN)
    x0, y0, x1, y1 = comp.roi
    blur = measure_blur(_gray(result[y0:y1, x0:x1]), text_region(comp.support > 0.05))
    delta = round(blur - original.blur_sigma, 3)
    status: Status = "pass" if abs(delta) <= SHARPNESS_WARN else "warn"
    return Check("sharpness", status, delta, SHARPNESS_WARN)


def _lab(rgb: Sequence[float]) -> NDArray[np.float32]:
    pixel = np.asarray(rgb, np.float32).reshape(1, 1, 3) / 255.0
    return np.asarray(cv2.cvtColor(pixel, cv2.COLOR_RGB2LAB), np.float32).reshape(3)


def colour_check(result: RGBImage, comp: Composite, original: OriginalLook) -> Check:
    if not comp.support.size:
        return Check("colour", "pass", 0.0)
    x0, y0, x1, y1 = comp.roi
    strength = np.abs(comp.density).mean(axis=2)
    region = (comp.support > 0.5) & (strength > 0)
    if region.sum() < 10:
        return Check("colour", "pass", 0.0)
    pixels = result[y0:y1, x0:x1][region].astype(np.float32)
    if original.mode == "relief":
        values = _gray(result[y0:y1, x0:x1])[comp.support > 0.5]
        contrast = float(np.percentile(values, 95) - np.percentile(values, 5)) / 255.0
        change = round(abs(contrast - original.contrast) / max(original.contrast, 1e-3), 3)
        return Check(
            "colour",
            "pass" if change <= RELIEF_CONTRAST_WARN else "warn",
            change,
            RELIEF_CONTRAST_WARN,
        )
    strongest = strength[region] >= np.percentile(strength[region], 70)
    ink = np.median(pixels[strongest], axis=0)
    delta = round(float(np.linalg.norm(_lab(ink) - _lab(original.ink_rgb))), 2)
    return Check("colour", "pass" if delta <= COLOUR_WARN else "warn", delta, COLOUR_WARN)


def outside_check(original_image: RGBImage, result: RGBImage, comp: Composite) -> Check:
    keep = comp.changed == 0
    same = bool(np.array_equal(original_image[keep], result[keep]))
    return Check("outside_unchanged", "pass" if same else "fail", same)


def build_report(checks: Sequence[Check]) -> QualityReport:
    overall: Status = max((c.status for c in checks), key=lambda s: _ORDER[s], default="pass")
    return QualityReport(overall=overall, checks=tuple(checks))


def verify(
    original_image: RGBImage,
    comp: Composite,
    quad: Quad,
    new_text: str,
    original: OriginalLook,
    detector: TextDetector | None,
) -> QualityReport:
    result = comp.image
    checks: list[Check] = []
    if detector is not None:
        checks.append(ocr_readback(detector, result, quad, new_text))
    checks.append(seam_check(result, comp))
    checks.append(noise_check(result, comp))
    checks.append(sharpness_check(result, comp, original))
    checks.append(colour_check(result, comp, original))
    checks.append(outside_check(original_image, result, comp))
    return build_report(checks)
