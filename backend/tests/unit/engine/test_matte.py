import numpy as np
import pytest

from app.engine.geometry import clip_quad, expand_quad, rectify
from app.engine.matte import GlyphCrop, estimate_blur, estimate_noise, extract_glyphs
from app.engine.segment import BlendMode, segment
from tests.fixtures.generate import Surface, make_token_image


def _glyphs(surface: Surface, mode: BlendMode, seed: int = 3, **kwargs: object) -> list[GlyphCrop]:
    fixture = make_token_image("A7-204913", surface, seed=seed, **kwargs)  # type: ignore[arg-type]
    h, w = fixture.image.shape[:2]
    strip = rectify(fixture.image, clip_quad(expand_quad(fixture.quad, 0.25), w, h)).patch
    return extract_glyphs(strip, segment(strip, "A7-204913", [], mode=mode), mode)


@pytest.mark.parametrize("surface", ["print", "paint", "laser_mark"])
def test_ink_glyphs_have_opaque_strokes_and_clear_background(surface: Surface) -> None:
    for glyph in _glyphs(surface, "ink"):
        alpha = glyph.rgba[..., 3]
        assert glyph.rgba.dtype == np.uint8 and glyph.rgba.shape[2] == 4
        assert alpha.max() >= 200  # stroke centres are solid
        border = np.concatenate([alpha[0], alpha[-1], alpha[:, 0], alpha[:, -1]])
        assert float(border.mean()) < 20  # padding stays transparent
        assert 0 < glyph.metrics.quality <= 1


def test_ink_color_and_contrast_on_paper() -> None:
    metrics = _glyphs("print", "ink")[0].metrics
    r, g, b = (int(metrics.ink_color[i : i + 2], 16) for i in (1, 3, 5))

    assert max(r, g, b) < 90  # dark ink
    assert metrics.bg_luma > 0.75  # light paper
    assert metrics.contrast > 0.4
    assert metrics.light_dir_deg is None


def test_blur_estimate_increases_with_blur() -> None:
    def median_blur(sigma: float) -> float:
        glyphs = _glyphs("print", "ink", blur_sigma=sigma, noise_sigma=1.5)
        return float(np.median([g.metrics.blur_sigma for g in glyphs]))

    sharp, soft, softer = median_blur(0.4), median_blur(1.2), median_blur(2.0)

    assert sharp < soft < softer


def test_noise_estimate_tracks_sensor_noise() -> None:
    low = np.median([g.metrics.noise_sigma for g in _glyphs("print", "ink", noise_sigma=1.0)])
    high = np.median([g.metrics.noise_sigma for g in _glyphs("print", "ink", noise_sigma=6.0)])

    assert high > 2 * low


def test_engraved_light_direction_matches_the_fixture() -> None:
    fixture = make_token_image("A7-204913", "engraved", seed=4)
    assert fixture.light_deg is not None
    angles = [g.metrics.light_dir_deg for g in _glyphs("engraved", "relief", seed=4)]
    measured = [a for a in angles if a is not None]

    assert len(measured) >= 6
    mean = np.degrees(np.angle(np.mean(np.exp(1j * np.radians(measured))))) % 360
    error = (mean - fixture.light_deg + 180) % 360 - 180
    assert abs(error) < 45


def test_relief_glyphs_include_their_rim() -> None:
    glyph = _glyphs("engraved", "relief")[1]  # "7"

    assert glyph.metrics.contrast > 0.1
    assert (glyph.rgba[..., 3] > 128).sum() > 50


def test_blur_and_noise_estimators_on_synthetic_edges() -> None:
    import cv2

    edge = np.zeros((64, 64), np.float32)
    edge[:, 32:] = 200
    assert estimate_blur(edge, 200) < 0.3
    assert estimate_blur(cv2.GaussianBlur(edge, (0, 0), 2.0), 200) == pytest.approx(2.0, abs=0.4)

    rng = np.random.default_rng(0)
    flat = (120 + rng.normal(0, 4, (64, 64))).astype(np.float32)
    assert estimate_noise(flat, np.ones((64, 64), bool)) == pytest.approx(4 * 0.86, rel=0.25)
