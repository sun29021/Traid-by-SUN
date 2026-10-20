import io

import pytest
from PIL import Image

from app.core.errors import AppError, ErrorCode
from app.db.models.enums import MimeType
from app.storage.images import validate_image
from tests.factories import image_bytes

LIMITS = {"max_bytes": 5 * 1024 * 1024, "max_pixels": 10_000}


@pytest.mark.parametrize(
    ("fmt", "mime"),
    [("PNG", MimeType.PNG), ("JPEG", MimeType.JPEG), ("TIFF", MimeType.TIFF)],
)
def test_accepts_supported_formats(fmt: str, mime: MimeType) -> None:
    info = validate_image(image_bytes(fmt), **LIMITS)

    assert info.mime_type is mime
    assert (info.width, info.height) == (32, 16)


def test_reads_dpi_and_icc_profile() -> None:
    srgb = Image.new("RGB", (1, 1)).info.get("icc_profile") or b"\x00" * 128
    data = image_bytes("PNG", dpi=(300, 300), icc_profile=srgb)

    info = validate_image(data, **LIMITS)

    assert info.dpi_x == pytest.approx(300, abs=0.5)
    assert info.has_icc is True


def _code(data: bytes, **limits: int) -> tuple[int, ErrorCode]:
    with pytest.raises(AppError) as caught:
        validate_image(data, **{**LIMITS, **limits})
    return caught.value.http_status, caught.value.code


def test_rejects_files_over_the_byte_limit() -> None:
    assert _code(image_bytes("PNG"), max_bytes=10) == (413, ErrorCode.UPLOAD_TOO_LARGE)


def test_rejects_unknown_content_regardless_of_name() -> None:
    assert _code(b"GIF89a" + b"\x00" * 40) == (415, ErrorCode.UNSUPPORTED_MEDIA_TYPE)
    assert _code(b"%PDF-1.7 not an image") == (415, ErrorCode.UNSUPPORTED_MEDIA_TYPE)


def test_rejects_truncated_images() -> None:
    data = image_bytes("JPEG", size=(64, 64))
    assert _code(data[: len(data) // 2]) == (422, ErrorCode.IMAGE_DECODE_FAILED)


def test_rejects_images_over_the_pixel_limit() -> None:
    assert _code(image_bytes("PNG", size=(200, 100))) == (422, ErrorCode.IMAGE_TOO_LARGE)


def test_rejects_16_bit_images() -> None:
    assert _code(image_bytes("PNG", mode="I;16")) == (415, ErrorCode.UNSUPPORTED_MEDIA_TYPE)


def test_rejects_multi_page_tiff() -> None:
    buffer = io.BytesIO()
    pages = [Image.new("RGB", (8, 8)), Image.new("RGB", (8, 8))]
    pages[0].save(buffer, format="TIFF", save_all=True, append_images=pages[1:])

    assert _code(buffer.getvalue()) == (415, ErrorCode.UNSUPPORTED_MEDIA_TYPE)


def test_rejects_empty_file() -> None:
    assert _code(b"") == (422, ErrorCode.IMAGE_DECODE_FAILED)
