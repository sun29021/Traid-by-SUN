"""PRD §18 success-criteria report over the owner's real edits (Phase 15.1).

Reads Traid's database **read-only** (never changes it) and writes `showcase.json`
and `showcase.html` with: OCR read-back rate, acceptance of first renders without
adjustments, time per token, learning effect and stability.

    cd backend
    .venv\\Scripts\\python.exe tests\\eval\\showcase_report.py --data-dir ..\\data --out showcase
"""

from __future__ import annotations

import argparse
import html
import json
import sqlite3
import statistics
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_PARAMS = {
    "dx": 0.0,
    "dy": 0.0,
    "scale": 1.0,
    "spacing": 0.0,
    "weight": 0.0,
    "blur": 0.0,
    "ink_tone": 0.0,
    "grain": 1.0,
}


@dataclass(frozen=True)
class Criterion:
    name: str
    target: str
    value: str
    met: bool | None  # None: not enough data yet
    detail: str


def _connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def _untouched(params: dict[str, Any]) -> bool:
    if params.get("glyph_overrides"):
        return False
    return all(abs(float(params.get(k, v)) - v) < 1e-6 for k, v in DEFAULT_PARAMS.items())


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.0%}"


def evaluate(db_path: Path) -> dict[str, Any]:
    with _connect(db_path) as db:
        jobs = [dict(r) for r in db.execute("SELECT * FROM edit_jobs ORDER BY created_at, id")]
        tasks = [dict(r) for r in db.execute("SELECT type, status, error_code FROM tasks")]
    for job in jobs:
        job["params"] = json.loads(job["params"] or "{}")
        job["quality"] = json.loads(job["quality"]) if job["quality"] else None

    rendered = [j for j in jobs if j["quality"]]
    readback = [
        next((c for c in j["quality"]["checks"] if c["id"] == "ocr_readback"), None)
        for j in rendered
    ]
    read_ok = sum(1 for c in readback if c and c["status"] == "pass")
    read_total = sum(1 for c in readback if c)

    decided = [j for j in jobs if j["status"] in ("accepted", "rejected") and j["batch_id"] is None]
    accepted_untouched = sum(
        1 for j in decided if j["status"] == "accepted" and _untouched(j["params"])
    )

    durations = []
    for job in jobs:
        start, end = _time(job["created_at"]), _time(job["exported_at"] or job["accepted_at"])
        if start and end and job["batch_id"] is None:
            durations.append((end - start).total_seconds())

    first_ten = decided[:10]
    accepted_seen = 0
    after_fifty: list[dict[str, Any]] = []
    for job in decided:
        if accepted_seen >= 50:
            after_fifty.append(job)
        if job["status"] == "accepted":
            accepted_seen += 1
    early = _rate(sum(j["status"] == "accepted" for j in first_ten), len(first_ten))
    late = _rate(sum(j["status"] == "accepted" for j in after_fifty), len(after_fifty))

    crashes = sum(1 for t in tasks if t["error_code"] in ("INTERNAL_ERROR", "TASK_INTERRUPTED"))
    read_rate = _rate(read_ok, read_total)
    accept_rate = _rate(accepted_untouched, len(decided))
    criteria = [
        Criterion(
            "OCR read-back correctness",
            "≥ 98 % of results (≥ 100 edits)",
            f"{_pct(read_rate)} of {read_total}",
            None if read_total < 100 else bool(read_rate is not None and read_rate >= 0.98),
            f"{read_ok} of {read_total} rendered results read back exactly.",
        ),
        Criterion(
            "Acceptance without fine-tuning",
            "≥ 80 % of first renders accepted",
            f"{_pct(accept_rate)} of {len(decided)}",
            None if len(decided) < 20 else bool(accept_rate is not None and accept_rate >= 0.8),
            "Accepted with default adjustments and no glyph overrides, "
            "over all decided single edits.",
        ),
        Criterion(
            "Time per token",
            "≤ 60 s from drop to export",
            f"{statistics.median(durations):.0f} s median" if durations else "—",
            None if not durations else statistics.median(durations) <= 60,
            f"{len(durations)} edits timed from upload to export (or accept).",
        ),
        Criterion(
            "Learning effect",
            "after 50 accepts ≥ first 10 + 10 points",
            f"{_pct(early)} → {_pct(late)}",
            None if early is None or late is None else late >= early + 0.10,
            f"First 10 decided edits vs. the {len(after_fifty)} decided after the 50th accept.",
        ),
        Criterion(
            "Stability",
            "zero crashes, zero data loss",
            f"{crashes} crashed task(s)",
            crashes == 0,
            "Tasks that ended with INTERNAL_ERROR or TASK_INTERRUPTED.",
        ),
    ]
    return {
        "jobs": len(jobs),
        "rendered": len(rendered),
        "criteria": [c.__dict__ for c in criteria],
    }


def write_report(result: dict[str, Any], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "showcase.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    rows = "".join(
        f"<tr><td>{html.escape(c['name'])}</td><td>{html.escape(c['target'])}</td>"
        f"<td>{html.escape(c['value'])}</td>"
        f"<td>{'Met' if c['met'] else 'Not met' if c['met'] is False else 'Not enough data'}</td>"
        f"<td>{html.escape(c['detail'])}</td></tr>"
        for c in result["criteria"]
    )
    (out / "showcase.html").write_text(
        "<!doctype html><meta charset=utf-8><title>Traid showcase report</title>"
        "<style>body{font:14px system-ui;margin:24px}table{border-collapse:collapse}"
        "td,th{border:1px solid #ccc;padding:6px 10px;text-align:left}</style>"
        f"<h1>Traid — success criteria (PRD §18)</h1><p>{result['jobs']} edit jobs, "
        f"{result['rendered']} rendered. Blind-test naturalness is scored separately "
        "(blind_kit.py).</p><table><tr><th>Criterion</th><th>Target</th><th>Result</th>"
        f"<th>Status</th><th>How</th></tr>{rows}</table>"
        "<p>Traid · Designed &amp; developed by Xavier Sun</p>",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("showcase"))
    args = parser.parse_args()
    result = evaluate(args.data_dir / "traid.db")
    write_report(result, args.out)
    for c in result["criteria"]:
        status = "MET" if c["met"] else "NOT MET" if c["met"] is False else "NEEDS DATA"
        print(f"{c['name']:<32} {c['value']:<22} {status}")
    print(f"Report: {args.out / 'showcase.html'}")


if __name__ == "__main__":
    main()
