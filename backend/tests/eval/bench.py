"""Timing benchmark against PRD §9 (run on the owner's laptop, on AC power).

    backend\\.venv\\Scripts\\python.exe tests\\eval\\bench.py

Prints median seconds over a few runs for: detection on a 12 MP photo (CPU and GPU),
glyph extraction per reference, full render (plain surface and one that needs LaMa),
and a cached re-render after an adjustment.
"""

from __future__ import annotations

import statistics
import sys
import time
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from app.core.config import REPO_ROOT  # noqa: E402
from app.engine.detect import FakeDetector, PaddleOcr  # noqa: E402
from app.engine.extract import extract_from_image  # noqa: E402
from app.engine.models import ModelRegistry, available_devices  # noqa: E402
from app.engine.pipeline import GlyphTransplantSynthesizer, RenderParams  # noqa: E402
from app.engine.types import Region  # noqa: E402
from tests.fixtures.bank import CHARSET, build_bank  # noqa: E402
from tests.fixtures.generate import make_token_image  # noqa: E402

RUNS = 3


def median(fn: Callable[[], object], runs: int = RUNS) -> float:
    fn()  # warm-up: model sessions, caches
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        times.append(time.perf_counter() - start)
    return statistics.median(times)


def twelve_mp(image: np.ndarray) -> np.ndarray:
    return np.asarray(cv2.resize(image, (4000, 3000), interpolation=cv2.INTER_CUBIC), np.uint8)


def main() -> None:
    rows: list[tuple[str, float, str]] = []
    fixture = make_token_image("A7-204913", "print", seed=8)
    big = twelve_mp(fixture.image)
    for device in ("cpu", "directml"):
        if device != "cpu" and "directml" not in available_devices():
            continue
        ocr = PaddleOcr(ModelRegistry.from_manifest(REPO_ROOT / "models", device=device))  # type: ignore[arg-type]
        rows.append((f"detect 12 MP ({device})", median(lambda o=ocr: o.detect(big)), "<= 4 s CPU"))

    reference = make_token_image("0123456789", "print", seed=101)
    fake = FakeDetector([Region(quad=reference.quad, text=reference.text, confidence=0.99)])
    rows.append(
        (
            "extract one reference",
            median(lambda: extract_from_image(reference.image, fake, charset=CHARSET, mode="ink")),
            "<= 3 s",
        )
    )

    registry = ModelRegistry.from_manifest(REPO_ROOT / "models", device="cpu")
    bank = build_bank("print")
    for label, rule in (("plain", False), ("line through text (LaMa)", True)):
        scene = make_token_image("A7-204913", "print", seed=8, rule=rule)

        def full(scene=scene) -> None:
            synth = GlyphTransplantSynthesizer(registry=registry)  # fresh: no removal cache
            prepared = synth.prepare(scene.image, scene.quad, scene.text, "ink")
            synth.render(scene.image, prepared, "B8-551067", bank, RenderParams(), seed=1)

        rows.append((f"full render, {label} (CPU)", median(full, runs=2), "<= 10 s CPU"))

        synth = GlyphTransplantSynthesizer(registry=registry)
        prepared = synth.prepare(scene.image, scene.quad, scene.text, "ink")
        synth.render(scene.image, prepared, "B8-551067", bank, RenderParams(), seed=1)
        step = iter(np.linspace(-3, 3, 50))
        rows.append(
            (
                f"re-render after adjustment, {label}",
                median(
                    lambda s=synth, p=prepared, sc=scene, st=step: s.render(
                        sc.image, p, "B8-551067", bank, RenderParams(dx=float(next(st))), seed=1
                    )
                ),
                "<= 3 s",
            )
        )

    width = max(len(r[0]) for r in rows)
    for name, seconds, target in rows:
        print(f"{name:<{width}}  {seconds:6.2f} s   target {target}")


if __name__ == "__main__":
    main()
