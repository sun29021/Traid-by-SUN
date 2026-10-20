"""Blind-test kit for visual naturalness (PRD §18, Phase 15.2).

`make` builds a folder of pairs from accepted edits: each pair shows the same token
area from the original photo and from Traid's result, side by side in random order.
Viewers mark which side they think is edited on `sheet.csv`; `answers.json` holds the
key (keep it hidden). `score` reads the filled sheets and reports accuracy against the
target (edited image identified in ≤ 60 % of pairs; 50 % is chance).

    python tests\\eval\\blind_kit.py make --data-dir ..\\data --out kit --pairs 24
    python tests\\eval\\blind_kit.py score --kit kit sheets\\*.csv

Only images the owner edited and accepted are used. The kit stays on this computer.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

TARGET = 0.60
MARGIN = 0.6  # context around the token, relative to its height


def _crop_box(quad: list[list[float]], width: int, height: int) -> tuple[int, int, int, int]:
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    pad = (max(ys) - min(ys)) * MARGIN
    return (
        max(int(min(xs) - pad), 0),
        max(int(min(ys) - pad), 0),
        min(int(max(xs) + pad), width),
        min(int(max(ys) + pad), height),
    )


def make_kit(data_dir: Path, out: Path, pairs: int, seed: int = 0) -> int:
    db_path = data_dir / "traid.db"
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """SELECT j.id, j.selected_quad, i.storage_path AS input_path, r.storage_path AS result_path
           FROM edit_jobs j JOIN files i ON i.id = j.input_file_id
           JOIN files r ON r.id = j.result_file_id
           WHERE j.status = 'accepted' ORDER BY j.accepted_at"""
    ).fetchall()
    connection.close()
    rng = random.Random(seed)  # noqa: S311 — reproducible shuffling, not security
    chosen = rng.sample(list(rows), min(pairs, len(rows)))
    out.mkdir(parents=True, exist_ok=True)
    answers: dict[str, Any] = {}
    files = data_dir / "files"
    for number, row in enumerate(chosen, start=1):
        with (
            Image.open(files / row["input_path"]) as a,
            Image.open(files / row["result_path"]) as b,
        ):
            original = np.asarray(a.convert("RGB"))
            edited = np.asarray(b.convert("RGB"))
        box = _crop_box(json.loads(row["selected_quad"]), original.shape[1], original.shape[0])
        x0, y0, x1, y1 = box
        crops = {"original": original[y0:y1, x0:x1], "edited": edited[y0:y1, x0:x1]}
        left = rng.choice(["original", "edited"])
        right = "edited" if left == "original" else "original"
        gap = np.full((crops[left].shape[0], 16, 3), 255, np.uint8)
        pair_id = f"pair-{number:02d}"
        Image.fromarray(np.hstack([crops[left], gap, crops[right]])).save(out / f"{pair_id}.png")
        answers[pair_id] = {"edited": "left" if left == "edited" else "right", "job_id": row["id"]}
    (out / "answers.json").write_text(json.dumps(answers, indent=2), encoding="utf-8")
    with (out / "sheet.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["pair", "edited_side (left/right)"])
        for pair_id in answers:
            writer.writerow([pair_id, ""])
    return len(answers)


def score(kit: Path, sheets: list[Path]) -> dict[str, Any]:
    answers = json.loads((kit / "answers.json").read_text(encoding="utf-8"))
    correct = total = 0
    viewers = []
    for sheet in sheets:
        right = seen = 0
        with sheet.open(newline="", encoding="utf-8") as handle:
            for row in csv.reader(handle):
                if len(row) < 2 or row[0] not in answers:
                    continue
                guess = row[1].strip().lower()
                if guess not in ("left", "right"):
                    continue
                seen += 1
                right += guess == answers[row[0]]["edited"]
        viewers.append({"sheet": sheet.name, "answered": seen, "correct": right})
        correct += right
        total += seen
    accuracy = correct / total if total else None
    # One-sided binomial p-value of doing at least this well by guessing (p = 0.5).
    p_value = (
        sum(math.comb(total, k) for k in range(correct, total + 1)) / 2**total if total else None
    )
    return {
        "viewers": viewers,
        "answers": total,
        "accuracy": accuracy,
        "target": TARGET,
        "met": None if accuracy is None else accuracy <= TARGET,
        "p_value_vs_chance": p_value,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("make")
    make.add_argument("--data-dir", type=Path, required=True)
    make.add_argument("--out", type=Path, default=Path("kit"))
    make.add_argument("--pairs", type=int, default=24)
    make.add_argument("--seed", type=int, default=0)
    scorer = sub.add_parser("score")
    scorer.add_argument("--kit", type=Path, required=True)
    scorer.add_argument("sheets", type=Path, nargs="+")
    args = parser.parse_args()
    if args.command == "make":
        count = make_kit(args.data_dir, args.out, args.pairs, args.seed)
        print(f"{count} pairs written to {args.out} (keep answers.json hidden from viewers)")
    else:
        result = score(args.kit, args.sheets)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
