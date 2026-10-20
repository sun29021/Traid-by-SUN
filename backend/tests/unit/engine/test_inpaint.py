from pathlib import Path

import cv2
import numpy as np
import pytest
from numpy.typing import NDArray

from app.core.config import REPO_ROOT
from app.engine.detect import PaddleOcr
from app.engine.inpaint import LAMA_MODEL, STRUCTURE_THRESHOLD, remove_text, structure_score
from app.engine.models import ModelRegistry
from tests.fixtures.generate import SURFACES, Surface, make_token_image

TEXT = "A7-204913"


def _scene(
    surface: Surface, seed: int, *, rule: bool = False
) -> tuple[NDArray[np.uint8], NDArray[np.uint8], NDArray[np.uint8]]:
    """(image with text, the same scene without ink, exact ink mask)."""
    fixture = make_token_image(TEXT, surface, seed=seed, rule=rule)
    blank = make_token_image(TEXT, surface, seed=seed, rule=rule, blank=True).image
    ink = (np.abs(fixture.image.astype(int) - blank.astype(int)).max(axis=2) > 6).astype(np.uint8)
    return fixture.image, blank, ink


def _lowpass(image: NDArray[np.uint8]) -> NDArray[np.float32]:
    return np.asarray(cv2.GaussianBlur(image.astype(np.float32), (0, 0), 2.0))


Image = NDArray[np.uint8]


def _structure_error(out: Image, truth: Image, mask: Image) -> float:
    return float(np.abs(_lowpass(out) - _lowpass(truth))[mask > 0].mean())


def _texture_ratio(out: Image, truth: Image, mask: Image) -> float:
    inside = mask > 0
    fine_out = out.astype(np.float32) - _lowpass(out)
    fine_truth = truth.astype(np.float32) - _lowpass(truth)
    return float(fine_out[inside].std() / max(float(fine_truth[inside].std()), 1e-3))


@pytest.fixture(scope="module")
def lama_registry() -> ModelRegistry:
    registry = ModelRegistry.from_manifest(REPO_ROOT / "models", device="cpu")
    if LAMA_MODEL not in registry.specs or not registry.checksum_ok(LAMA_MODEL):
        pytest.skip("LaMa model not installed (run scripts/fetch_models.py)")
    return registry


# ---------------------------------------------------------------- no models needed


@pytest.mark.parametrize("surface", SURFACES)
def test_plain_surface_is_filled_with_matching_grain(surface: Surface) -> None:
    image, blank, ink = _scene(surface, seed=8)

    result = remove_text(image, ink, seed=1)

    assert result.method == "telea" and not result.fallback_used
    assert _structure_error(result.image, blank, result.mask) < 2.5
    assert 0.7 < _texture_ratio(result.image, blank, result.mask) < 1.3
    assert result.grain_added > 0


def test_pixels_outside_the_feather_are_untouched() -> None:
    image, _, ink = _scene("print", seed=9)

    result = remove_text(image, ink, seed=1)

    feather = cv2.dilate(result.mask, np.ones((7, 7), np.uint8)) > 0
    assert np.array_equal(result.image[~feather], image[~feather])
    assert not np.array_equal(result.image[feather], image[feather])


def test_no_residual_text_remains() -> None:
    image, blank, ink = _scene("paint", seed=8)

    result = remove_text(image, ink, seed=1)

    # The worst inside pixel stays close to the true background (ink was ~100 levels off).
    diff = np.abs(_lowpass(result.image) - _lowpass(blank)).max(axis=2)
    assert float(np.percentile(diff[result.mask > 0], 99)) < 12


def test_empty_mask_returns_a_copy() -> None:
    image = np.full((40, 60, 3), 128, np.uint8)

    result = remove_text(image, np.zeros((40, 60), np.uint8))

    assert np.array_equal(result.image, image) and result.image is not image
    assert result.mask.max() == 0


def test_result_is_deterministic_for_a_seed() -> None:
    image, _, ink = _scene("laser_mark", seed=8)

    first = remove_text(image, ink, seed=3).image
    again = remove_text(image, ink, seed=3).image

    assert np.array_equal(first, again)


def test_structure_score_counts_lines_crossing_the_text() -> None:
    plain_image, _, plain_ink = _scene("print", seed=8)
    ruled_image, _, ruled_ink = _scene("print", seed=8, rule=True)

    def score(image: NDArray[np.uint8], ink: NDArray[np.uint8]) -> float:
        mask = cv2.dilate(ink, np.ones((7, 7), np.uint8))
        ys = np.nonzero(mask)[0]
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        return structure_score(gray, mask, ring_px=max(6, int(ys.max() - ys.min()) // 3))

    assert score(plain_image, plain_ink) < STRUCTURE_THRESHOLD
    assert score(ruled_image, ruled_ink) > STRUCTURE_THRESHOLD


def test_structured_background_without_lama_falls_back_to_telea() -> None:
    image, _, ink = _scene("print", seed=8, rule=True)

    result = remove_text(image, ink, registry=None, seed=1)

    assert result.method == "telea"
    assert result.fallback_used
    assert result.structure > STRUCTURE_THRESHOLD


def test_missing_lama_file_falls_back(tmp_path: Path) -> None:
    registry = ModelRegistry.from_manifest(REPO_ROOT / "models", device="cpu")
    registry.model_dir = tmp_path  # every model is now "missing"
    image, _, ink = _scene("print", seed=8)

    result = remove_text(image, ink, registry=registry, prefer="lama", seed=1)

    assert result.method == "telea" and result.fallback_used


# ---------------------------------------------------------------- real LaMa (skip if absent)


@pytest.mark.models
def test_lama_restores_a_line_crossing_the_text(lama_registry: ModelRegistry) -> None:
    image, blank, ink = _scene("engraved", seed=8, rule=True)

    result = remove_text(image, ink, registry=lama_registry, seed=1)
    telea = remove_text(image, ink, prefer="telea", seed=1)

    assert result.method == "lama" and not result.fallback_used
    lama_error = _structure_error(result.image, blank, result.mask)
    assert lama_error < 2.0
    assert lama_error < 0.5 * _structure_error(telea.image, blank, telea.mask)
    assert 0.7 < _texture_ratio(result.image, blank, result.mask) < 1.3


@pytest.mark.models
@pytest.mark.parametrize("surface", SURFACES)
def test_ocr_finds_no_text_after_removal(ocr: PaddleOcr, surface: Surface) -> None:
    image, _, ink = _scene(surface, seed=15)
    assert any(r.text == TEXT for r in ocr.detect(image))

    result = remove_text(image, ink, seed=1)

    assert ocr.detect(result.image) == []
