import io

import numpy as np
import pytest
from PIL import Image

from app.engine.io import decode_image, encode_image
from app.engine.metadata import (
    ARTIST,
    COPYRIGHT,
    FORBIDDEN_TAGS,
    IMAGE_DESCRIPTION,
    SOFTWARE,
    XP_AUTHOR,
    XP_KEYWORDS,
    XP_TITLE,
    ImageDetails,
)
from tests.factories import image_bytes

DETAILS = ImageDetails(
    title="Receipt — mock-up",
    description="Edited from receipt.jpg (2026-10-12)",
    author="Xavier Sun",
    copyright="© 2026 Xavier Sun",
    keywords=("traid", "receipt"),
    comment="Showcase sample",
)


def _encode(fmt: str, details: ImageDetails | None, marker: str | None = "Traid 0.1.0") -> bytes:
    source = decode_image(image_bytes(fmt, size=(48, 32)))
    rgb = np.full((32, 48, 3), 120, np.uint8)
    return encode_image(rgb, source, marker=marker, details=details)


def _xp(raw: object) -> str:
    data = bytes(raw) if not isinstance(raw, bytes) else raw  # type: ignore[call-overload]
    return data.decode("utf-16-le").rstrip("\0")


def test_jpeg_carries_exif_and_windows_fields() -> None:
    with Image.open(io.BytesIO(_encode("JPEG", DETAILS))) as image:
        exif = image.getexif()
        comment = image.info.get("comment")
        xmp = image.info["xmp"].decode("utf-8")

    assert exif[IMAGE_DESCRIPTION] == DETAILS.description
    assert exif[ARTIST] == "Xavier Sun"
    assert exif[COPYRIGHT] == "(c) 2026 Xavier Sun"  # EXIF text is ASCII
    assert exif[SOFTWARE] == "Traid 0.1.0"
    assert _xp(exif[XP_TITLE]) == DETAILS.title
    assert _xp(exif[XP_AUTHOR]) == "Xavier Sun"
    assert _xp(exif[XP_KEYWORDS]) == "traid;receipt"
    assert comment == b"Traid 0.1.0"
    assert "© 2026 Xavier Sun" in xmp and "<rdf:li>receipt</rdf:li>" in xmp
    assert "Receipt — mock-up" in xmp


def test_png_carries_text_chunks() -> None:
    with Image.open(io.BytesIO(_encode("PNG", DETAILS))) as image:
        text = dict(image.text)  # type: ignore[attr-defined]

    assert text["Title"] == DETAILS.title
    assert text["Author"] == "Xavier Sun"
    assert text["Copyright"] == "© 2026 Xavier Sun"
    assert text["Keywords"] == "traid; receipt"
    assert text["Comment"] == "Showcase sample"
    assert text["Software"] == "Traid 0.1.0"


def test_tiff_carries_baseline_tags() -> None:
    with Image.open(io.BytesIO(_encode("TIFF", DETAILS))) as image:
        tags = dict(image.tag_v2)  # type: ignore[attr-defined]

    assert tags[IMAGE_DESCRIPTION] == DETAILS.description
    assert tags[ARTIST] == "Xavier Sun"
    assert tags[COPYRIGHT] == "(c) 2026 Xavier Sun"
    assert tags[SOFTWARE] == "Traid 0.1.0"
    assert "© 2026 Xavier Sun" in bytes(tags[700]).decode("utf-8")


@pytest.mark.parametrize("fmt", ["JPEG", "TIFF"])
def test_no_capture_metadata_is_ever_written(fmt: str) -> None:
    with Image.open(io.BytesIO(_encode(fmt, DETAILS))) as image:
        written = set(image.getexif()) if fmt == "JPEG" else set(image.tag_v2)  # type: ignore[attr-defined]

    assert not written & FORBIDDEN_TAGS


def test_title_alone_becomes_the_description() -> None:
    with Image.open(io.BytesIO(_encode("JPEG", ImageDetails(title="Only a title")))) as image:
        assert image.getexif()[IMAGE_DESCRIPTION] == "Only a title"


def test_nothing_is_added_without_details_or_marker() -> None:
    with Image.open(io.BytesIO(_encode("JPEG", None, marker=None))) as image:
        assert len(image.getexif()) == 0
        assert "comment" not in image.info
