"""Quad geometry: ordering, rectification and warping back (PRD FR-E03)."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

from app.engine.types import FloatImage, Homography, Quad, Rectified, RGBImage


def order_quad(points: NDArray[np.floating] | list[list[float]]) -> Quad:
    """Order 4 points as top-left, top-right, bottom-right, bottom-left.

    Sorting by angle around the centroid is robust for rotated text, where the
    classic sum/difference trick breaks near 45°.
    """
    pts = np.asarray(points, dtype=np.float32).reshape(4, 2)
    center = pts.mean(axis=0)
    angles = np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0])
    clockwise = pts[np.argsort(angles)]  # image y points down → ascending angle is clockwise
    start = int(np.argmin(clockwise.sum(axis=1)))  # top-left = smallest x + y
    return np.roll(clockwise, -start, axis=0).astype(np.float32)


def quad_size(quad: Quad) -> tuple[int, int]:
    """(width, height) of the rectified patch: the longer of each pair of opposite edges."""
    tl, tr, br, bl = quad
    width = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
    height = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
    return max(1, round(float(width))), max(1, round(float(height)))


def quad_area(quad: Quad) -> float:
    return float(abs(cv2.contourArea(quad.astype(np.float32))))


def quad_iou(a: Quad, b: Quad) -> float:
    """Intersection over union of two convex quads."""
    inter, _ = cv2.intersectConvexConvex(a.astype(np.float32), b.astype(np.float32))
    union = quad_area(a) + quad_area(b) - float(inter)
    return float(inter) / union if union > 0 else 0.0


def is_valid_quad(quad: Quad, width: int, height: int, min_area: float = 64.0) -> bool:
    """Convex, inside the image (1 px tolerance) and at least `min_area` px² (API.md §3.6)."""
    pts = quad.astype(np.float32)
    inside = bool(
        np.all(pts[:, 0] >= -1) and np.all(pts[:, 0] <= width + 1)
        and np.all(pts[:, 1] >= -1) and np.all(pts[:, 1] <= height + 1)
    )  # fmt: skip
    return (
        inside and bool(cv2.isContourConvex(pts.reshape(-1, 1, 2))) and quad_area(pts) >= min_area
    )


def rectify(image: RGBImage, quad: Quad, size: tuple[int, int] | None = None) -> Rectified:
    """Warp the quad to a frontal, axis-aligned patch (bilinear, edges replicated)."""
    width, height = size or quad_size(quad)
    target = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32
    )
    to_patch: Homography = np.asarray(
        cv2.getPerspectiveTransform(quad.astype(np.float32), target), dtype=np.float64
    )
    to_image: Homography = np.asarray(np.linalg.inv(to_patch), dtype=np.float64)
    patch = cv2.warpPerspective(
        image, to_patch, (width, height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
    )
    return Rectified(
        patch=np.ascontiguousarray(patch, dtype=np.uint8), to_patch=to_patch, to_image=to_image
    )


def warp_to_image(
    patch: NDArray[np.uint8] | NDArray[np.float32],
    to_image: Homography,
    image_size: tuple[int, int],
) -> NDArray[Any]:
    """Project a rectified patch (or mask) back into image space (zeros outside)."""
    width, height = image_size
    warped = cv2.warpPerspective(
        patch, to_image, (width, height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT
    )
    return np.asarray(warped, dtype=patch.dtype)


def transform_points(points: NDArray[np.floating], homography: Homography) -> NDArray[np.float32]:
    pts = np.asarray(points, dtype=np.float32).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(pts, homography).reshape(-1, 2).astype(np.float32)


def polygon_mask(quad: Quad, image_size: tuple[int, int]) -> FloatImage:
    """Anti-aliased 0..1 mask of a quad in image space."""
    width, height = image_size
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillConvexPoly(mask, np.round(quad * 16).astype(np.int32), 255, cv2.LINE_AA, shift=4)
    return (mask.astype(np.float32) / 255.0).astype(np.float32)
