"""Text detection and recognition with PP-OCRv4 on ONNX Runtime (PRD FR-E01).

Detection (DB): probability map -> binary map -> min-area rectangles, expanded by the
DB "unclip" distance (area * ratio / perimeter). For rectangles that offset equals
growing both sides by 2*d, so no polygon-clipping library is needed.

Recognition (CTC): each line is rectified to a 48 px high strip; greedy CTC decoding
also yields where each character sits along the strip (`Region.char_positions`),
which character segmentation uses later.

Inputs are RGB; the PaddleOCR models expect BGR channel order.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import cv2
import numpy as np
from numpy.typing import NDArray

from app.engine.geometry import order_quad, quad_size, rectify
from app.engine.models import ModelRegistry
from app.engine.types import Quad, Region, RGBImage

DET_MODEL = "ppocr-det"
REC_MODEL = "ppocr-rec"

_DET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_DET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
REC_HEIGHT = 48


class TextDetector(Protocol):
    def detect(self, image: RGBImage) -> list[Region]: ...


@dataclass(frozen=True)
class DetectorConfig:
    max_side: int = 1920  # downscale big photos to this (small tokens stay readable)
    min_side: int = 960  # upscale small crops so text is large enough for DB
    bin_threshold: float = 0.3
    box_threshold: float = 0.5
    unclip_ratio: float = 1.6
    min_box_side: float = 3.0
    max_candidates: int = 1000
    min_confidence: float = 0.3


class PaddleOcr:
    """`TextDetector` backed by the PP-OCR ONNX models in the registry."""

    def __init__(self, registry: ModelRegistry, config: DetectorConfig | None = None) -> None:
        self.registry = registry
        self.config = config or DetectorConfig()
        self._charset: list[str] | None = None

    # ------------------------------------------------------------ public

    def detect(self, image: RGBImage) -> list[Region]:
        bgr = np.ascontiguousarray(image[..., ::-1])
        regions: list[Region] = []
        for quad in self.detect_boxes(bgr):
            region = self.recognize(bgr, quad)
            if region is not None and region.confidence >= self.config.min_confidence:
                regions.append(region)
        return regions

    def detect_boxes(self, bgr: NDArray[np.uint8]) -> list[Quad]:
        resized, (scale_y, scale_x) = self._resize_for_detection(bgr)
        tensor = ((resized.astype(np.float32) / 255.0 - _DET_MEAN) / _DET_STD).transpose(2, 0, 1)
        session = self.registry.session(DET_MODEL)
        prob = session.run({"x": tensor[None].astype(np.float32)})[0][0, 0]
        quads = self._boxes_from_probability(prob)
        height, width = bgr.shape[:2]
        scaled = []
        scale = np.array([scale_x, scale_y], dtype=np.float32)
        for quad in quads:
            original = np.asarray(quad / scale, dtype=np.float32)
            original[:, 0] = np.clip(original[:, 0], 0, width - 1)
            original[:, 1] = np.clip(original[:, 1], 0, height - 1)
            scaled.append(order_quad(original))
        # Reading order: top to bottom, then left to right within a line.
        scaled.sort(key=lambda q: (round(float(q[:, 1].mean()) / 10), float(q[:, 0].min())))
        return scaled

    def recognize(self, bgr: NDArray[np.uint8], quad: Quad) -> Region | None:
        width, height = quad_size(quad)
        strip = rectify(bgr, quad, (width, height)).patch
        vertical = height >= 1.5 * width
        if vertical:
            strip = np.asarray(cv2.rotate(strip, cv2.ROTATE_90_COUNTERCLOCKWISE), dtype=np.uint8)
        h, w = strip.shape[:2]
        rec_width = max(REC_HEIGHT // 4, math.ceil(REC_HEIGHT * w / h))
        resized = cv2.resize(strip, (rec_width, REC_HEIGHT), interpolation=cv2.INTER_LINEAR)
        tensor = ((resized.astype(np.float32) / 255.0 - 0.5) / 0.5).transpose(2, 0, 1)
        session = self.registry.session(REC_MODEL)
        probs = session.run({"x": tensor[None].astype(np.float32)})[0][0]  # (T, classes)
        text, confidences, positions = self._ctc_decode(probs, self._get_charset())
        if not text.strip():
            return None
        return Region(
            quad=quad,
            text=text,
            confidence=float(np.mean(confidences)),
            char_positions=tuple(positions),
            char_confidences=tuple(confidences),
            vertical=vertical,
        )

    # ------------------------------------------------------------ detection helpers

    def _resize_for_detection(
        self, bgr: NDArray[np.uint8]
    ) -> tuple[NDArray[np.uint8], tuple[float, float]]:
        height, width = bgr.shape[:2]
        longest = max(height, width)
        ratio = 1.0
        if longest > self.config.max_side:
            ratio = self.config.max_side / longest
        elif longest < self.config.min_side:
            ratio = self.config.min_side / longest
        new_h = max(32, round(height * ratio / 32) * 32)
        new_w = max(32, round(width * ratio / 32) * 32)
        resized = cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        return np.asarray(resized, dtype=np.uint8), (new_h / height, new_w / width)

    def _boxes_from_probability(self, prob: NDArray[np.float32]) -> list[Quad]:
        config = self.config
        bitmap = (prob > config.bin_threshold).astype(np.uint8) * 255
        contours, _ = cv2.findContours(bitmap, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        quads: list[Quad] = []
        for contour in contours[: config.max_candidates]:
            (cx, cy), (w, h), angle = cv2.minAreaRect(contour)
            if min(w, h) < config.min_box_side:
                continue
            box = np.asarray(cv2.boxPoints(((cx, cy), (w, h), angle)), dtype=np.float32)
            if self._box_score(prob, box) < config.box_threshold:
                continue
            distance = (w * h) * config.unclip_ratio / (2 * (w + h))
            grown = ((cx, cy), (w + 2 * distance, h + 2 * distance), angle)
            if min(grown[1]) < config.min_box_side + 2:
                continue
            quads.append(cv2.boxPoints(grown).astype(np.float32))
        return quads

    @staticmethod
    def _box_score(prob: NDArray[np.float32], box: NDArray[np.float32]) -> float:
        """Mean probability inside the box (DB 'fast' score)."""
        h, w = prob.shape
        x0 = int(np.clip(np.floor(box[:, 0].min()), 0, w - 1))
        x1 = int(np.clip(np.ceil(box[:, 0].max()), 0, w - 1))
        y0 = int(np.clip(np.floor(box[:, 1].min()), 0, h - 1))
        y1 = int(np.clip(np.ceil(box[:, 1].max()), 0, h - 1))
        mask = np.zeros((y1 - y0 + 1, x1 - x0 + 1), dtype=np.uint8)
        cv2.fillPoly(mask, [(box - [x0, y0]).astype(np.int32)], 1)
        return float(cv2.mean(prob[y0 : y1 + 1, x0 : x1 + 1], mask)[0])

    # ------------------------------------------------------------ recognition helpers

    def _get_charset(self) -> list[str]:
        """CTC classes: blank, the model's embedded dictionary, then space."""
        if self._charset is None:
            meta = self.registry.session(REC_MODEL).metadata()
            dictionary = meta.get("character", "").split("\n")
            self._charset = ["", *dictionary, " "]
        return self._charset

    @staticmethod
    def _ctc_decode(
        probs: NDArray[np.float32], charset: Sequence[str]
    ) -> tuple[str, list[float], list[float]]:
        """Greedy CTC: collapse repeats, drop blanks; position = centre of each run."""
        indices = probs.argmax(axis=1)
        scores = probs.max(axis=1)
        steps = len(indices)
        chars: list[str] = []
        confidences: list[float] = []
        positions: list[float] = []
        run_start = 0
        for t in range(steps + 1):
            boundary = t == steps or (t > 0 and indices[t] != indices[t - 1])
            if t > 0 and boundary:
                index = int(indices[t - 1])
                if index != 0 and index < len(charset):
                    chars.append(charset[index])
                    confidences.append(float(scores[run_start:t].mean()))
                    positions.append(((run_start + t) / 2) / steps)
                run_start = t
        return "".join(chars), confidences, positions


class FakeDetector:
    """Returns preset regions; lets service/API tests run without model files."""

    def __init__(self, regions: list[Region]) -> None:
        self.regions = regions

    def detect(self, image: RGBImage) -> list[Region]:
        return list(self.regions)
