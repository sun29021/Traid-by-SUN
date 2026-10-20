"""Engine evaluation harness (IMPLEMENTATION_PLAN.md task 8.7, PRD §18).

Renders new tokens into synthetic fixture photos for every surface and writes
`results.csv` (one row per render) and `report.html` (summary per surface plus
before/after crops) to the output folder.

    backend\\.venv\\Scripts\\python.exe tests\\eval\\run_eval.py [--out DIR] [--seeds N]

Real photos replace the fixtures once the owner's evaluation set exists
(`--images` is reserved for that, Phase 15).
"""

from __future__ import annotations

import argparse
import base64
import csv
import html
import io
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from app.core.config import REPO_ROOT  # noqa: E402
from app.engine.detect import PaddleOcr  # noqa: E402
from app.engine.glyph_select import GlyphMissingError  # noqa: E402
from app.engine.models import ModelRegistry  # noqa: E402
from app.engine.pipeline import GlyphTransplantSynthesizer, RenderParams  # noqa: E402
from tests.fixtures.bank import blend_mode, build_bank  # noqa: E402
from tests.fixtures.generate import SURFACES, Surface, make_token_image  # noqa: E402

ORIGINAL = "A7-204913"
NEW_TEXTS = ("A7-204914", "B8-551067", "ZX-90", "QK-7731-W", "M3-0042")
CHECKS = ("ocr_readback", "seam", "noise", "sharpness", "colour", "outside_unchanged")


@dataclass
class Row:
    surface: Surface
    seed: int
    new_text: str
    status: str  # pass / warn / fail / blocked
    layout: str
    readback: str
    checks: dict[str, tuple[str, object]]
    ms: float
    crop_png: bytes | None


def _crop_pair(before: np.ndarray, after: np.ndarray, quad: np.ndarray) -> bytes:
    x0, y0 = np.maximum(np.floor(quad.min(axis=0)).astype(int) - 30, 0)
    x1, y1 = np.ceil(quad.max(axis=0)).astype(int) + 30
    pair = np.vstack([before[y0:y1, x0:x1], after[y0:y1, x0:x1]])
    buffer = io.BytesIO()
    Image.fromarray(pair).save(buffer, "PNG")
    return buffer.getvalue()


def run(seeds: int, out: Path) -> list[Row]:
    registry = ModelRegistry.from_manifest(REPO_ROOT / "models", device="cpu")
    detector = PaddleOcr(registry) if registry.ready else None
    synth = GlyphTransplantSynthesizer(registry=registry, detector=detector)
    rows: list[Row] = []
    for surface in SURFACES:
        bank = build_bank(surface)
        for seed in range(1, seeds + 1):
            fixture = make_token_image(ORIGINAL, surface, seed=200 + seed)
            prepared = synth.prepare(fixture.image, fixture.quad, ORIGINAL, blend_mode(surface))
            for new_text in NEW_TEXTS:
                start = time.perf_counter()
                try:
                    result = synth.render(
                        fixture.image, prepared, new_text, bank, RenderParams(), seed=seed
                    )
                except GlyphMissingError as error:
                    rows.append(
                        Row(surface, seed, new_text, "blocked", "-", str(error), {}, 0.0, None)
                    )
                    continue
                ms = (time.perf_counter() - start) * 1000
                checks = {c.id: (c.status, c.value) for c in result.quality.checks}
                readback = str(checks.get("ocr_readback", ("", ""))[1])
                png = _crop_pair(fixture.image, result.image, fixture.quad) if seed == 1 else None
                rows.append(
                    Row(
                        surface,
                        seed,
                        new_text,
                        result.quality.overall,
                        result.layout_mode,
                        readback,
                        checks,
                        ms,
                        png,
                    )
                )
                print(f"{surface:10} s{seed} {new_text:10} {result.quality.overall:5} {ms:6.0f} ms")
    out.mkdir(parents=True, exist_ok=True)
    _write_csv(rows, out / "results.csv")
    _write_html(rows, out / "report.html", ocr=detector is not None)
    return rows


