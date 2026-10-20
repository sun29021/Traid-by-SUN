"""Glyph Transplant engine: prepare a token, then render new text into it (FR-E07…E14).

    prepare  rectify → segment → matte (same-image glyphs, target look)      ~0.1 s
    render   select → layout → remove (cached) → harmonize → composite → verify

`Synthesizer` is the swappable interface (FR-E14); a future generative engine
implements the same two calls. Rendering is deterministic for a given seed (FR-E13):
every random draw comes from the seed and no stage depends on timing or threads.
"""

from __future__ import annotations

import hashlib
import math
import time
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields
from typing import Any, ClassVar, Literal, Protocol

import cv2
import numpy as np
from numpy.typing import NDArray

from app.engine.composite import Composite, composite
from app.engine.detect import TextDetector
from app.engine.extract import STRIP_PADDING, line_angle
from app.engine.geometry import clip_quad, expand_quad, order_quad, rectify, transform_points
from app.engine.glyph_select import (
    SMALL_CHARS,
    Choice,
    GlyphSample,
    TargetConditions,
    agrees_with_bank,
    select_glyphs,
    variants,
)
from app.engine.harmonize import (
    Adjustments,
    TargetLook,
    full_density,
    glyph_density,
    relief_contrast,
    render_layer,
)
from app.engine.inpaint import RemovalResult, remove_text
from app.engine.layout import (
    Alignment,
    LayoutMode,
    LineGeometry,
    SpacingMode,
    plan_relayout,
    plan_slots,
    slot_positions,
)
from app.engine.matte import extract_glyphs
from app.engine.models import ModelRegistry
from app.engine.segment import BlendMode, segment
from app.engine.types import GrayImage, Homography, Quad, RGBImage
from app.engine.verify import OriginalLook, QualityReport, measure_blur, text_region, verify

ENGINE_VERSION = "glyph_transplant@1.0.0"

# Removal mask growth around the old ink (px): covers anti-aliased fringes; relief
# strokes also have highlight/shadow rims.
_REMOVAL_GROW: dict[BlendMode, int] = {"ink": 3, "relief": 4}
# Relief rims widen with the cap height (bevel width scales with the letters).
_RELIEF_GROW_PER_CAP = 0.12


class PreparationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RenderParams:
    """Owner adjustments (API.md §3.6). Distances are rectified-strip pixels."""

    dx: float = 0.0
    dy: float = 0.0
    scale: float = 1.0
    spacing: float = 0.0
    weight: float = 0.0
    blur: float = 0.0
    ink_tone: float = 0.0
    grain: float = 1.0
    glyph_overrides: Mapping[int, str] = field(default_factory=dict)

    RANGES: ClassVar[dict[str, tuple[float, float]]] = {
        "dx": (-50.0, 50.0),
        "dy": (-50.0, 50.0),
        "scale": (0.8, 1.2),
        "spacing": (-10.0, 10.0),
        "weight": (-1.0, 1.0),
        "blur": (-2.0, 2.0),
        "ink_tone": (-1.0, 1.0),
        "grain": (0.0, 3.0),
    }

    def __post_init__(self) -> None:
        for name, (low, high) in self.RANGES.items():
            value = getattr(self, name)
            if not (isinstance(value, int | float) and math.isfinite(value)):
                raise ValueError(f"{name} must be a number")
            if not low <= value <= high:
                raise ValueError(f"{name} must be between {low:g} and {high:g}")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> RenderParams:
        data = dict(data or {})
        overrides = {int(k): str(v) for k, v in dict(data.pop("glyph_overrides", {}) or {}).items()}
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"unknown parameter: {sorted(unknown)[0]}")
        return cls(**{k: float(v) for k, v in data.items()}, glyph_overrides=overrides)

    def to_dict(self) -> dict[str, Any]:
        values: dict[str, Any] = {name: getattr(self, name) for name in self.RANGES}
        values["glyph_overrides"] = {str(k): v for k, v in sorted(self.glyph_overrides.items())}
        return values


@dataclass(frozen=True, eq=False)
class PreparedRegion:
    key: str  # stable identity for caches
    quad: Quad
    to_image: Homography  # strip → image
    strip: RGBImage
    line: LineGeometry
    same_image: tuple[GlyphSample, ...]
    conditions: TargetConditions
    look: TargetLook
    original: OriginalLook
    mode: BlendMode
    image_size: tuple[int, int]  # (width, height)


