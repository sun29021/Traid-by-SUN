"""Text removal: fill the old token so the surface looks untouched (PRD FR-E06).

Hybrid, chosen by measurement on fixtures with ground truth (Phase 7):

    method          structure error   texture ratio (1.0 = real)   time
    Telea alone          1.24               0.39 (smooth smudge)     ~5 ms
    LaMa (CPU)           1.00               0.78                     ~8.3 s
    Telea + grain        1.06               0.89                     ~5 ms

So the default is a Telea fill plus grain matched to the surrounding surface. LaMa
(learned inpainting) is used when the background around the text has real structure
— lines or edges crossing the token — where a diffusion fill visibly fails. Every
result gets a grain top-up so the patch is neither smoother nor noisier than its
surroundings. Pixels outside the (feathered) mask are never modified.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np
from numpy.typing import NDArray

from app.engine.models import ModelRegistry, ModelUnavailableError
from app.engine.types import GrayImage, RGBImage

LAMA_MODEL = "lama-inpaint"
LAMA_SIZE = 512
# Long edges entering the mask from the ring; a crossing line gives two (top and bottom).
STRUCTURE_THRESHOLD = 1.5

Method = Literal["telea", "lama"]
Preference = Literal["auto", "telea", "lama"]


@dataclass(frozen=True, eq=False)
class RemovalResult:
    image: RGBImage  # full image, text removed
    mask: GrayImage  # 0/255 removal mask actually filled (image coordinates)
    method: Method
    fallback_used: bool  # LaMa was wanted but unavailable
    structure: float  # long edges entering the mask (see structure_score)
    grain_added: float  # std dev (grey levels) of the grain top-up


def _ellipse(size: int) -> NDArray[np.uint8]:
    size = max(1, size)
    return np.asarray(cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size)), np.uint8)


def _bbox(mask: NDArray[np.uint8]) -> tuple[int, int, int, int] | None:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def structure_score(gray: NDArray[np.uint8], mask: NDArray[np.uint8], ring_px: int) -> float:
    """Number of long edges that run into the masked text from outside.

    A printed rule, a label border or a pattern crossing the token shows up as edge
    segments that touch the mask and are long relative to the ring; surface grain only
    makes short specks. (Edge *density* was tried first and misses thin lines: measured
    0.01 on fixtures with a rule line, the same as plain paper.)
    """
    grown = cv2.dilate(mask, _ellipse(2 * ring_px + 1))
    ring = (grown > 0) & (mask == 0)
    if ring.sum() < 20:
        return 0.0
    edges = (cv2.Canny(cv2.GaussianBlur(gray, (0, 0), 1.0), 40, 100) > 0) & ring
    touching = cv2.dilate(mask, _ellipse(5)) > 0
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        edges.astype(np.uint8), connectivity=8
    )
    long_edges = 0
    for label in range(1, count):
        length = max(int(stats[label, cv2.CC_STAT_WIDTH]), int(stats[label, cv2.CC_STAT_HEIGHT]))
        if length >= 0.6 * ring_px and bool((touching & (labels == label)).any()):
            long_edges += 1
    return float(long_edges)


def _highpass_sigma(image: NDArray[np.float32], region: NDArray[np.bool_]) -> NDArray[np.float32]:
    """Per-channel std dev of fine grain inside `region`."""
    residual = image - cv2.GaussianBlur(image, (0, 0), 1.5)
    if region.sum() < 20:
        return np.zeros(3, np.float32)
    return np.asarray([residual[..., c][region].std() for c in range(3)], dtype=np.float32)


def _lama(registry: ModelRegistry, crop: RGBImage, mask: NDArray[np.uint8]) -> RGBImage:
    """LaMa at its fixed 512x512 input, resized back to the crop."""
    height, width = crop.shape[:2]
    interpolation = cv2.INTER_AREA if max(height, width) > LAMA_SIZE else cv2.INTER_CUBIC
    image = cv2.resize(crop, (LAMA_SIZE, LAMA_SIZE), interpolation=interpolation)
    small_mask = cv2.resize(mask, (LAMA_SIZE, LAMA_SIZE), interpolation=cv2.INTER_NEAREST)
    feeds = {
        "image": np.ascontiguousarray(image.transpose(2, 0, 1)[None], dtype=np.float32) / 255.0,
        "mask": (small_mask > 0).astype(np.float32)[None, None],
    }
    output = registry.session(LAMA_MODEL).run(feeds)[0][0]
    filled = np.clip(output.transpose(1, 2, 0), 0, 255).astype(np.uint8)
    return np.asarray(cv2.resize(filled, (width, height), interpolation=cv2.INTER_CUBIC), np.uint8)


def remove_text(
    image: RGBImage,
    ink_mask: NDArray[np.uint8] | NDArray[np.bool_],
    *,
    registry: ModelRegistry | None = None,
    prefer: Preference = "auto",
    dilate_px: int = 3,
    seed: int = 0,
) -> RemovalResult:
    """Remove the ink in `ink_mask` (image coordinates, nonzero = ink)."""
    height, width = image.shape[:2]
    ink = (np.asarray(ink_mask, dtype=np.uint8) > 0).astype(np.uint8)
    mask = np.asarray(cv2.dilate(ink, _ellipse(2 * dilate_px + 1)), np.uint8)
    box = _bbox(mask)
    if box is None:
        return RemovalResult(image.copy(), mask * 255, "telea", False, 0.0, 0.0)

    # Work on a crop around the text with generous context.
    x0, y0, x1, y1 = box
    margin = max(32, y1 - y0)
    cx0, cy0 = max(x0 - margin, 0), max(y0 - margin, 0)
    cx1, cy1 = min(x1 + margin, width), min(y1 + margin, height)
    crop = np.ascontiguousarray(image[cy0:cy1, cx0:cx1])
    crop_mask = np.ascontiguousarray(mask[cy0:cy1, cx0:cx1])
    gray = np.asarray(cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY), np.uint8)

    structure = structure_score(gray, crop_mask, ring_px=max(6, (y1 - y0) // 3))
    wants_lama = prefer == "lama" or (prefer == "auto" and structure > STRUCTURE_THRESHOLD)
    method: Method = "telea"
    fallback = False
    filled: RGBImage
    if wants_lama and registry is not None:
        try:
            filled = _lama(registry, crop, crop_mask)
            method = "lama"
        except ModelUnavailableError:
            fallback = True
            filled = np.asarray(cv2.inpaint(crop, crop_mask * 255, 3, cv2.INPAINT_TELEA), np.uint8)
    else:
        fallback = wants_lama  # wanted LaMa but no registry was given
        filled = np.asarray(cv2.inpaint(crop, crop_mask * 255, 3, cv2.INPAINT_TELEA), np.uint8)

    # Grain top-up: add only the variance the fill is missing, per channel.
    inside = crop_mask > 0
    ring = (cv2.dilate(crop_mask, _ellipse(25)) > 0) & ~inside
    target = _highpass_sigma(crop.astype(np.float32), ring)
    current = _highpass_sigma(filled.astype(np.float32), inside)
    add = np.sqrt(np.maximum(target**2 - current**2, 0.0))
    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, 1.0, crop.shape).astype(np.float32)
    noise = np.asarray(cv2.GaussianBlur(noise, (0, 0), 0.6), np.float32)  # grain is correlated
    noise /= max(float(noise.std()), 1e-6)
    grained = filled.astype(np.float32) + noise * add[None, None, :]

    # Feathered blend; outside the feather the original pixels are kept exactly.
    alpha = cv2.GaussianBlur(crop_mask.astype(np.float32), (0, 0), 1.0)
    alpha = np.where(cv2.dilate(crop_mask, _ellipse(5)) > 0, np.maximum(alpha, inside), 0.0)
    blended = crop.astype(np.float32) * (1 - alpha[..., None]) + grained * alpha[..., None]
    result = image.copy()
    region = np.clip(np.round(blended), 0, 255).astype(np.uint8)
    keep = alpha <= 0
    region[keep] = crop[keep]
    result[cy0:cy1, cx0:cx1] = region

    full_mask = np.zeros((height, width), np.uint8)
    full_mask[cy0:cy1, cx0:cx1] = crop_mask * 255
    return RemovalResult(
        image=result,
        mask=full_mask,
        method=method,
        fallback_used=fallback,
        structure=round(structure, 4),
        grain_added=round(float(math.sqrt(float((add**2).mean()))), 3),
    )