def _write_csv(rows: list[Row], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        header = ["surface", "seed", "new_text", "status", "layout", "readback", "ms"]
        writer.writerow(header + [f"{c}_{k}" for c in CHECKS for k in ("status", "value")])
        for row in rows:
            values = [row.surface, row.seed, row.new_text, row.status, row.layout]
            values += [row.readback, round(row.ms)]
            for check in CHECKS:
                status, value = row.checks.get(check, ("", ""))
                values += [status, value]
            writer.writerow(values)


def summarise(rows: list[Row]) -> dict[str, dict[str, float]]:
    groups: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        groups[row.surface].append(row)
        groups["all"].append(row)
    summary: dict[str, dict[str, float]] = {}
    for name, group in groups.items():
        rendered = [r for r in group if r.status != "blocked"]
        read = [r for r in rendered if r.checks.get("ocr_readback", ("",))[0] == "pass"]
        seams = [float(r.checks["seam"][1]) for r in rendered if "seam" in r.checks]  # type: ignore[arg-type]
        summary[name] = {
            "renders": len(group),
            "blocked": len(group) - len(rendered),
            "pass": sum(r.status == "pass" for r in rendered),
            "warn": sum(r.status == "warn" for r in rendered),
            "fail": sum(r.status == "fail" for r in rendered),
            "readback": len(read) / len(rendered) if rendered else 0.0,
            "seam_median": float(np.median(seams)) if seams else 0.0,
            "ms_median": float(np.median([r.ms for r in rendered])) if rendered else 0.0,
        }
    return summary


def _write_html(rows: list[Row], path: Path, *, ocr: bool) -> None:
    summary = summarise(rows)
    lines = [
        "<!doctype html><meta charset=utf-8><title>Traid engine evaluation</title>",
        "<style>body{font:14px system-ui;margin:24px;color:#1b1f24}table{border-collapse:collapse}"
        "td,th{border:1px solid #d0d7de;padding:4px 8px;text-align:right}th{background:#f6f8fa}"
        "td:first-child{text-align:left}figure{display:inline-block;margin:8px}"
        "figcaption{font:12px ui-monospace,monospace}img{max-width:360px}</style>",
        "<h1>Traid engine evaluation</h1>",
        f"<p>Synthetic fixtures, engine {html.escape(GlyphTransplantSynthesizer.version)}. "
        f"OCR read-back {'on' if ocr else 'off (models missing)'}.</p>",
        "<table><tr><th>Surface</th><th>Renders</th><th>Blocked</th><th>Pass</th><th>Warn</th>"
        "<th>Fail</th><th>OCR read-back</th><th>Seam (median)</th><th>Time (median)</th></tr>",
    ]
    for name, s in summary.items():
        lines.append(
            f"<tr><td>{name}</td><td>{s['renders']:.0f}</td><td>{s['blocked']:.0f}</td>"
            f"<td>{s['pass']:.0f}</td><td>{s['warn']:.0f}</td><td>{s['fail']:.0f}</td>"
            f"<td>{s['readback']:.1%}</td><td>{s['seam_median']:.3f}</td>"
            f"<td>{s['ms_median']:.0f} ms</td></tr>"
        )
    lines.append("</table><h2>Before / after (seed 1)</h2>")
    for row in rows:
        if row.crop_png:
            data = base64.b64encode(row.crop_png).decode()
            label = f"{row.surface} → {row.new_text}: {row.status}, read {row.readback}"
            caption = html.escape(label)
            lines.append(
                f"<figure><img alt='{caption}' src='data:image/png;base64,{data}'>"
                f"<figcaption>{caption}</figcaption></figure>"
            )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=BACKEND / "tests" / "eval" / "out")
    parser.add_argument("--seeds", type=int, default=5)
    args = parser.parse_args()
    rows = run(args.seeds, args.out)
    for name, s in summarise(rows).items():
        print(
            f"{name:10} renders {s['renders']:.0f} blocked {s['blocked']:.0f} "
            f"pass {s['pass']:.0f} warn {s['warn']:.0f} fail {s['fail']:.0f} "
            f"read-back {s['readback']:.1%} seam {s['seam_median']:.3f} {s['ms_median']:.0f} ms"
        )
    print(f"Report: {args.out / 'report.html'}")


if __name__ == "__main__":
    main()
