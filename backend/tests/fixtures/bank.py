"""A glyph bank learned from synthetic reference images (for engine tests and eval)."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from app.engine.detect import FakeDetector
from app.engine.extract import extract_from_image
from app.engine.geometry import quad_iou
from app.engine.glyph_select import GlyphSample
from app.engine.segment import BlendMode
from app.engine.types import Region
from tests.fixtures.generate import Surface, make_token_image

REFERENCE_TEXTS = ("0123456789", "ABCDEFGHIJ", "KLMNOPQRST", "UVWXYZ-/#7", "ZX-WY/QK#V")
CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-/# "


def blend_mode(surface: Surface) -> BlendMode:
    return "relief" if surface in ("laser_mark", "engraved") else "ink"


def build_bank(
    surface: Surface,
    seeds: Sequence[int] = (101, 102),
    texts: Sequence[str] = REFERENCE_TEXTS,
    *,
    reviewed: bool = True,
) -> list[GlyphSample]:
    """Extract every character of `texts` on `surface` for each seed, as bank glyphs.

    `reviewed` keeps only glyphs whose crop really holds that character (what the
    owner's review does in the app): a mis-segmented crop would otherwise teach the
    bank a wrong letter.
    """
    bank: list[GlyphSample] = []
    for seed in seeds:
        for offset, text in enumerate(texts):
            fixture = make_token_image(text, surface, seed=seed * 10 + offset)
            detector = FakeDetector([Region(quad=fixture.quad, text=text, confidence=0.99)])
            result = extract_from_image(
                fixture.image, detector, charset=CHARSET, mode=blend_mode(surface)
            )
            for index, glyph in enumerate(result.glyphs):
                if reviewed and not _holds(glyph.source_quad, glyph.char, fixture.char_quads):
                    continue
                bank.append(
                    GlyphSample(
                        char=glyph.char,
                        rgba=glyph.rgba,
                        metrics=glyph.metrics,
                        angle_deg=glyph.angle_deg,
                        baseline_y=glyph.baseline_y,
                        source="bank",
                        glyph_id=f"{surface}-{seed}-{offset}-{index}",
                    )
                )
    return bank


def _holds(crop: np.ndarray, char: str, truth: Sequence[tuple[str, np.ndarray]]) -> bool:
    """The crop overlaps the true box of a `char` more than any other character."""
    best = max(truth, key=lambda pair: quad_iou(crop, pair[1]))
    return best[0] == char and quad_iou(crop, best[1]) > 0.2
