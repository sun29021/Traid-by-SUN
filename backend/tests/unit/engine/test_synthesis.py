"""Glyph selection, layout and the full render pipeline on synthetic fixtures."""

import ast
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from app.engine.detect import PaddleOcr
from app.engine.glyph_select import (
    GlyphMissingError,
    GlyphSample,
    TargetConditions,
    learned_factor,
    rank,
    select_glyphs,
)
from app.engine.layout import LineGeometry, plan_relayout, plan_slots, slot_positions
from app.engine.pipeline import (
    GlyphTransplantSynthesizer,
    PreparedRegion,
    RenderParams,
    prepare_region,
)
from app.engine.segment import CharBox
from tests.fixtures.bank import blend_mode, build_bank
from tests.fixtures.generate import SURFACES, Surface, make_token_image

ENGINE_DIR = Path(__file__).resolve().parents[3] / "app" / "engine"
TEXT = "A7-204913"


@pytest.fixture(scope="module")
def print_bank() -> list[GlyphSample]:
    return build_bank("print")


@pytest.fixture(scope="module")
def print_scene() -> tuple[np.ndarray, PreparedRegion]:
    fixture = make_token_image(TEXT, "print", seed=8)
    return fixture.image, prepare_region(fixture.image, fixture.quad, TEXT, "ink")


