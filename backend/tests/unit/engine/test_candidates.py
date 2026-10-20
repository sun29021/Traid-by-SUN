import numpy as np

from app.engine.candidates import score_regions
from app.engine.types import Region

CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-/# "


def _region(text: str, x: float, y: float, confidence: float = 0.95) -> Region:
    quad = np.array([[x, y], [x + 200, y], [x + 200, y + 40], [x, y + 40]], dtype=np.float32)
    return Region(quad=quad, text=text, confidence=confidence)


def test_pattern_match_wins_and_ids_follow_rank() -> None:
    regions = [_region("TOTAL 12.50", 10, 10), _region("A7-204913", 300, 300)]

    scored = score_regions(regions, (1000, 800), charset=CHARSET, pattern=r"[A-Z0-9]{2}-\d{6}")

    assert [s.region.text for s in scored] == ["A7-204913", "TOTAL 12.50"]
    assert [s.id for s in scored] == ["r1", "r2"]
    assert "pattern" in scored[0].reasons and "pattern" not in scored[1].reasons


def test_learned_position_breaks_ties() -> None:
    near = _region("B8-551067", 700, 600)
    far = _region("C9-000001", 50, 50)
    typical = {"count": 5, "cx": 0.8, "cy": 0.78, "sx": 0.05, "sy": 0.05}

    scored = score_regions(
        [far, near], (1000, 800), charset=CHARSET, pattern=None, typical_region=typical
    )

    assert scored[0].region is near
    assert "position" in scored[0].reasons


def test_without_pattern_or_history_charset_and_confidence_decide() -> None:
    clean = _region("XZ-0071", 0, 0, confidence=0.9)
    noisy = _region("x?z", 0, 100, confidence=0.99)

    scored = score_regions([noisy, clean], (500, 500), charset=CHARSET, pattern=None)

    assert scored[0].region is clean
    assert scored[0].to_dict()["quad"][0] == [0.0, 0.0]
