import cv2
import numpy as np
import pytest

from app.engine.detect import DetectorConfig, FakeDetector, PaddleOcr
from app.engine.geometry import quad_iou
from app.engine.models import ModelRegistry
from app.engine.types import Region
from tests.fixtures.generate import SURFACES, Surface, make_token_image

# ---------------------------------------------------------------- no models needed


def test_ctc_decode_collapses_repeats_and_blanks() -> None:
    charset = ["", "A", "7", "-"]
    # time steps: A A _ 7 _ 7 - -   (blank = 0)
    steps = [1, 1, 0, 2, 0, 2, 3, 3]
    probs = np.full((len(steps), len(charset)), 0.01, dtype=np.float32)
    for t, index in enumerate(steps):
        probs[t, index] = 0.97

    text, confidences, positions = PaddleOcr._ctc_decode(probs, charset)

    assert text == "A77-"
    assert len(confidences) == 4 and all(c == pytest.approx(0.97) for c in confidences)
    assert positions == pytest.approx([1 / 8, 3.5 / 8, 5.5 / 8, 7 / 8])


def test_boxes_from_probability_map() -> None:
    prob = np.zeros((200, 400), dtype=np.float32)
    cv2.rectangle(prob, (100, 80), (300, 110), 0.9, thickness=-1)  # one text line
    cv2.rectangle(prob, (10, 10), (11, 11), 0.9, thickness=-1)  # speck → ignored
    ocr = PaddleOcr(ModelRegistry.from_manifest(__import__("pathlib").Path("unused")))

    quads = ocr._boxes_from_probability(prob)

    assert len(quads) == 1
    xs, ys = quads[0][:, 0], quads[0][:, 1]
    # DB unclip grows the 201x31 core by 2*d on each axis, d = area * 1.6 / perimeter.
    d = 201 * 31 * 1.6 / (2 * (201 + 31))
    assert xs.max() - xs.min() == pytest.approx(200 + 2 * d, abs=2)
    assert ys.max() - ys.min() == pytest.approx(30 + 2 * d, abs=2)


def test_fake_detector_returns_its_regions() -> None:
    region = Region(quad=np.zeros((4, 2), np.float32), text="X", confidence=1.0)

    assert FakeDetector([region]).detect(np.zeros((4, 4, 3), np.uint8)) == [region]


def test_detection_resizes_into_the_working_range() -> None:
    ocr = PaddleOcr(ModelRegistry.from_manifest(__import__("pathlib").Path("unused")))

    big, (sy, sx) = ocr._resize_for_detection(np.zeros((3000, 4000, 3), np.uint8))
    small, _ = ocr._resize_for_detection(np.zeros((300, 400, 3), np.uint8))

    assert max(big.shape[:2]) == 1920 and big.shape[0] % 32 == 0 and big.shape[1] % 32 == 0
    assert sy == pytest.approx(1440 / 3000) and sx == pytest.approx(1920 / 4000)
    assert max(small.shape[:2]) == DetectorConfig().min_side


# ---------------------------------------------------------------- real models (skip if absent)


@pytest.mark.models
@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("seed", [1, 8, 15])
def test_reads_tokens_on_every_surface(ocr: PaddleOcr, surface: Surface, seed: int) -> None:
    fixture = make_token_image("A7-204913", surface, seed=seed, jpeg_quality=88)

    regions = ocr.detect(fixture.image)

    best = max(regions, key=lambda r: quad_iou(r.quad, fixture.quad))
    assert best.text == fixture.text
    assert best.confidence > 0.9
    assert quad_iou(best.quad, fixture.quad) > 0.75
    assert len(best.char_positions) == len(fixture.text)
    assert list(best.char_positions) == sorted(best.char_positions)


@pytest.mark.models
def test_reads_mixed_case_and_finds_separate_lines(ocr: PaddleOcr) -> None:
    top = make_token_image("Lot 42b", "print", seed=21, canvas=(960, 320), rotation_deg=0)
    bottom = make_token_image("XZ-0071", "print", seed=22, canvas=(960, 320), rotation_deg=0)
    image = np.vstack([top.image, bottom.image])

    texts = [r.text for r in ocr.detect(image)]

    # Reading order is top to bottom. PP-OCR rarely emits spaces; they are recovered from
    # ink gaps during character segmentation (IMPLEMENTATION_PLAN.md task 5.3).
    assert [t.replace(" ", "") for t in texts] == ["Lot42b", "XZ-0071"]


@pytest.mark.models
def test_blank_image_has_no_text(ocr: PaddleOcr) -> None:
    assert ocr.detect(np.full((480, 640, 3), 200, np.uint8)) == []
