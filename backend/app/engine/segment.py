"""Character segmentation inside a rectified text strip (PRD FR-E04).

1. Ink map: difference between the strip and a large median filter (the local
   background). Ink mode keeps one polarity (dark-on-light or light-on-dark);
   relief mode (laser marks, engraving) keeps both highlights and shadows and closes
   them into strokes.
2. Connected components that overlap horizontally (an i and its dot, a colon) form
   column groups. Groups are reconciled with the number of labels: fragments merge
   into their nearest neighbour; touching characters split at the thinnest column
   (the group holding the most recogniser centres splits first). Groups then map to
   labels left to right. Recogniser positions (CTC) drift by a few pixels, so they
   only guide splits, never the assignment itself.

Spaces are NOT inferred from ink gaps: measured on fixtures, gaps at real spaces
(0.24-0.41 x cap height) overlap normal letter gaps next to narrow glyphs such as
"1" (up to 0.47). Spaces come from the recogniser when it emits them, from the
owner's known text, or from the profile's token pattern.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np
from numpy.typing import NDArray

from app.engine.types import RGBImage

BlendMode = Literal["ink", "relief"]
Polarity = Literal["dark", "light", "relief"]

# Characters that hang below the baseline; excluded when estimating the baseline.
_DESCENDERS = frozenset("gjpqy,;")


@dataclass(frozen=True, eq=False)
class CharBox:
    char: str
    x0: int
    y0: int
    x1: int  # exclusive
    y1: int  # exclusive
    mask: NDArray[np.bool_]  # ink pixels of this character, shape (y1 - y0, x1 - x0)
    confidence: float

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0


@dataclass(frozen=True, eq=False)
class Segmentation:
    chars: tuple[CharBox, ...]  # non-space characters that have ink, left to right
    missing: tuple[int, ...]  # indices into the input labels that got no ink
    ink: NDArray[np.bool_]  # ink map of the whole strip
    polarity: Polarity
    cap_height: float
    baseline: float
    pitch: float


def _odd(value: float, low: int = 3, high: int = 255) -> int:
    size = int(max(low, min(high, round(value))))
    return size if size % 2 else size + 1


def ink_map(strip: RGBImage, mode: BlendMode) -> tuple[NDArray[np.bool_], Polarity]:
    gray = cv2.cvtColor(strip, cv2.COLOR_RGB2GRAY)
    height = gray.shape[0]
    background = cv2.medianBlur(gray, _odd(height * 0.9))
    diff = gray.astype(np.int16) - background.astype(np.int16)
    magnitude = np.abs(diff).astype(np.uint8)
    threshold, _ = cv2.threshold(magnitude, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    threshold = max(threshold, 8.0)  # never treat sensor noise as ink

    if mode == "relief":
        # Highlights and shadows both count. Only a minimal closing: column grouping
        # already joins a stroke's highlight and shadow, and a larger kernel fuses the
        # rims of neighbouring letters (measured on engraved fixtures).
        candidate = magnitude > threshold
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        closed = cv2.morphologyEx(candidate.astype(np.uint8), cv2.MORPH_CLOSE, kernel)
        return closed.astype(bool), "relief"

    strong = magnitude > threshold
    dark = int(np.count_nonzero(strong & (diff < 0)))
    light = int(np.count_nonzero(strong & (diff > 0)))
    polarity: Polarity = "dark" if dark >= light else "light"
    ink = strong & ((diff < 0) if polarity == "dark" else (diff > 0))
    return ink, polarity


def _clean(ink: NDArray[np.bool_]) -> tuple[NDArray[np.int32], NDArray[np.int32]]:
    """Label components, dropping specks and strip-border artefacts."""
    height, width = ink.shape
    count, labels, stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
    min_area = max(4.0, (height * 0.035) ** 2)
    keep = np.zeros(count, dtype=bool)
    for label in range(1, count):
        _, y, w, h, area = stats[label]
        # Long horizontal lines (label edges, underlines) are not characters. Tall
        # components are kept: a tight text box makes real letters fill the height.
        border_line = w >= 0.9 * width
        # Small slivers cut off at the top/bottom edge belong to neighbouring lines.
        cut_off = (y == 0 or y + h == height) and h < 0.25 * height
        if area >= min_area and not border_line and not cut_off:
            keep[label] = True
    kept = np.asarray(np.where(keep[labels], labels, 0), dtype=np.int32)
    return kept, np.asarray(stats, dtype=np.int32)


@dataclass
class _Group:
    """Ink pixels of one candidate character (absolute strip coordinates)."""

    mask: NDArray[np.bool_]  # full-strip mask
    x0: int
    x1: int  # exclusive

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def area(self) -> int:
        return int(np.count_nonzero(self.mask))


def _group(mask: NDArray[np.bool_]) -> _Group:
    xs = np.nonzero(mask.any(axis=0))[0]
    return _Group(mask, int(xs.min()), int(xs.max()) + 1)


def _column_groups(labels: NDArray[np.int32]) -> list[_Group]:
    """Components merged when their x-ranges overlap by half of the narrower one."""
    groups = [_group(labels == label) for label in np.unique(labels) if label != 0]
    groups.sort(key=lambda g: g.x0)
    merged: list[_Group] = []
    for group in groups:
        if merged:
            last = merged[-1]
            overlap = min(last.x1, group.x1) - max(last.x0, group.x0)
            if overlap >= 0.5 * min(last.width, group.width):
                merged[-1] = _group(last.mask | group.mask)
                continue
        merged.append(group)
    return merged


def _merge_smallest(groups: list[_Group]) -> None:
    """Merge the smallest group (a fragment) into its nearer neighbour."""
    index = min(range(len(groups)), key=lambda i: groups[i].area)
    candidates = [i for i in (index - 1, index + 1) if 0 <= i < len(groups)]
    gap = {i: max(groups[max(i, index)].x0 - groups[min(i, index)].x1, 0) for i in candidates}
    other = min(candidates, key=lambda i: gap[i])
    first, second = sorted((index, other))
    groups[first : second + 1] = [_group(groups[first].mask | groups[second].mask)]


def _split_one(groups: list[_Group], centers: Sequence[float]) -> None:
    """Split the group most likely to hold two touching characters."""

    def centres_inside(group: _Group) -> int:
        return sum(group.x0 <= c < group.x1 for c in centers)

    def plausible_pair(group: _Group) -> bool:
        # Two touching characters are wide relative to their height (measured: merged
        # "11" ~0.6 h); a lone narrow stroke is a single character with a missing
        # neighbour, which must be reported, not cut in half.
        rows = np.nonzero(group.mask.any(axis=1))[0]
        height = int(rows.max() - rows.min() + 1) if len(rows) else 1
        return centres_inside(group) >= 2 or group.width >= 0.6 * height

    candidates = [i for i in range(len(groups)) if plausible_pair(groups[i])]
    if not candidates:
        raise _CannotSplitError
    median_width = float(np.median([g.width for g in groups]))
    index = max(
        candidates,
        key=lambda i: (centres_inside(groups[i]), groups[i].width / max(median_width, 1.0)),
    )
    group = groups[index]
    if group.width < 2:
        raise _CannotSplitError
    inner = [c for c in centers if group.x0 < c < group.x1]
    if len(inner) >= 2:  # cut at the thinnest column between the first two centres
        lo, hi = int(inner[0]) + 1, int(inner[1])
    else:  # thinnest column near the middle (a wider window finds letter interiors,
        # such as the crossbar of an H, instead of the junction)
        lo, hi = group.x0 + int(group.width * 0.35), group.x0 + int(group.width * 0.65)
    lo, hi = max(lo, group.x0 + 1), max(min(hi, group.x1 - 1), max(lo, group.x0 + 1) + 1)
    profile = group.mask[:, lo:hi].sum(axis=0)
    cut = lo + int(np.argmin(profile))
    left, right = group.mask.copy(), group.mask.copy()
    left[:, cut:] = False
    right[:, :cut] = False
    if not left.any() or not right.any():
        raise _CannotSplitError
    groups[index : index + 1] = [_group(left), _group(right)]


class _CannotSplitError(Exception):
    pass


def segment(
    strip: RGBImage,
    labels: str,
    positions: Sequence[float],
    *,
    mode: BlendMode = "ink",
    confidences: Sequence[float] | None = None,
) -> Segmentation:
    """Split `strip` into the characters of `labels` (no spaces).

    `positions` (0..1 along the strip, one per label) only guide where touching
    characters are split; they are ignored when their count does not match the labels
    (e.g. labels from the owner's known text instead of OCR).
    """
    width = strip.shape[1]
    ink, polarity = ink_map(strip, mode)
    component_labels, _ = _clean(ink)
    centers = [p * width for p in positions] if len(positions) == len(labels) else []
    groups = _column_groups(component_labels)
    while len(groups) > len(labels) and len(groups) > 1:
        _merge_smallest(groups)
    try:
        while 0 < len(groups) < len(labels):
            _split_one(groups, centers)
    except _CannotSplitError:
        pass

    # Groups map to labels left to right. If splitting could not reach the label count,
    # the trailing labels have no ink and are reported as missing.
    pixels: list[NDArray[np.bool_] | None] = [g.mask for g in groups[: len(labels)]]
    pixels += [None] * (len(labels) - len(pixels))

    boxes: list[CharBox] = []
    missing: list[int] = []
    for index, (char, mask) in enumerate(zip(labels, pixels, strict=True)):
        if mask is None:
            missing.append(index)
            continue
        ys, xs = np.nonzero(mask)
        x0, x1, y0, y1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
        confidence = float(confidences[index]) if confidences is not None else 1.0
        boxes.append(CharBox(char, x0, y0, x1, y1, mask[y0:y1, x0:x1].copy(), confidence))

    cap_height, baseline, pitch = _metrics(boxes)
    return Segmentation(
        chars=tuple(boxes),
        missing=tuple(missing),
        ink=ink,
        polarity=polarity,
        cap_height=cap_height,
        baseline=baseline,
        pitch=pitch,
    )


def _metrics(boxes: Sequence[CharBox]) -> tuple[float, float, float]:
    """Cap height, baseline (y) and pitch (median centre distance) of a line."""
    if not boxes:
        return 0.0, 0.0, 0.0
    tall = [b for b in boxes if b.char.isupper() or b.char.isdigit()] or list(boxes)
    cap_height = float(np.median([b.height for b in tall]))
    base = [b for b in boxes if b.char not in _DESCENDERS] or list(boxes)
    baseline = float(np.median([b.y1 for b in base]))
    centers = [(b.x0 + b.x1) / 2 for b in boxes]
    pitch = float(np.median(np.diff(centers))) if len(centers) > 1 else float(boxes[0].width)
    return cap_height, baseline, pitch