def _target(**changes: object) -> TargetConditions:
    base = TargetConditions(
        cap_height_px=40.0,
        stroke_width_px=5.0,
        blur_sigma=0.8,
        bg_luma=0.85,
        contrast=0.6,
        angle_deg=0.0,
        light_dir_deg=None,
        mode="ink",
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def _sample(char: str, source: str = "bank", **metrics: object) -> GlyphSample:
    from app.engine.matte import GlyphMetrics

    base = GlyphMetrics(
        cap_height_px=40.0,
        stroke_width_px=5.0,
        blur_sigma=0.8,
        noise_sigma=2.0,
        ink_color="#202020",
        bg_luma=0.85,
        contrast=0.6,
        light_dir_deg=None,
        isolation=1.0,
        clipped=False,
        quality=0.9,
    )
    rgba = np.zeros((50, 30, 4), np.uint8)
    rgba[5:45, 5:25, 3] = 255
    return GlyphSample(
        char=char,
        rgba=rgba,
        metrics=replace(base, **metrics),  # type: ignore[arg-type]
        angle_deg=0.0,
        baseline_y=45.0,
        source=source,  # type: ignore[arg-type]
        glyph_id=f"{char}-{source}-{id(metrics)}",
    )


# ---------------------------------------------------------------- glyph selection


def test_learned_factor_follows_the_documented_formula() -> None:
    assert learned_factor(0, 0) == 1.0
    assert learned_factor(3, 0) == 1.0
    assert learned_factor(0, 1) == pytest.approx(1 / 3)
    assert learned_factor(4, 1) == pytest.approx(5 / 7)


def test_same_image_glyphs_come_before_better_bank_glyphs() -> None:
    same = _sample("7", "same_image", blur_sigma=2.0)  # worse conditions on purpose
    bank = _sample("7", "bank")

    ranked = rank("7", [bank, same], _target())

    assert ranked[0][1] is same


def test_bank_ranking_prefers_similar_capture_and_accepted_glyphs() -> None:
    close = _sample("A", blur_sigma=0.8)
    blurry = _sample("A", blur_sigma=2.5)
    rejected = replace(_sample("A"), reject_count=4)

    ranked = [s for _, s in rank("A", [blurry, rejected, close], _target())]

    assert ranked[0] is close
    assert ranked.index(rejected) > 0 and ranked.index(blurry) > 0


def test_missing_characters_block_the_render() -> None:
    with pytest.raises(GlyphMissingError) as error:
        select_glyphs("AZQ", [], [_sample("A")], _target())
    assert error.value.missing == ["Q", "Z"]


def test_override_must_name_a_glyph_of_the_same_character() -> None:
    a = _sample("A")
    b = _sample("B")
    chosen = select_glyphs("A", [], [a, b], _target(), overrides={0: str(a.glyph_id)})
    assert chosen[0].sample is a
    with pytest.raises(ValueError, match="not a 'A'"):
        select_glyphs("A", [], [a, b], _target(), overrides={0: str(b.glyph_id)})


def test_repeated_characters_use_different_real_samples() -> None:
    first, second = _sample("1", quality=0.9), _sample("1", quality=0.88)

    chosen = select_glyphs("11", [], [first, second], _target())

    assert chosen[0].sample is not chosen[1].sample


# ---------------------------------------------------------------- layout


def _line(labels: str, width: int = 30, gap: int = 6) -> LineGeometry:
    boxes = []
    x = 10
    for char in labels.replace(" ", ""):
        boxes.append(
            CharBox(char, x, 10, x + width, 50, np.ones((40, width), bool), confidence=0.99)
        )
        x += width + gap
    return LineGeometry(
        boxes=tuple(boxes), labels=labels, cap_height=40.0, baseline=50.0, pitch=width + gap
    )


def test_slot_positions_only_for_the_same_shape() -> None:
    line = _line("AB-12")
    assert slot_positions("AB-13", line) == [4]
    assert slot_positions("AB-123", line) is None
    assert slot_positions("AB 12", line) is None  # space where there was ink
    assert slot_positions("AB-13", replace(line, suspect=(4,))) is None
    assert slot_positions("XB-12", replace(line, suspect=(4,))) == [0]


def test_slots_keep_unchanged_characters_and_reuse_the_slot() -> None:
    line = _line("AB-12")
    choices = select_glyphs("AB-13", [], [_sample("3")], _target(), positions={4})

    plan = plan_slots("AB-13", line, choices)

    assert plan is not None and plan.mode == "slots"
    assert plan.removed_slots == (4,)
    (placement,) = plan.placements
    assert placement.x_center == pytest.approx((line.boxes[4].x0 + line.boxes[4].x1) / 2)
    assert placement.baseline == 50.0 and placement.scale == pytest.approx(1.0)


def test_a_glyph_too_wide_for_its_slot_needs_a_relayout() -> None:
    line = _line("AB-12")
    rgba = np.zeros((50, 70, 4), np.uint8)
    rgba[5:45, 5:65, 3] = 255  # 60 px of ink in a 30 px slot
    wide = replace(_sample("W"), rgba=rgba)
    choices = select_glyphs("AW-12", [], [wide], _target(), positions={1})

    assert plan_slots("AW-12", line, choices) is None


def test_relayout_alignment_anchors() -> None:
    line = _line("AB-12")
    bank = [_sample(c) for c in "XY"]
    choices = select_glyphs("XY", [], bank, _target())

    left = plan_relayout("XY", line, choices, alignment="left", spacing_mode="proportional")
    right = plan_relayout("XY", line, choices, alignment="right", spacing_mode="proportional")
    centre = plan_relayout("XY", line, choices, alignment="center", spacing_mode="proportional")

    assert left.mode == "relayout" and left.removed_slots == (0, 1, 2, 3, 4)
    assert left.placements[0].x_center - 10 == pytest.approx(10)  # ink starts at x0
    assert right.placements[-1].x_center + 10 == pytest.approx(line.boxes[-1].x1)
    mid = (line.boxes[0].x0 + line.boxes[-1].x1) / 2
    assert np.mean([p.x_center for p in centre.placements]) == pytest.approx(mid)


# ---------------------------------------------------------------- pipeline


def test_render_params_validate_ranges_and_round_trip() -> None:
    params = RenderParams.from_dict({"dx": 3, "grain": 0.5, "glyph_overrides": {"2": "g1"}})
    assert params.glyph_overrides == {2: "g1"}
    assert RenderParams.from_dict(params.to_dict()) == params
    with pytest.raises(ValueError, match="scale"):
        RenderParams(scale=1.5)
    with pytest.raises(ValueError, match="unknown"):
        RenderParams.from_dict({"opacity": 1})


def test_same_length_edit_changes_only_the_changed_character(
    print_scene: tuple[np.ndarray, PreparedRegion], print_bank: list[GlyphSample]
) -> None:
    image, prepared = print_scene
    synth = GlyphTransplantSynthesizer()

    result = synth.render(image, prepared, "A7-204914", print_bank, RenderParams(), seed=3)

    assert result.layout_mode == "slots"
    assert [u.source for u in result.glyphs_used].count("kept") == 8
    changed = result.changed_mask > 0
    # Only the area around the last character changed.
    xs = np.nonzero(changed)[1]
    last = prepared.quad[:, 0].max()
    assert xs.min() > last - 0.2 * (last - prepared.quad[:, 0].min())
    assert np.array_equal(result.image[~changed], image[~changed])
    assert result.quality.check("outside_unchanged").status == "pass"  # type: ignore[union-attr]


def test_render_is_deterministic_for_a_seed(
    print_scene: tuple[np.ndarray, PreparedRegion], print_bank: list[GlyphSample]
) -> None:
    image, prepared = print_scene
    first = GlyphTransplantSynthesizer().render(
        image, prepared, "B8-551067", print_bank, RenderParams(), seed=11
    )
    again = GlyphTransplantSynthesizer().render(
        image, prepared, "B8-551067", print_bank, RenderParams(), seed=11
    )
    other = GlyphTransplantSynthesizer().render(
        image, prepared, "B8-551067", print_bank, RenderParams(), seed=12
    )

    assert first.image.tobytes() == again.image.tobytes()
    assert first.image.tobytes() != other.image.tobytes()


def test_adjustments_move_and_darken_the_new_glyphs(
    print_scene: tuple[np.ndarray, PreparedRegion], print_bank: list[GlyphSample]
) -> None:
    image, prepared = print_scene
    synth = GlyphTransplantSynthesizer()
    base = synth.render(image, prepared, "ZX-90", print_bank, RenderParams(), seed=1)
    shifted = synth.render(image, prepared, "ZX-90", print_bank, RenderParams(dx=6), seed=1)
    darker = synth.render(image, prepared, "ZX-90", print_bank, RenderParams(ink_tone=1), seed=1)

    region = (base.changed_mask > 0) | (shifted.changed_mask > 0)

    def ink_centre(img: np.ndarray) -> float:
        darkness = np.clip(200.0 - img.mean(axis=2), 0, None) * region
        return float((darkness.sum(axis=0) * np.arange(img.shape[1])).sum() / darkness.sum())

    assert ink_centre(shifted.image) > ink_centre(base.image) + 3
    assert darker.image[region].mean() < base.image[region].mean()


def test_quality_report_shape(
    print_scene: tuple[np.ndarray, PreparedRegion], print_bank: list[GlyphSample]
) -> None:
    image, prepared = print_scene
    result = GlyphTransplantSynthesizer().render(
        image, prepared, "ZX-90", print_bank, RenderParams(), seed=1
    )

    report = result.quality.to_dict()
    ids = [c["id"] for c in report["checks"]]  # type: ignore[index]
    assert ids == ["seam", "noise", "sharpness", "colour", "outside_unchanged"]
    assert result.quality.overall == "pass"
    assert set(result.timings_ms) == {"layout", "remove", "harmonize", "composite", "verify"}


def test_render_time_budget(
    print_scene: tuple[np.ndarray, PreparedRegion], print_bank: list[GlyphSample]
) -> None:
    """ARCHITECTURE §3.3: a re-render after an adjustment is ≤ 3 s on CPU."""
    image, prepared = print_scene
    synth = GlyphTransplantSynthesizer()
    synth.render(image, prepared, "QK-7731-W", print_bank, RenderParams(), seed=2)

    start = time.perf_counter()
    synth.render(image, prepared, "QK-7731-W", print_bank, RenderParams(dx=1), seed=2)

    assert time.perf_counter() - start < 3.0


def test_engine_never_draws_text_with_a_font() -> None:
    """PRD FR-E07: no system-font fallback exists anywhere in the engine."""
    forbidden = {"ImageFont", "putText", "freetype", "truetype", "load_default"}
    for path in ENGINE_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {
            node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "")
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute | ast.Name)
        }
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import | ast.ImportFrom)
            for alias in node.names
        }
        assert not (names | imports) & forbidden, path.name


@pytest.mark.models
@pytest.mark.parametrize("surface", ["print", "paint", "laser_mark"])
@pytest.mark.parametrize("new_text", ["A7-204914", "B8-551067", "ZX-90"])
def test_ocr_reads_the_new_token(ocr: PaddleOcr, surface: Surface, new_text: str) -> None:
    fixture = make_token_image(TEXT, surface, seed=8)
    bank = _banks(surface)
    synth = GlyphTransplantSynthesizer(detector=ocr)
    prepared = synth.prepare(fixture.image, fixture.quad, TEXT, blend_mode(surface))

    result = synth.render(fixture.image, prepared, new_text, bank, RenderParams(), seed=5)

    readback = result.quality.check("ocr_readback")
    assert readback is not None and readback.status == "pass", readback
    assert result.quality.overall == "pass", result.quality.to_dict()


_BANK_CACHE: dict[str, list[GlyphSample]] = {}


def _banks(surface: Surface) -> list[GlyphSample]:
    if surface not in _BANK_CACHE:
        _BANK_CACHE[surface] = build_bank(surface)
    return _BANK_CACHE[surface]


def test_all_surfaces_have_fixture_banks() -> None:
    assert set(SURFACES) == {"print", "paint", "laser_mark", "engraved"}
