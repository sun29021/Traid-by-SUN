"""Choose a real glyph for every character of the new token (PRD FR-E07).

Priority: (1) the same character in this image's own token (it already has exactly the
right font, size, blur, lighting and noise), (2) the profile bank, ranked by how close
each glyph's capture conditions are to the target, times its learned acceptance score,
(3) nothing: the render is blocked with GLYPH_MISSING. There is no font fallback; Traid
never draws text it has not seen.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from app.engine.matte import GlyphMetrics
from app.engine.segment import BlendMode

GlyphSource = Literal["same_image", "bank"]

# Tolerances: a difference of one tolerance costs as much as any other. Chosen so a
# glyph from a similar photo (cap height within 25 %, blur within 0.6 px …) still ranks
# well, while one from a very different capture drops out.
_TOLERANCE = {
    "scale": 0.25,  # |log(cap ratio)|
    "stroke": 0.035,  # stroke width / cap height
    "blur": 0.6,  # px, after scaling to the target size
    "bg_luma": 0.15,
    "contrast": 0.12,
    "angle": 12.0,  # degrees
    "light": 45.0,  # degrees (relief only, double weight: PRD FR-E15)
}
# Same-character alternatives within this share of the best score count as equivalent,
# so repeated characters can use different real samples.
_VARIETY_SHARE = 0.85


@dataclass(frozen=True, eq=False)
class GlyphSample:
    """A real character image the synthesizer may place."""

    char: str
    rgba: NDArray[np.uint8]  # H x W x 4, original pixels + soft alpha
    metrics: GlyphMetrics
    angle_deg: float
    baseline_y: float | None  # crop-relative baseline (px); None when unknown
    source: GlyphSource
    glyph_id: str | None = None  # bank glyphs only
    accept_count: int = 0
    reject_count: int = 0


@dataclass(frozen=True)
class TargetConditions:
    """How the characters of the token being replaced were captured."""

    cap_height_px: float
    stroke_width_px: float
    blur_sigma: float
    bg_luma: float
    contrast: float
    angle_deg: float
    light_dir_deg: float | None
    mode: BlendMode


@dataclass(frozen=True, eq=False)
class Choice:
    position: int  # index into the new text (spaces included)
    char: str
    sample: GlyphSample
    score: float


@dataclass
class GlyphMissingError(Exception):
    missing: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return "No usable glyph for: " + " ".join(self.missing)


# Characters that are legitimately much lower than the cap height.
SMALL_CHARS = frozenset("-_.,:;'\"`~=+*·•")
# Template agreement: a same-image crop must look more like its own character in the
# reviewed bank than like any other character, by at least this correlation margin.
_TEMPLATE_MARGIN = 0.03
_TEMPLATE_SIZE = 32


def shape_descriptor(rgba: NDArray[np.uint8]) -> NDArray[np.float32] | None:
    """Alpha inside the ink box, resized to 32x32, zero mean and unit length."""
    import cv2

    alpha = rgba[..., 3]
    ys, xs = np.nonzero(alpha >= 64)
    if len(xs) < 4:
        return None
    crop = alpha[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1].astype(np.float32)
    small = cv2.resize(crop, (_TEMPLATE_SIZE, _TEMPLATE_SIZE), interpolation=cv2.INTER_AREA)
    vector = small.ravel() - float(small.mean())
    norm = float(np.linalg.norm(vector))
    return None if norm < 1e-3 else np.asarray(vector / norm, np.float32)


def agrees_with_bank(sample: GlyphSample, bank: Sequence[GlyphSample]) -> bool:
    """False when the bank is sure this crop is a different character.

    Only decides when the bank has both this character and others; otherwise trusts
    the crop.
    """
    own = shape_descriptor(sample.rgba)
    if own is None:
        return False
    best_same, best_other = -1.0, -1.0
    for glyph in bank:
        other = shape_descriptor(glyph.rgba)
        if other is None:
            continue
        value = float(own @ other)
        if glyph.char == sample.char:
            best_same = max(best_same, value)
        else:
            best_other = max(best_other, value)
    if best_same < -0.5 or best_other < -0.5:
        return True
    return best_same + _TEMPLATE_MARGIN >= best_other


def learned_factor(accept_count: int, reject_count: int) -> float:
    """ARCHITECTURE §5.3: (1 + accepts) / (1 + accepts + 2 x rejects)."""
    return (1 + accept_count) / (1 + accept_count + 2 * reject_count)


def _angle_diff(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def condition_similarity(sample: GlyphSample, target: TargetConditions) -> float:
    """exp(-d²/2) over tolerance-normalised differences; 1.0 = identical capture."""
    m = sample.metrics
    scale = target.cap_height_px / max(m.cap_height_px, 1.0)
    terms = {
        "scale": abs(math.log(max(scale, 1e-3))),
        "stroke": abs(
            m.stroke_width_px / max(m.cap_height_px, 1.0)
            - target.stroke_width_px / max(target.cap_height_px, 1.0)
        ),
        "blur": abs(m.blur_sigma * scale - target.blur_sigma),
        "bg_luma": abs(m.bg_luma - target.bg_luma),
        "contrast": abs(m.contrast - target.contrast),
        "angle": abs(sample.angle_deg - target.angle_deg),
    }
    distance = sum((value / _TOLERANCE[name]) ** 2 for name, value in terms.items())
    if target.mode == "relief" and m.light_dir_deg is not None and target.light_dir_deg is not None:
        light = _angle_diff(m.light_dir_deg, target.light_dir_deg) / _TOLERANCE["light"]
        distance += 2.0 * light**2
    return math.exp(-0.5 * distance)


def score(sample: GlyphSample, target: TargetConditions) -> float:
    learned = learned_factor(sample.accept_count, sample.reject_count)
    quality = 0.5 + 0.5 * sample.metrics.quality
    return condition_similarity(sample, target) * learned * quality


def rank(
    char: str, samples: Sequence[GlyphSample], target: TargetConditions
) -> list[tuple[float, GlyphSample]]:
    """Samples of `char`, best first. Same-image samples always come before bank ones."""
    scored = [(score(s, target), s) for s in samples if s.char == char]
    return sorted(scored, key=lambda pair: (pair[1].source != "same_image", -pair[0]))


def select_glyphs(
    new_text: str,
    same_image: Sequence[GlyphSample],
    bank: Sequence[GlyphSample],
    target: TargetConditions,
    *,
    overrides: Mapping[int, str] | None = None,
    positions: Collection[int] | None = None,
) -> list[Choice]:
    """One Choice per non-space character (or per index in `positions`), in text order.

    Raises GlyphMissingError listing every character with no usable glyph, and
    ValueError for an override that names an unknown glyph or a different character.
    """
    overrides = overrides or {}
    by_id = {s.glyph_id: s for s in bank if s.glyph_id}
    pool = [*same_image, *bank]
    ranked: dict[str, list[tuple[float, GlyphSample]]] = {}
    wanted = [
        (i, c) for i, c in enumerate(new_text) if c != " " and (positions is None or i in positions)
    ]
    missing = sorted({c for _, c in wanted if not rank(c, pool, target)})
    if missing:
        raise GlyphMissingError(missing)

    uses: dict[int, int] = {}  # id(sample) → times used so far
    choices: list[Choice] = []
    for position, char in wanted:
        if position in overrides:
            sample = by_id.get(overrides[position])
            if sample is None or sample.char != char:
                raise ValueError(f"glyph override for position {position} is not a '{char}'")
            choices.append(Choice(position, char, sample, score(sample, target)))
            continue
        options = ranked.setdefault(char, rank(char, pool, target))
        best_source = options[0][1].source
        best_score = options[0][0]
        # Equivalent alternatives: same source tier, close in score.
        equivalent = [
            (s, sample)
            for s, sample in options
            if sample.source == best_source and s >= _VARIETY_SHARE * best_score
        ]
        chosen_score, chosen = min(
            equivalent, key=lambda pair: (uses.get(id(pair[1]), 0), -pair[0])
        )
        uses[id(chosen)] = uses.get(id(chosen), 0) + 1
        choices.append(Choice(position, char, chosen, chosen_score))
    return choices


def variants(
    char: str,
    same_image: Sequence[GlyphSample],
    bank: Sequence[GlyphSample],
    target: TargetConditions,
    limit: int = 6,
) -> list[tuple[float, GlyphSample]]:
    """Top alternatives for one character (API: glyph-variants)."""
    return rank(char, [*same_image, *bank], target)[:limit]
