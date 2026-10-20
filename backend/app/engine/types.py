"""Engine data types. Pixel arrays are RGB uint8 (H x W x 3) unless stated otherwise.

Coordinates are image pixels as float32 (x, y). A quad is 4 points ordered
top-left, top-right, bottom-right, bottom-left (see geometry.order_quad).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from numpy.typing import NDArray

RGBImage = NDArray[np.uint8]
GrayImage = NDArray[np.uint8]
FloatImage = NDArray[np.float32]
Quad = NDArray[np.float32]  # shape (4, 2)
Homography = NDArray[np.float64]  # shape (3, 3)

ImageFormat = Literal["JPEG", "PNG", "TIFF"]


@dataclass(frozen=True, eq=False)
class DecodedImage:
    """A decoded upload plus everything needed to encode a result the same way."""

    rgb: RGBImage
    alpha: GrayImage | None
    format: ImageFormat
    mode: str  # original Pillow mode (L, LA, P, RGB, RGBA)
    icc_profile: bytes | None = None
    dpi: tuple[float, float] | None = None
    jpeg_qtables: dict[int, list[int]] | None = None
    jpeg_subsampling: int | None = None
    jpeg_quality_est: int | None = None
    tiff_compression: str | None = None
    exif_orientation_applied: bool = False

    @property
    def width(self) -> int:
        return int(self.rgb.shape[1])

    @property
    def height(self) -> int:
        return int(self.rgb.shape[0])


@dataclass(frozen=True, eq=False)
class Region:
    """One detected line of text.

    `char_positions` are the centres of the recognised characters as fractions (0 to 1)
    along the rectified text line, from the recogniser's CTC time steps.
    """

    quad: Quad
    text: str
    confidence: float
    char_positions: tuple[float, ...] = field(default_factory=tuple)
    char_confidences: tuple[float, ...] = field(default_factory=tuple)
    vertical: bool = False


@dataclass(frozen=True, eq=False)
class Rectified:
    """A quad warped to an axis-aligned patch, with transforms both ways."""

    patch: RGBImage
    to_patch: Homography  # image → patch
    to_image: Homography  # patch → image
