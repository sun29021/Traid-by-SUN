"""Where each new glyph goes, in rectified strip coordinates (PRD FR-E08).

Same length (and spaces in the same places): every character keeps its original slot,
and only the slots whose character changes are removed and re-rendered. The untouched
characters stay the camera's own pixels, which is the most natural result possible.

Different length: the whole token is removed and laid out again from the original
anchor (left edge, centre or right edge) with the original pitch (monospace) or the
measured letter gap (proportional), on the original baseline.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from app.engine.glyph_select import Choice
from app.engine.segment import CharBox

Alignment = Literal["auto", "left", "center", "right"]
SpacingMode = Literal["auto", "monospace", "proportional"]
LayoutMode = Literal["slots", "relayout"]

# Characters that sit away from the baseline when a glyph has no stored baseline.
_MIDLINE = frozenset("-+=~*·•:")
_DESCENDERS = frozenset("gjpqy,;")
# Width of a space relative to cap height in proportional layouts (typical sans fonts).
_SPACE_PER_CAP = 0.36
# Centre spacing varying less than this (relative) means the original is monospaced.
_MONOSPACE_CV = 0.08
# Slot reuse is abandoned when a new glyph would leave less than this share of the
# usual letter gap to a neighbour (wide letters in narrow slots would touch).
_MIN_GAP_SHARE = 0.35


@dataclass(frozen=True)
class LineGeometry:
    """The original token as segmented: one box per non-space character, in order."""

    boxes: tuple[CharBox, ...]
    labels: str  # the original text, spaces included
    cap_height: float
    baseline: float
    pitch: float
    missing: tuple[int, ...] = ()  # label indices without ink (layout cannot reuse slots)
    suspect: tuple[int, ...] = ()  # box indices whose size is implausible for their label


@dataclass(frozen=True)
class Placement:
    position: int  # index into the new text
    char: str
    x_center: float  # strip px, centre of the glyph's ink
    baseline: float  # strip px
    scale: float  # glyph px → strip px


@dataclass(frozen=True)
class LayoutPlan:
    mode: LayoutMode
    placements: tuple[Placement, ...]
    removed_slots: tuple[int, ...]  # indices into LineGeometry.boxes to remove


def ink_bounds(rgba: NDArray[np.uint8], threshold: int = 64) -> tuple[int, int, int, int]:
    """(x0, y0, x1, y1) of the glyph's ink inside its crop (exclusive ends)."""
    ys, xs = np.nonzero(rgba[..., 3] >= threshold)
    if len(xs) == 0:
        h, w = rgba.shape[:2]
        return 0, 0, w, h
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def glyph_baseline(choice: Choice) -> float:
    """Baseline inside the crop: stored when known, otherwise from the ink and the char."""
    sample = choice.sample
    if sample.baseline_y is not None:
        return sample.baseline_y
    _, y0, _, y1 = ink_bounds(sample.rgba)
    cap = sample.metrics.cap_height_px
    if choice.char in _MIDLINE:
        return (y0 + y1) / 2 + 0.45 * cap
    if choice.char in _DESCENDERS:
        return y1 - 0.22 * cap
    return float(y1)


def _is_monospace(boxes: Sequence[CharBox]) -> bool:
    if len(boxes) < 3:
        return False
    centres = np.array([(b.x0 + b.x1) / 2 for b in boxes])
    steps = np.diff(centres)
    return bool(steps.mean() > 0 and steps.std() / steps.mean() < _MONOSPACE_CV)


def _median_gap(boxes: Sequence[CharBox], cap: float) -> float:
    gaps = [b.x0 - a.x1 for a, b in pairwise(boxes)]
    return float(np.median(gaps)) if gaps else 0.12 * cap


def _slots_fit(
    line: LineGeometry,
    placements: Sequence[Placement],
    by_position: dict[int, Choice],
    removed: Sequence[int],
) -> bool:
    """True when every new glyph keeps a normal gap to its neighbours."""
    extents = [(float(b.x0), float(b.x1)) for b in line.boxes]
    for placement, slot in zip(placements, removed, strict=True):
        x0, _, x1, _ = ink_bounds(by_position[placement.position].sample.rgba)
        half = (x1 - x0) * placement.scale / 2
        extents[slot] = (placement.x_center - half, placement.x_center + half)
    gap = _median_gap(line.boxes, line.cap_height)
    limit = _MIN_GAP_SHARE * max(gap, 1.0)
    changed = set(removed)
    for index in range(len(extents) - 1):
        near_change = index in changed or index + 1 in changed
        if near_change and extents[index + 1][0] - extents[index][1] < limit:
            return False
    return True