@dataclass(frozen=True)
class GlyphUse:
    position: int
    char: str
    source: Literal["same_image", "bank", "kept"]
    glyph_id: str | None
    score: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "char": self.char,
            "source": self.source,
            "glyph_id": self.glyph_id,
            "score": None if self.score is None else round(self.score, 4),
        }


@dataclass(frozen=True, eq=False)
class RenderResult:
    image: RGBImage
    changed_mask: GrayImage  # 0/255
    removal_mask: GrayImage  # 0/255
    glyphs_used: tuple[GlyphUse, ...]
    quality: QualityReport
    layout_mode: LayoutMode
    warnings: tuple[str, ...]
    timings_ms: dict[str, float]


class Synthesizer(Protocol):
    version: str

    def prepare(
        self,
        image: RGBImage,
        quad: Quad,
        original_text: str,
        mode: BlendMode,
        *,
        char_positions: Sequence[float] = (),
        char_confidences: Sequence[float] = (),
    ) -> PreparedRegion: ...

    def render(
        self,
        image: RGBImage,
        prepared: PreparedRegion,
        new_text: str,
        bank: Sequence[GlyphSample],
        params: RenderParams,
        *,
        seed: int,
        alignment: Alignment = "auto",
        spacing_mode: SpacingMode = "auto",
    ) -> RenderResult: ...


# ---------------------------------------------------------------- prepare


def _hex_to_rgb(value: str) -> tuple[float, float, float]:
    return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))


def _grain(gray: NDArray[np.float32], region: NDArray[np.bool_]) -> float:
    residual = gray - cv2.GaussianBlur(gray, (0, 0), 1.5)
    values = residual[region]
    if values.size < 30:
        return 0.0
    return float(1.4826 * np.median(np.abs(values - np.median(values))))


