"""Put the harmonized glyph layer into the photo (PRD FR-E10).

result = background x exp(-D) inside the glyph support, where background is the photo
after text removal. The density layer is the only thing warped from strip space into
the image; pixels outside the removal mask and the glyph support are copied from the
original unchanged (hard mask enforcement), so exports are bit-identical there.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from app.engine.harmonize import DensityLayer
from app.engine.types import GrayImage, Homography, RGBImage

FloatArray = NDArray[np.float32]


@dataclass(frozen=True, eq=False)
class Composite:
    image: RGBImage
    changed: GrayImage  # 0/255: every pixel that may differ from the original
    roi: tuple[int, int, int, int]  # (x0, y0, x1, y1) of the glyph layer in the image
    support: FloatArray  # glyph support inside `roi` (0..1)
    density: FloatArray  # per-channel density inside `roi`


def _translation(x: float, y: float) -> NDArray[np.float64]:
    return np.array([[1, 0, x], [0, 1, y], [0, 0, 1]], dtype=np.float64)


def warp_layer(
    layer: DensityLayer, strip_to_image: Homography, image_size: tuple[int, int]
) -> tuple[FloatArray, FloatArray, tuple[int, int, int, int]]:
    """Layer → image space, computed only over the layer's bounding box.

    Returns (density ROI, support ROI, (x0, y0, x1, y1) of the ROI in the image).
    """
    width, height = image_size
    canvas_to_image = strip_to_image @ _translation(*layer.origin)
    h, w = layer.support.shape
    corners = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32).reshape(-1, 1, 2)
    projected = cv2.perspectiveTransform(corners, canvas_to_image).reshape(-1, 2)
    x0 = max(math.floor(float(projected[:, 0].min())) - 2, 0)
    y0 = max(math.floor(float(projected[:, 1].min())) - 2, 0)
    x1 = min(math.ceil(float(projected[:, 0].max())) + 2, width)
    y1 = min(math.ceil(float(projected[:, 1].max())) + 2, height)
    if x1 <= x0 or y1 <= y0:
        empty = np.zeros((0, 0), np.float32)
        return np.zeros((0, 0, 3), np.float32), empty, (0, 0, 0, 0)
    to_roi = _translation(-x0, -y0) @ canvas_to_image
    size = (x1 - x0, y1 - y0)
    density = cv2.warpPerspective(
        layer.density, to_roi, size, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT
    )
    support = cv2.warpPerspective(
        layer.support, to_roi, size, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT
    )
    return np.asarray(density, np.float32), np.asarray(support, np.float32), (x0, y0, x1, y1)


def composite(
    original: RGBImage,
    background: RGBImage,
    removal_mask: GrayImage,
    layer: DensityLayer | None,
    strip_to_image: Homography,
    *,
    grain_sigma: float,
    seed: int,
) -> Composite:
    """Apply the layer to the cleaned background; `grain_sigma` tops up ink grain."""
    height, width = original.shape[:2]
    result = background.copy()
    changed = (removal_mask > 0).astype(np.uint8)
    # Removal feathers up to 3 px beyond its mask; include that band.
    changed = np.asarray(cv2.dilate(changed, np.ones((7, 7), np.uint8)), np.uint8)
    roi = (0, 0, 0, 0)
    support_roi = np.zeros((0, 0), np.float32)
    density_roi = np.zeros((0, 0, 3), np.float32)

    if layer is not None:
        density, support, (x0, y0, x1, y1) = warp_layer(layer, strip_to_image, (width, height))
        if support.size:
            base = background[y0:y1, x0:x1].astype(np.float32)
            rendered = base * np.exp(-density)
            if grain_sigma > 0:
                rng = np.random.default_rng(seed)
                noise = rng.normal(0.0, 1.0, base.shape).astype(np.float32)
                noise = np.asarray(cv2.GaussianBlur(noise, (0, 0), 0.6), np.float32)
                noise /= max(float(noise.std()), 1e-6)
                rendered += noise * grain_sigma * support[..., None]
            touched = (support > 1 / 512) | (np.abs(density).max(axis=2) > 1e-4)
            region = np.clip(np.round(rendered), 0, 255).astype(np.uint8)
            current = result[y0:y1, x0:x1]
            current[touched] = region[touched]
            changed[y0:y1, x0:x1] |= touched.astype(np.uint8)
            roi, support_roi, density_roi = (x0, y0, x1, y1), support, density

    # Hard enforcement: nothing outside the changed mask may differ from the original.
    keep = changed == 0
    result[keep] = original[keep]
    return Composite(
        image=result, changed=changed * 255, roi=roi, support=support_roi, density=density_roi
    )
