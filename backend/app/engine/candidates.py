"""Which detected text line is the token to replace (PRD FR-E02, ARCHITECTURE §10.1).

Weighted score of: the profile's token pattern, a Gaussian prior around where this
profile's tokens usually sit (learned from accepted jobs), the share of characters in
the profile's charset, and OCR confidence. Every score lists its reasons so the UI can
say why a region was preselected.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.engine.types import Region

WEIGHTS = {"pattern": 0.45, "position": 0.25, "charset": 0.15, "confidence": 0.15}


@dataclass(frozen=True)
class ScoredRegion:
    id: str
    region: Region
    score: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "quad": [[round(float(x), 1), round(float(y), 1)] for x, y in self.region.quad],
            "text": self.region.text,
            "confidence": round(float(self.region.confidence), 4),
            "score": round(self.score, 4),
            "reasons": list(self.reasons),
            "char_positions": [round(float(p), 4) for p in self.region.char_positions],
        }


def _position_score(
    region: Region, image_size: tuple[int, int], typical: Mapping[str, Any] | None
) -> float | None:
    """exp(-d²/2) of the region centre against the learned mean/std (normalised coords)."""
    if not typical or not typical.get("count"):
        return None
    width, height = image_size
    centre = region.quad.mean(axis=0) / np.array([width, height], dtype=np.float32)
    mean = np.array([typical.get("cx", 0.5), typical.get("cy", 0.5)], dtype=np.float64)
    std = np.maximum(np.array([typical.get("sx", 0.2), typical.get("sy", 0.2)]), 0.03)
    d2 = float((((centre - mean) / std) ** 2).sum())
    return math.exp(-0.5 * d2)


def score_regions(
    regions: Sequence[Region],
    image_size: tuple[int, int],
    *,
    charset: str,
    pattern: str | None,
    typical_region: Mapping[str, Any] | None = None,
) -> list[ScoredRegion]:
    """Regions best first, with ids r1, r2, … in that order."""
    compiled = re.compile(pattern) if pattern else None
    allowed = set(charset)
    scored = []
    for region in regions:
        text = region.text
        parts: dict[str, float] = {}
        reasons: list[str] = []
        if compiled is not None:
            parts["pattern"] = 1.0 if compiled.fullmatch(text) else 0.0
            if parts["pattern"]:
                reasons.append("pattern")
        position = _position_score(region, image_size, typical_region)
        if position is not None:
            parts["position"] = position
            if position > 0.5:
                reasons.append("position")
        letters = [c for c in text if c != " "]
        parts["charset"] = sum(c in allowed for c in letters) / len(letters) if letters else 0.0
        if parts["charset"] == 1.0:
            reasons.append("charset")
        parts["confidence"] = float(region.confidence)
        if region.confidence >= 0.9:
            reasons.append("confidence")
        total_weight = sum(WEIGHTS[name] for name in parts)
        score = sum(WEIGHTS[name] * value for name, value in parts.items()) / total_weight
        scored.append((score, region, tuple(reasons)))
    scored.sort(key=lambda item: -item[0])
    return [
        ScoredRegion(id=f"r{index + 1}", region=region, score=score, reasons=reasons)
        for index, (score, region, reasons) in enumerate(scored)
    ]