def prepare_region(
    image: RGBImage,
    quad: Quad,
    original_text: str,
    mode: BlendMode,
    *,
    char_positions: Sequence[float] = (),
    char_confidences: Sequence[float] = (),
) -> PreparedRegion:
    """Measure the token being replaced. Raises PreparationError(SEGMENTATION_FAILED)."""
    height, width = image.shape[:2]
    quad = order_quad(quad)
    strip_quad = clip_quad(expand_quad(quad, STRIP_PADDING), width, height)
    rect = rectify(image, strip_quad)
    labels = original_text.replace(" ", "")
    if not labels:
        raise PreparationError("SEGMENTATION_FAILED", "The selected region has no text")
    positions = list(char_positions) if len(char_positions) == len(labels) else []
    confidences = list(char_confidences) if len(char_confidences) == len(labels) else None
    seg = segment(rect.patch, labels, positions, mode=mode, confidences=confidences)
    if not seg.chars:
        raise PreparationError("SEGMENTATION_FAILED", "No characters could be separated")
    crops = extract_glyphs(rect.patch, seg, mode)
    angle = line_angle(quad)
    suspect = tuple(
        index
        for index, box in enumerate(seg.chars)
        if not _plausible_box(box.char, box.width, box.height, seg.cap_height, seg.pitch)
    )
    all_samples = tuple(
        GlyphSample(
            char=c.char,
            rgba=c.rgba,
            metrics=c.metrics,
            angle_deg=angle,
            baseline_y=c.baseline_y,
            source="same_image",
            source_quad=transform_points(
                np.array(
                    [
                        [c.box[0], c.box[1]],
                        [c.box[2], c.box[1]],
                        [c.box[2], c.box[3]],
                        [c.box[0], c.box[3]],
                    ],
                    dtype=np.float32,
                ),
                rect.to_image,
            ),
        )
        for c in crops
    )
    same_image = tuple(s for i, s in enumerate(all_samples) if i not in suspect) or all_samples

    metrics = [s.metrics for s in same_image]
    densities = [glyph_density(s) for s in same_image]
    lights = [m.light_dir_deg for m in metrics if m.light_dir_deg is not None]
    conditions = TargetConditions(
        cap_height_px=seg.cap_height,
        stroke_width_px=float(np.median([m.stroke_width_px for m in metrics])),
        blur_sigma=float(np.median([m.blur_sigma for m in metrics])),
        bg_luma=float(np.median([m.bg_luma for m in metrics])),
        contrast=float(np.median([m.contrast for m in metrics])),
        angle_deg=angle,
        light_dir_deg=float(np.median(lights)) if lights else None,
        mode=mode,
    )

    gray = np.asarray(cv2.cvtColor(rect.patch, cv2.COLOR_RGB2GRAY), np.float32)
    core = cv2.erode(seg.ink.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    full = np.median(
        [full_density(d, s.rgba[..., 3]) for (d, _), s in zip(densities, same_image, strict=True)],
        axis=0,
    )
    spread = float(np.median([relief_contrast(d, sup) for d, sup in densities]))
    look = TargetLook(
        density=(float(full[0]), float(full[1]), float(full[2])),
        contrast=spread,
        blur_sigma=conditions.blur_sigma,
        ink_noise_sigma=_grain(gray, core),
        mode=mode,
    )
    ink_region = cv2.dilate(seg.ink.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    values = gray[ink_region]
    original = OriginalLook(
        blur_sigma=measure_blur(gray, text_region(seg.ink)),
        ink_rgb=_hex_to_rgb(metrics[0].ink_color),
        contrast=float(np.percentile(values, 95) - np.percentile(values, 5)) / 255.0,
        mode=mode,
    )
    line = LineGeometry(
        boxes=seg.chars,
        labels=original_text,
        cap_height=seg.cap_height,
        baseline=seg.baseline,
        pitch=seg.pitch,
        missing=seg.missing,
        suspect=suspect,
    )
    digest = hashlib.sha1(usedforsecurity=False)
    digest.update(np.ascontiguousarray(quad, np.float32).tobytes())
    digest.update(f"{width}x{height}|{mode}|{original_text}".encode())
    digest.update(rect.patch.tobytes())
    return PreparedRegion(
        key=digest.hexdigest(),
        quad=quad,
        to_image=rect.to_image,
        strip=rect.patch,
        line=line,
        same_image=same_image,
        conditions=conditions,
        look=look,
        original=original,
        mode=mode,
        image_size=(width, height),
    )


def _plausible_box(char: str, width: int, height: int, cap: float, pitch: float) -> bool:
    """A segmented character box that could really hold `char`."""
    if char in SMALL_CHARS:
        return width >= 0.15 * cap and height <= 0.8 * cap
    return height >= 0.55 * cap and width <= 1.8 * max(pitch, 0.6 * cap)


# ---------------------------------------------------------------- render helpers


def removal_mask(prepared: PreparedRegion, slots: Sequence[int]) -> GrayImage:
    """Old ink of `slots` (dilated), never touching the characters that stay, in image px."""
    strip_h, strip_w = prepared.strip.shape[:2]
    remove = np.zeros((strip_h, strip_w), np.uint8)
    keep = np.zeros((strip_h, strip_w), np.uint8)
    chosen = set(slots)
    for index, box in enumerate(prepared.line.boxes):
        target = remove if index in chosen else keep
        target[box.y0 : box.y1, box.x0 : box.x1] |= box.mask.astype(np.uint8)
    grow = _REMOVAL_GROW[prepared.mode]
    if prepared.mode == "relief":
        grow = max(grow, round(_RELIEF_GROW_PER_CAP * prepared.line.cap_height))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1))
    remove = np.asarray(cv2.dilate(remove, kernel), np.uint8)
    if keep.any():
        protected = cv2.dilate(keep, np.ones((3, 3), np.uint8)) > 0
        remove[protected] = 0
    width, height = prepared.image_size
    warped = cv2.warpPerspective(
        remove.astype(np.uint8) * 255,
        prepared.to_image,
        (width, height),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
    )
    return np.asarray(warped, np.uint8)


