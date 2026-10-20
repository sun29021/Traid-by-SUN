"""Upload validation for images (API.md §5).

Checks run cheapest-first: size → magic bytes → header (format, mode, pixel count)
→ full decode. File names are never trusted; the content decides the type.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

from app.core.errors import (
    ErrorCode,
    PayloadTooLarge,
    UnsupportedMediaType,
    ValidationFailed,
)
from app.db.models.enums import MimeType

_MAGIC: tuple[tuple[bytes, MimeType], ...] = (
    (b"\xff\xd8\xff", MimeType.JPEG),
    (b"\x89PNG\r\n\x1a\n", MimeType.PNG),
    (b"II*\x00", MimeType.TIFF),
    (b"MM\x00*", MimeType.TIFF),
)
_PIL_FORMAT = {MimeType.JPEG: "JPEG", MimeType.PNG: "PNG", MimeType.TIFF: "TIFF"}
# 8-bit per channel only: grayscale (+alpha), palette, RGB, RGBA.
_ALLOWED_MODES = frozenset({"L", "LA", "P", "RGB", "RGBA"})


@dataclass(frozen=True)
class ImageInfo:
    mime_type: MimeType
    width: int
    height: int
    dpi_x: float | None
    dpi_y: float | None
    has_icc: bool


def sniff_image_type(data: bytes) -> MimeType | None:
    for magic, mime in _MAGIC:
        if data.startswith(magic):
            return mime
    return None


def validate_image(data: bytes, *, max_bytes: int, max_pixels: int) -> ImageInfo:
    if len(data) > max_bytes:
        raise PayloadTooLarge(f"File is larger than {max_bytes // (1024 * 1024)} MB")
    if not data:
        raise ValidationFailed("File is empty", code=ErrorCode.IMAGE_DECODE_FAILED)

    mime = sniff_image_type(data)
    if mime is None:
        raise UnsupportedMediaType("Only JPEG, PNG and TIFF images are supported")

    try:
        with Image.open(io.BytesIO(data)) as image:
            # Phones (e.g. Pixel "Ultra HDR") save JPEGs with an embedded gain map, which
            # Pillow reads as MPO. The first image is the photo itself; it is all we use.
            multi_picture = mime is MimeType.JPEG and image.format == "MPO"
            if image.format != _PIL_FORMAT[mime] and not multi_picture:
                raise UnsupportedMediaType("File content does not match a supported image type")
            if image.mode not in _ALLOWED_MODES:
                raise UnsupportedMediaType(
                    "Only 8-bit RGB, RGBA, grayscale or palette images are supported"
                )
            if getattr(image, "n_frames", 1) > 1 and not multi_picture:
                raise UnsupportedMediaType("Multi-page or animated images are not supported")
            width, height = image.size
            if width * height > max_pixels:
                raise ValidationFailed(
                    f"Image has {width * height:,} pixels; the limit is {max_pixels:,}",
                    code=ErrorCode.IMAGE_TOO_LARGE,
                    details={"width": width, "height": height, "max_pixels": max_pixels},
                )
            image.load()  # full decode: catches truncated or corrupt files
            dpi = image.info.get("dpi")
            has_icc = bool(image.info.get("icc_profile"))
    except Image.DecompressionBombError as exc:
        raise ValidationFailed(
            "Image is too large to open safely", code=ErrorCode.IMAGE_TOO_LARGE
        ) from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise ValidationFailed(
            "Image could not be decoded; the file may be damaged",
            code=ErrorCode.IMAGE_DECODE_FAILED,
        ) from exc

    dpi_x, dpi_y = _parse_dpi(dpi)
    return ImageInfo(mime, width, height, dpi_x, dpi_y, has_icc)


def _parse_dpi(dpi: object) -> tuple[float | None, float | None]:
    if isinstance(dpi, tuple) and len(dpi) == 2:
        try:
            x, y = float(dpi[0]), float(dpi[1])
        except (TypeError, ValueError):
            return None, None
        if x > 0 and y > 0:
            return x, y
    return None, None
