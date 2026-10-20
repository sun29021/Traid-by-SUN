"""Character segmentation on synthetic fixtures with exact per-character ground truth.

Strips are cut from the true text box (padded as in extraction), so these tests
measure segmentation alone, independent of OCR.
"""

import numpy as np
import pytest

from app.engine.geometry import clip_quad, expand_quad, order_quad, quad_iou, rectify
from app.engine.geometry import transform_points as tp
from app.engine.segment import BlendMode, segment
from tests.fixtures.generate import Surface, TokenFixture, make_token_image

TEXTS = ["A7-204913", "Lot 42b", "WM-1111", "MILL 11", "ij-gpq"]


def _strip_and_truth(fixture: TokenFixture) -> tuple[np.ndarray, list[np.ndarray]]:
    h, w = fixture.image.shape[:2]
    rect = rectify(fixture.image, clip_quad(expand_quad(fixture.quad, 0.25), w, h))
    return rect.patch, [order_quad(tp(q, rect.to_patch)) for _, q in fixture.char_quads]


def _box_quad(box: object) -> np.ndarray:
    x0, y0, x1, y1 = box.x0, box.y0, box.x1, box.y1  # type: ignore[attr-defined]
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float32)


def _ious(surface: Surface, mode: BlendMode, text: str, seed: int) -> list[float]:
    fixture = make_token_image(text, surface, seed=seed, jpeg_quality=88)
    strip, truth = _strip_and_truth(fixture)
    result = segment(strip, text.replace(" ", ""), [], mode=mode)
    assert result.missing == ()
    assert [c.char for c in result.chars] == list(text.replace(" ", ""))
    return [quad_iou(t, _box_quad(c)) for t, c in zip(truth, result.chars, strict=True)]


@pytest.mark.parametrize("surface", ["print", "paint", "laser_mark"])
@pytest.mark.parametrize("text", TEXTS)
def test_ink_surfaces_segment_every_character(surface: Surface, text: str) -> None:
    ious = _ious(surface, "ink", text, seed=9)

    assert min(ious) > 0.4  # thin glyphs ("1", "-") have small boxes
    assert float(np.median(ious)) > 0.8


@pytest.mark.parametrize("text", TEXTS)
def test_engraved_segments_with_rims(text: str) -> None:
    # Relief glyphs include their highlight/shadow rim, so boxes are larger than the ink.
    ious = _ious("engraved", "relief", text, seed=9)

    assert float(np.median(ious)) > 0.6


def _draw_h(strip: np.ndarray, x: int) -> None:
    """A stroke-built 'H' 30 px wide, 40 px tall, strokes 6 px."""
    strip[10:50, x : x + 6] = 30
    strip[10:50, x + 24 : x + 30] = 30
    strip[28:34, x : x + 30] = 30


def test_touching_characters_are_split_between_them() -> None:
    strip = np.full((60, 200, 3), 230, dtype=np.uint8)
    _draw_h(strip, 40)  # stems at 40-46 and 64-70
    _draw_h(strip, 72)  # stems at 72-78 and 96-102
    strip[40:43, 70:72] = 30  # ink bridge: one connected blob

    result = segment(strip, "HH", [], mode="ink")

    assert [c.char for c in result.chars] == ["H", "H"]
    assert 69 <= result.chars[0].x1 <= 73 and 69 <= result.chars[1].x0 <= 73
    assert result.missing == ()


def test_dots_join_their_letter_and_specks_are_dropped() -> None:
    strip = np.full((80, 160, 3), 230, dtype=np.uint8)
    strip[30:65, 40:48] = 30  # stem of an i
    strip[18:25, 40:48] = 30  # its dot (overlaps in x)
    strip[30:65, 90:120] = 30  # a second letter
    strip[5, 150] = 30  # a single-pixel speck

    result = segment(strip, "iL", [], mode="ink")

    assert [c.char for c in result.chars] == ["i", "L"]
    assert result.chars[0].y0 <= 18  # dot included


def test_light_text_on_dark_background() -> None:
    strip = np.full((60, 120, 3), 40, dtype=np.uint8)
    strip[12:48, 30:42] = 220
    strip[12:48, 70:82] = 220

    result = segment(strip, "11", [], mode="ink")

    assert result.polarity == "light"
    assert len(result.chars) == 2


def test_missing_ink_is_reported_not_invented() -> None:
    strip = np.full((60, 120, 3), 230, dtype=np.uint8)
    strip[12:48, 30:42] = 30  # only one character visible

    result = segment(strip, "AB", [], mode="ink")

    assert [c.char for c in result.chars] == ["A"]
    assert result.missing == (1,)


def test_line_metrics() -> None:
    fixture = make_token_image("HELLO 42", "print", seed=1, rotation_deg=0, perspective=0)
    strip, truth = _strip_and_truth(fixture)

    result = segment(strip, "HELLO42", [], mode="ink")

    true_cap = float(np.median([t[:, 1].max() - t[:, 1].min() for t in truth]))
    true_base = float(np.median([t[:, 1].max() for t in truth]))
    assert result.cap_height == pytest.approx(true_cap, abs=3)
    assert result.baseline == pytest.approx(true_base, abs=3)
    assert result.pitch > 0