def slot_positions(new_text: str, line: LineGeometry) -> list[int] | None:
    """Positions that change when the original slots can be reused, else None.

    Slots are reused when the length and the space positions match, every label got
    ink, and no changed slot (or its neighbour) has an implausible segmentation.
    """
    old = line.labels
    if (
        len(old) != len(new_text)
        or any((a == " ") != (b == " ") for a, b in zip(old, new_text, strict=True))
        or line.missing
        or len(line.boxes) != sum(c != " " for c in old)
    ):
        return None
    changed: list[int] = []
    risky = set(line.suspect)
    slot = -1
    for position, (before, after) in enumerate(zip(old, new_text, strict=True)):
        if after == " ":
            continue
        slot += 1
        if before != after:
            if risky & {slot - 1, slot, slot + 1}:
                return None
            changed.append(position)
    return changed


def _scale(choice: Choice, line: LineGeometry, scale: float) -> float:
    return scale * line.cap_height / max(choice.sample.metrics.cap_height_px, 1.0)


def plan_slots(
    new_text: str,
    line: LineGeometry,
    choices: Sequence[Choice],
    *,
    dx: float = 0.0,
    dy: float = 0.0,
    scale: float = 1.0,
    spacing: float = 0.0,
) -> LayoutPlan | None:
    """Each changed character in its original slot; None when the glyphs do not fit.

    `choices` only needs the changed positions (see slot_positions).
    """
    changed = slot_positions(new_text, line)
    if changed is None:
        return None
    by_position = {c.position: c for c in choices}
    slot_of: dict[int, int] = {}
    slot = -1
    for position, char in enumerate(new_text):
        if char != " ":
            slot += 1
            slot_of[position] = slot
    middle = (len(changed) - 1) / 2
    placements = []
    for order, position in enumerate(changed):
        box = line.boxes[slot_of[position]]
        placements.append(
            Placement(
                position=position,
                char=new_text[position],
                x_center=(box.x0 + box.x1) / 2 + dx + spacing * (order - middle),
                baseline=line.baseline + dy,
                scale=_scale(by_position[position], line, scale),
            )
        )
    removed = [slot_of[p] for p in changed]
    if not _slots_fit(line, placements, by_position, removed):
        return None
    return LayoutPlan("slots", tuple(placements), tuple(removed))


def plan_relayout(
    new_text: str,
    line: LineGeometry,
    choices: Sequence[Choice],
    *,
    alignment: Alignment = "auto",
    spacing_mode: SpacingMode = "auto",
    dx: float = 0.0,
    dy: float = 0.0,
    scale: float = 1.0,
    spacing: float = 0.0,
) -> LayoutPlan:
    """The whole token laid out again from the original anchor (strip px)."""
    by_position = {c.position: c for c in choices}
    mono = spacing_mode == "monospace" or (spacing_mode == "auto" and _is_monospace(line.boxes))
    gap = _median_gap(line.boxes, line.cap_height) + spacing
    pitch = line.pitch + spacing

    # Advance widths, then centres relative to the start of the line.
    centres: list[tuple[int, str, float, float]] = []  # (position, char, centre, scale)
    cursor = 0.0
    for position, char in enumerate(new_text):
        if char == " ":
            cursor += pitch if mono else _SPACE_PER_CAP * line.cap_height * scale + gap
            continue
        choice = by_position[position]
        s = _scale(choice, line, scale)
        x0, _, x1, _ = ink_bounds(choice.sample.rgba)
        width = (x1 - x0) * s
        if mono:
            centres.append((position, char, cursor + pitch / 2, s))
            cursor += pitch
        else:
            centres.append((position, char, cursor + width / 2, s))
            cursor += width + gap
    total = (cursor if mono else cursor - gap) if centres else 0.0

    first, last = line.boxes[0], line.boxes[-1]
    if alignment == "right":
        start = last.x1 - total
    elif alignment == "center":
        start = (first.x0 + last.x1) / 2 - total / 2
    elif mono:  # keep the first character's cell where the original one was
        start = (first.x0 + first.x1) / 2 - pitch / 2
    else:  # left and auto: most fields and labels are left-aligned
        start = float(first.x0)

    placements = [
        Placement(position, char, start + centre + dx, line.baseline + dy, s)
        for position, char, centre, s in centres
    ]
    return LayoutPlan("relayout", tuple(placements), tuple(range(len(line.boxes))))
