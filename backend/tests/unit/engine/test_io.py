import io

import numpy as np
import pytest
from PIL import Image, ImageCms

from app.engine.io import decode_image, encode_image, estimate_jpeg_quality
from tests.fixtures.generate import make_token_image

SRGB_ICC = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def _save(image: Image.Image, fmt: str, **options: object) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **options)
    return buffer.getvalue()


def _photo() -> Image.Image:
    return Image.fromarray(make_token_image(seed=3).image)


@pytest.mark.parametrize("quality", [50, 65, 75, 85, 92, 98])
def test_jpeg_quality_estimate(quality: int) -> None:
    decoded = decode_image(_save(_photo(), "JPEG", quality=quality))

    assert decoded.jpeg_quality_est is not None
    assert abs(decoded.jpeg_quality_est - quality) <= 2


def test_estimate_without_tables_is_none() -> None:
    assert estimate_jpeg_quality(None) is None


@pytest.mark.parametrize("fmt", ["PNG", "TIFF", "JPEG"])
def test_round_trip_keeps_size_dpi_and_icc(fmt: str) -> None:
    data = _save(_photo(), fmt, dpi=(300, 300), icc_profile=SRGB_ICC)

    decoded = decode_image(data)
    again = Image.open(io.BytesIO(encode_image(decoded.rgb, decoded)))

    assert again.format == fmt
    assert again.size == (decoded.width, decoded.height)
    assert again.info.get("icc_profile") == SRGB_ICC
    assert tuple(round(v) for v in again.info["dpi"]) == (300, 300)


def test_png_round_trip_is_lossless() -> None:
    decoded = decode_image(_save(_photo(), "PNG"))

    again = decode_image(encode_image(decoded.rgb, decoded))

    assert np.array_equal(again.rgb, decoded.rgb)


def test_jpeg_reuses_source_tables_and_subsampling() -> None:
    source = _save(_photo(), "JPEG", quality=77, subsampling=2)
    decoded = decode_image(source)

    reencoded = Image.open(io.BytesIO(encode_image(decoded.rgb, decoded)))

    assert {k: list(v) for k, v in reencoded.quantization.items()} == decoded.jpeg_qtables  # type: ignore[attr-defined]
    assert decoded.jpeg_subsampling == 2


def test_exif_orientation_is_applied_and_not_copied() -> None:
    image = Image.new("RGB", (40, 20), (200, 10, 10))
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90° CW on display
    data = _save(image, "JPEG", exif=exif.tobytes(), quality=95)

    decoded = decode_image(data)
    output = Image.open(io.BytesIO(encode_image(decoded.rgb, decoded)))

    assert (decoded.width, decoded.height) == (20, 40)
    assert decoded.exif_orientation_applied is True
    assert output.getexif().get(0x0112) is None


def test_grayscale_stays_grayscale_and_alpha_is_kept() -> None:
    gray = decode_image(_save(Image.new("L", (16, 8), 90), "PNG"))
    assert Image.open(io.BytesIO(encode_image(gray.rgb, gray))).mode == "L"

    rgba = Image.new("RGBA", (16, 8), (10, 20, 30, 128))
    decoded = decode_image(_save(rgba, "PNG"))
    assert decoded.alpha is not None and int(decoded.alpha[0, 0]) == 128
    output = Image.open(io.BytesIO(encode_image(decoded.rgb, decoded)))
    assert output.mode == "RGBA" and output.getpixel((0, 0)) == (10, 20, 30, 128)


def test_format_override_and_fixed_quality() -> None:
    decoded = decode_image(_save(_photo(), "PNG"))

    jpeg = decode_image(encode_image(decoded.rgb, decoded, fmt="JPEG", jpeg_quality=80))

    assert jpeg.format == "JPEG"
    assert jpeg.jpeg_quality_est is not None and abs(jpeg.jpeg_quality_est - 80) <= 2


def test_jpeg_with_gain_map_decodes_as_the_photo_and_exports_as_jpeg() -> None:
    from tests.unit.storage.test_images import _ultra_hdr_like

    decoded = decode_image(_ultra_hdr_like())
    encoded = encode_image(decoded.rgb, decoded)

    assert decoded.format == "JPEG" and decoded.rgb.shape == (48, 64, 3)
    assert decoded.jpeg_qtables
    with Image.open(io.BytesIO(encoded)) as image:
        assert image.format == "JPEG" and image.size == (64, 48)