def _ink_grain(result: RGBImage, comp: Composite) -> float:
    if not comp.support.size:
        return 0.0
    x0, y0, x1, y1 = comp.roi
    gray = np.asarray(cv2.cvtColor(result[y0:y1, x0:x1], cv2.COLOR_RGB2GRAY), np.float32)
    strength = np.abs(comp.density).mean(axis=2)
    core = (comp.support > 0.9) & (strength > 0.5 * max(float(strength.max()), 1e-6))
    core = cv2.erode(core.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    return _grain(gray, core)


class GlyphTransplantSynthesizer:
    """The MVP engine (ARCHITECTURE §10.1)."""

    version = ENGINE_VERSION

    def __init__(
        self,
        *,
        registry: ModelRegistry | None = None,
        detector: TextDetector | None = None,
        removal_cache_size: int = 8,
    ) -> None:
        self.registry = registry
        self.detector = detector
        self._removals: OrderedDict[tuple[str, tuple[int, ...], int], RemovalResult] = OrderedDict()
        self._cache_size = removal_cache_size

    def prepare(
        self,
        image: RGBImage,
        quad: Quad,
        original_text: str,
        mode: BlendMode,
        *,
        char_positions: Sequence[float] = (),
        char_confidences: Sequence[float] = (),
    ) -> PreparedRegion:
        return prepare_region(
            image,
            quad,
            original_text,
            mode,
            char_positions=char_positions,
            char_confidences=char_confidences,
        )

    def variants(
        self, prepared: PreparedRegion, bank: Sequence[GlyphSample], char: str, limit: int = 6
    ) -> list[tuple[float, GlyphSample]]:
        return variants(char, prepared.same_image, bank, prepared.conditions, limit)

    def _remove(
        self, image: RGBImage, prepared: PreparedRegion, slots: tuple[int, ...], seed: int
    ) -> RemovalResult:
        key = (prepared.key, slots, seed)
        cached = self._removals.get(key)
        if cached is not None:
            self._removals.move_to_end(key)
            return cached
        result = remove_text(
            image, removal_mask(prepared, slots), registry=self.registry, dilate_px=0, seed=seed
        )
        self._removals[key] = result
        while len(self._removals) > self._cache_size:
            self._removals.popitem(last=False)
        return result

    def render(
        self,
        image: RGBImage,
        prepared: PreparedRegion,
        new_text: str,
        bank: Sequence[GlyphSample],
        params: RenderParams,
        *,
        seed: int,
        alignment: Alignment = "auto",
        spacing_mode: SpacingMode = "auto",
    ) -> RenderResult:
        """Raises GlyphMissingError when a character has no usable glyph."""
        timings: dict[str, float] = {}
        clock = time.perf_counter()

        def lap(stage: str) -> None:
            nonlocal clock
            now = time.perf_counter()
            timings[stage] = round((now - clock) * 1000, 1)
            clock = now

        # Same-image crops come from an unreviewed segmentation: drop any the reviewed
        # bank recognises as a different character.
        same_image = [s for s in prepared.same_image if agrees_with_bank(s, bank)]
        overrides = params.glyph_overrides
        plan = None
        changed = slot_positions(new_text, prepared.line)
        if changed is not None:
            # Slots first: only the changed characters need glyphs.
            choices: list[Choice] = select_glyphs(
                new_text,
                same_image,
                bank,
                prepared.conditions,
                overrides=overrides,
                positions=set(changed),
            )
            plan = plan_slots(
                new_text,
                prepared.line,
                choices,
                dx=params.dx,
                dy=params.dy,
                scale=params.scale,
                spacing=params.spacing,
            )
        if plan is None:
            choices = select_glyphs(
                new_text, same_image, bank, prepared.conditions, overrides=overrides
            )
            plan = plan_relayout(
                new_text,
                prepared.line,
                choices,
                alignment=alignment,
                spacing_mode=spacing_mode,
                dx=params.dx,
                dy=params.dy,
                scale=params.scale,
                spacing=params.spacing,
            )
        lap("layout")
        removal = self._remove(image, prepared, plan.removed_slots, seed)
        lap("remove")
        adjustments = Adjustments(weight=params.weight, blur=params.blur, ink_tone=params.ink_tone)
        layer = render_layer(choices, plan.placements, prepared.look, adjustments)
        lap("harmonize")
        comp = composite(
            image, removal.image, removal.mask, layer, prepared.to_image, grain_sigma=0.0, seed=seed
        )
        # Grain top-up: the new ink should be as grainy as the original ink was.
        have = _ink_grain(comp.image, comp)
        want = prepared.look.ink_noise_sigma
        top_up = math.sqrt(max(want**2 - have**2, 0.0)) * params.grain
        if top_up > 0.05:
            comp = composite(
                image,
                removal.image,
                removal.mask,
                layer,
                prepared.to_image,
                grain_sigma=top_up,
                seed=seed + 1,
            )
        lap("composite")
        quality = verify(image, comp, prepared.quad, new_text, prepared.original, self.detector)
        lap("verify")

        placed = {p.position for p in plan.placements}
        uses = [
            GlyphUse(c.position, c.char, c.sample.source, c.sample.glyph_id, c.score)
            for c in choices
            if c.position in placed
        ]
        uses += [
            GlyphUse(i, c, "kept", None, None)
            for i, c in enumerate(new_text)
            if c != " " and i not in placed
        ]
        warnings = ("INPAINT_FALLBACK_USED",) if removal.fallback_used else ()
        return RenderResult(
            image=comp.image,
            changed_mask=comp.changed,
            removal_mask=removal.mask,
            glyphs_used=tuple(sorted(uses, key=lambda u: u.position)),
            quality=quality,
            layout_mode=plan.mode,
            warnings=warnings,
            timings_ms=timings,
        )
