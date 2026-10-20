"""Decode uploads and encode results so the output matches the input file.

PRD FR-E11: same format, dimensions, DPI and ICC profile. JPEG results reuse the
source's own quantisation tables and chroma subsampling, so compression texture is
identical inside and outside the edited area. EXIF orientation is applied on decode
(pixels become upright) and camera EXIF is never copied to outputs.
"""

from __future__ import annotations

import io
from typing import Any, cast

import numpy as np
from PIL import Image, ImageOps, JpegImagePlugin

from app.engine.metadata import ImageDetails, save_options
from app.engine.types import DecodedImage, GrayImage, ImageFormat, RGBImage

# IJG standard luminance quantisation table (JPEG Annex K), used for quality estimates.
_IJG_LUMA = (
    16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55,
    14, 13, 16, 24, 40, 57, 69, 56, 14, 17, 22, 29, 51, 87, 80, 62,
    18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99,
)  # fmt: skip
_IJG_LUMA_SUM = sum(_IJG_LUMA)


def estimate_jpeg_quality(qtables: dict[int, list[int]] | None) -> int | None:
    """Estimate the IJG quality (1-100) from the luminance table.

    Uses the ratio of table sums, which is independent of zig-zag vs natural order.
    """
    if not qtables or 0 not in qtables:
        return None
    scale = 100.0 * sum(qtables[0]) / _IJG_LUMA_SUM
    quality = 5000.0 / scale if scale > 100 else (200.0 - scale) / 2.0
    return int(min(100, max(1, round(quality))))


def decode_image(data: bytes) -> DecodedImage:
    """Decode JPEG/PNG/TIFF bytes (already validated by app.storage.images)."""
    with Image.open(io.BytesIO(data)) as source:
        fmt = cast(ImageFormat, source.format)
        mode = source.mode
        info = dict(source.info)
        qtables: dict[int, list[int]] | None = None
        subsampling: int | None = None
        if isinstance(source, JpegImagePlugin.JpegImageFile):
            qtables = {k: list(v) for k, v in source.quantization.items()}
            subsampling = JpegImagePlugin.get_sampling(source)
        orientation = source.getexif().get(0x0112, 1)
        upright = ImageOps.exif_transpose(source)

        alpha: GrayImage | None = None
        if upright.mode in ("RGBA", "LA") or (upright.mode == "P" and "transparency" in info):
            rgba = upright.convert("RGBA")
            alpha = np.asarray(rgba.getchannel("A"), dtype=np.uint8).copy()
            rgb_image = rgba.convert("RGB")
        else:
            rgb_image = upright.convert("RGB")
        rgb: RGBImage = np.asarray(rgb_image, dtype=np.uint8).copy()

    dpi = info.get("dpi")
    return DecodedImage(
        rgb=rgb,
        alpha=alpha,
        format=fmt,
        mode=mode,
        icc_profile=info.get("icc_profile") or None,
        dpi=(float(dpi[0]), float(dpi[1])) if isinstance(dpi, tuple) and len(dpi) == 2 else None,
        jpeg_qtables=qtables,
        jpeg_subsampling=subsampling,
        jpeg_quality_est=estimate_jpeg_quality(qtables),
        tiff_compression=info.get("compression") if fmt == "TIFF" else None,
        exif_orientation_applied=orientation != 1,
    )


def encode_image(
    rgb: RGBImage,
    like: DecodedImage,
    *,
    alpha: GrayImage | None = None,
    fmt: ImageFormat | None = None,
    jpeg_quality: int | None = None,
    marker: str | None = None,
    details: ImageDetails | None = None,
) -> bytes:
    """Encode `rgb` with the source's format, DPI, ICC profile and JPEG tables.

    `fmt` overrides the format; `jpeg_quality` forces a fixed quality instead of the
    source's tables. Alpha defaults to the source's alpha (unchanged outside edits).
    `marker` is written as the file's software/comment metadata (PRD FR-E11, D-06):
    JPEG comment, PNG `Software` text chunk, TIFF Software tag. `details` adds the
    owner's descriptive metadata (engine/metadata.py); capture data is never written.
    """
    target = fmt or like.format
    alpha = alpha if alpha is not None else like.alpha
    image = Image.fromarray(np.ascontiguousarray(rgb), "RGB")
    if like.mode in ("L", "LA"):
        image = image.convert("L")
    if alpha is not None and target != "JPEG":
        image = image.convert("LA" if image.mode == "L" else "RGBA")
        image.putalpha(Image.fromarray(np.ascontiguousarray(alpha), "L"))

    options: dict[str, Any] = {}
    if like.icc_profile:
        options["icc_profile"] = like.icc_profile
    if like.dpi:
        options["dpi"] = like.dpi

    if target == "JPEG":
        if jpeg_quality is None and like.jpeg_qtables:
            options["qtables"] = like.jpeg_qtables
            if like.jpeg_subsampling is not None and like.jpeg_subsampling >= 0:
                options["subsampling"] = like.jpeg_subsampling
        else:
            options["quality"] = jpeg_quality or like.jpeg_quality_est or 95
    elif target == "TIFF":
        options["compression"] = like.tiff_compression or "tiff_lzw"
    elif target == "PNG":
        options["optimize"] = False

    options.update(save_options(target, details, marker))

    buffer = io.BytesIO()
    image.save(buffer, format=target, **options)
    return buffer.getvalue()
