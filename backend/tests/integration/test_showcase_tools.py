"""Phase 15 tools run on a real Traid database (read-only)."""

import csv
import hashlib
import json
from pathlib import Path

from app.core.config import Settings
from tests.eval.blind_kit import make_kit, score
from tests.eval.showcase_report import evaluate, write_report
from tests.integration.conftest import Studio
from tests.integration.test_jobs_api import _ready_profile, _rendered


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_report_and_blind_kit(studio: Studio, settings: Settings, tmp_path: Path) -> None:
    profile = _ready_profile(studio)
    accepted = []
    for text in ("A7-204914", "ZX-58", "A7-204915"):
        job = _rendered(studio, profile["id"], text)
        studio.client.post(f"/api/v1/jobs/{job['id']}/accept")
        accepted.append(job["id"])
    rejected = _rendered(studio, profile["id"], "A7-204916")
    studio.client.post(f"/api/v1/jobs/{rejected['id']}/reject", json={})
    db_path = settings.data_dir / "traid.db"
    before = _digest(db_path)

    result = evaluate(db_path)
    write_report(result, tmp_path / "report")

    criteria = {c["name"]: c for c in result["criteria"]}
    assert result["rendered"] >= 4
    assert criteria["Acceptance without fine-tuning"]["value"] == "75% of 4"
    assert criteria["OCR read-back correctness"]["met"] is None  # fewer than 100 edits
    assert criteria["Stability"]["met"] is True
    assert (tmp_path / "report" / "showcase.html").read_text(encoding="utf-8").count("<tr>") == 6

    count = make_kit(settings.data_dir, tmp_path / "kit", pairs=10, seed=1)
    assert count == 3
    answers = json.loads((tmp_path / "kit" / "answers.json").read_text(encoding="utf-8"))
    assert {a["job_id"] for a in answers.values()} == set(accepted)
    assert sorted(p.name for p in (tmp_path / "kit").glob("pair-*.png")) == [
        "pair-01.png",
        "pair-02.png",
        "pair-03.png",
    ]

    # A viewer who always answers "left" is right exactly where the edit was on the left.
    sheet = tmp_path / "viewer1.csv"
    with sheet.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["pair", "edited_side (left/right)"])
        for pair_id in answers:
            writer.writerow([pair_id, "left"])
    scored = score(tmp_path / "kit", [sheet])
    expected = sum(a["edited"] == "left" for a in answers.values())
    assert scored["answers"] == 3 and scored["viewers"][0]["correct"] == expected

    assert _digest(db_path) == before  # the tools never write to the database
