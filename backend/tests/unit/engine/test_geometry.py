import cv2
import numpy as np
import pytest

from app.engine.geometry import (
    is_valid_quad,
    order_quad,
    polygon_mask,
    quad_iou,
    quad_size,
    rectify,
    transform_points,
    warp_to_image,
)
from tests.fixtures.generate import make_token_image

SQUARE = np.array([[10, 10], [110, 10], [110, 60], [10, 60]], dtype=np.float32)


@pytest.mark.parametrize("shift", [0, 1, 2, 3])
def test_order_quad_from_any_start(shift: int) -> None:
    shuffled = np.roll(SQUARE, shift, axis=0)[::-1]

    assert np.array_equal(order_quad(shuffled), SQUARE)


def test_order_quad_handles_strong_rotation() -> None:
    center = SQUARE.mean(axis=0)
    angle = np.deg2rad(40)
    rot = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    rotated = ((SQUARE - center) @ rot.T + center).astype(np.float32)

    ordered = order_quad(rotated[[2, 0, 3, 1]])

    # Clockwise in image coordinates: signed area (shoelace) is positive.
    x, y = ordered[:, 0], ordered[:, 1]
    assert 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) > 0
    assert np.allclose(ordered[0], rotated[np.argmin(rotated.sum(axis=1))])


def test_quad_size_and_iou() -> None:
    assert quad_size(SQUARE) == (100, 50)
    assert quad_iou(SQUARE, SQUARE) == pytest.approx(1.0)
    shifted = SQUARE + np.array([50, 0], dtype=np.float32)
    assert quad_iou(SQUARE, shifted) == pytest.approx(1 / 3, abs=1e-3)


def test_rectify_maps_corners_within_a_pixel() -> None:
    fixture = make_token_image(seed=5, perspective=0.1)
    quad = order_quad(fixture.quad)

    rect = rectify(fixture.image, quad)
    width, height = quad_size(quad)
    corners = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]])

    back = transform_points(corners.astype(np.float32), rect.to_image)
    assert np.abs(back - quad).max() < 1.0
    assert rect.patch.shape == (height, width, 3)


def test_rectified_patch_warps_back_onto_the_original() -> None:
    fixture = make_token_image(seed=6, perspective=0.08, blur_sigma=0, noise_sigma=0)
    quad = order_quad(fixture.quad)
    h, w = fixture.image.shape[:2]
    rect = rectify(fixture.image, quad)

    restored = warp_to_image(rect.patch, rect.to_image, (w, h))
    inner = cv2.erode((polygon_mask(quad, (w, h)) > 0.99).astype(np.uint8), np.ones((5, 5)))

    diff = np.abs(restored.astype(np.int16) - fixture.image.astype(np.int16))[inner > 0]
    assert float(diff.mean()) < 6.0


def test_quad_validation() -> None:
    assert is_valid_quad(SQUARE, 200, 100)
    assert not is_valid_quad(SQUARE + np.array([150, 0], dtype=np.float32), 200, 100)  # outside
    assert not is_valid_quad(SQUARE[[0, 2, 1, 3]], 200, 100)  # self-intersecting
    tiny = np.array([[0, 0], [4, 0], [4, 4], [0, 4]], dtype=np.float32)
    assert not is_valid_quad(tiny, 200, 100)  # area 16 < 64
