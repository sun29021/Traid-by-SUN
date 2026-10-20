import numpy as np
import pytest

from tests.fixtures.generate import SURFACES, Surface, make_token_image


def test_fixtures_are_deterministic() -> None:
    a = make_token_image(seed=11, jpeg_quality=90)
    b = make_token_image(seed=11, jpeg_quality=90)

    assert np.array_equal(a.image, b.image)
    assert np.array_equal(a.quad, b.quad)


@pytest.mark.parametrize("surface", SURFACES)
def test_text_quad_lies_inside_the_canvas(surface: Surface) -> None:
    fixture = make_token_image(surface=surface, seed=2)
    h, w = fixture.image.shape[:2]

    assert fixture.image.dtype == np.uint8 and fixture.image.shape == (640, 960, 3)
    assert np.all(fixture.quad >= 0)
    assert np.all(fixture.quad[:, 0] < w) and np.all(fixture.quad[:, 1] < h)


@pytest.mark.parametrize("surface", SURFACES)
def test_text_is_visible_inside_its_quad(surface: Surface) -> None:
    fixture = make_token_image(surface=surface, seed=4)
    x0, y0 = fixture.quad.min(axis=0).astype(int)
    x1, y1 = fixture.quad.max(axis=0).astype(int)
    inside = fixture.image[y0:y1, x0:x1].astype(np.float32)

    # Text strokes create real contrast inside the box.
    assert float(inside.std()) > 8.0
