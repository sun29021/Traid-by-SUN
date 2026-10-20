"""Synthetic token images with known ground truth (IMPLEMENTATION_PLAN.md task 4.1).

Real reference photos arrive late in the project, so engine stages are built and
tested on these. Each fixture is deterministic for a given seed and records exactly
where the text is, so tests can measure errors in pixels.

Surfaces (PRD FR-E15):
  print       dark ink on paper
  paint       painted lettering with ragged edges on a plaster wall
  laser_mark  colour-change marking on brushed metal or plastic
  engraved    cut-in text with directional highlights/shadows

Run `python tests/fixtures/generate.py <out_dir>` (from backend/) to write samples.
"""

from __future__ import annotations

import io
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw, ImageFont

Surface = Literal["print", "paint", "laser_mark", "engraved"]
SURFACES: tuple[Surface, ...] = ("print", "paint", "laser_mark", "engraved")

F32 = NDArray[np.float32]


@dataclass(frozen=True, eq=False)
class TokenFixture:
    image: NDArray[np.uint8]  # RGB
    text: str
    quad: NDArray[np.float32]  # text box corners TL, TR, BR, BL in image px
    surface: Surface
    background: str
    blur_sigma: float
    noise_sigma: float
    jpeg_quality: int | None
    seed: int


# ---------------------------------------------------------- textures (float32 0-255, H x W x 3)


def _noise(rng: np.random.Generator, shape: tuple[int, int], sigma: float) -> F32:
    return rng.normal(0.0, sigma, shape).astype(np.float32)


def _low_freq(rng: np.random.Generator, shape: tuple[int, int], scale: float, amp: float) -> F32:
    small = rng.normal(0.0, 1.0, (max(2, int(shape[0] / scale)), max(2, int(shape[1] / scale))))
    big = cv2.resize(small.astype(np.float32), (shape[1], shape[0]), interpolation=cv2.INTER_CUBIC)
    return (big / (np.abs(big).max() + 1e-6) * amp).astype(np.float32)


def _tint(gray: F32, color: tuple[float, float, float]) -> F32:
    base = np.array(color, dtype=np.float32) / 128.0
    return (gray[..., None] * base[None, None, :]).astype(np.float32)


def _texture(rng: np.random.Generator, kind: str, shape: tuple[int, int]) -> F32:
    h, w = shape
    if kind == "paper":
        gray = 228 + _low_freq(rng, shape, 120, 6) + _noise(rng, shape, 3.0)
        return _tint(gray, (130, 128, 122))
    if kind == "plaster":
        gray = 182 + _low_freq(rng, shape, 40, 14) + _low_freq(rng, shape, 8, 6)
        gray += _noise(rng, shape, 6.0)
        return _tint(gray, (130, 127, 121))
    if kind == "metal":
        streaks = rng.normal(0.0, 1.0, (h, w)).astype(np.float32)
        streaks = cv2.blur(streaks, (61, 1)) * 18  # brushed along x
        gray = 150 + streaks + _low_freq(rng, shape, 90, 12) + _noise(rng, shape, 2.0)
        return _tint(gray, (128, 129, 132))
    if kind == "plastic":
        gray = 90 + _low_freq(rng, shape, 150, 8) + _noise(rng, shape, 2.5)
        hue = [(128, 128, 150), (150, 128, 120), (120, 140, 125)][int(rng.integers(0, 3))]
        return _tint(gray, (float(hue[0]), float(hue[1]), float(hue[2])))
    if kind == "table":
        gray = 75 + _low_freq(rng, shape, 60, 10) + _noise(rng, shape, 3.0)
        return _tint(gray, (138, 126, 112))
    raise ValueError(kind)


# ---------------------------------------------------------------- text


def _render_text_mask(
    text: str, font_px: int, margin: int
) -> tuple[F32, tuple[int, int, int, int]]:
    """0..1 text mask on a plane with `margin` px around the ink, plus the ink box."""
    font = ImageFont.load_default(size=font_px)
    left, top, right, bottom = font.getbbox(text)
    width, height = right - left + 2 * margin, bottom - top + 2 * margin
    plane = Image.new("L", (width, height), 0)
    ImageDraw.Draw(plane).text((margin - left, margin - top), text, fill=255, font=font)
    box = (margin, margin, margin + right - left, margin + bottom - top)
    return np.asarray(plane, dtype=np.float32) / 255.0, box


def _apply_surface(rng: np.random.Generator, surface: Surface, mask: F32) -> tuple[F32, str]:
    """Composite the text mask onto a surface texture. Returns (plane RGB, background name)."""
    shape = mask.shape[:2]
    if surface == "print":
        bg = _texture(rng, "paper", (shape[0], shape[1]))
        density = np.clip(0.88 + _noise(rng, shape, 0.05), 0, 1)
        ink = np.array([28, 30, 38], dtype=np.float32)
        alpha = (mask * density)[..., None]
        return bg * (1 - alpha) + ink * alpha, "paper"
    if surface == "paint":
        bg = _texture(rng, "plaster", (shape[0], shape[1]))
        rough = cv2.GaussianBlur(mask, (0, 0), 1.2) + _low_freq(rng, shape, 3, 0.25)
        alpha = np.clip((rough - 0.35) * 3.0, 0, 1)[..., None]
        paint = np.array(
            [[150, 32, 30], [20, 22, 26], [24, 60, 140]][int(rng.integers(0, 3))], np.float32
        )
        return bg * (1 - alpha) + paint * alpha, "plaster"
    if surface == "laser_mark":
        kind = "metal" if rng.random() < 0.6 else "plastic"
        bg = _texture(rng, kind, (shape[0], shape[1]))
        alpha = (cv2.GaussianBlur(mask, (0, 0), 0.6) * 0.7)[..., None]
        mark = np.array([0.35, 0.33, 0.30], dtype=np.float32)  # darkening with a warm tint
        return bg * (1 - alpha * (1 - mark)), kind
    # engraved: grooves lit from a random direction
    kind = "metal" if rng.random() < 0.7 else "plastic"
    bg = _texture(rng, kind, (shape[0], shape[1]))
    depth = cv2.GaussianBlur(mask, (0, 0), 1.6)
    gy, gx = np.gradient(-depth)
    angle = float(rng.uniform(0, 2 * np.pi))
    shading = 1.0 + 1.6 * (gx * np.cos(angle) + gy * np.sin(angle))
    groove = 1.0 - 0.25 * depth
    return bg * (shading * groove)[..., None], kind


# ---------------------------------------------------------------- composition


def make_token_image(
    text: str = "A7-204913",
    surface: Surface = "print",
    seed: int = 0,
    *,
    canvas: tuple[int, int] = (960, 640),
    font_px: int = 56,
    perspective: float = 0.06,
    rotation_deg: float | None = None,
    blur_sigma: float | None = None,
    noise_sigma: float | None = None,
    jpeg_quality: int | None = None,
) -> TokenFixture:
    """Render `text` on `surface`, place it in perspective on a canvas, degrade it."""
    rng = np.random.default_rng(seed)
    margin = font_px
    mask, (x0, y0, x1, y1) = _render_text_mask(text, font_px, margin)
    plane, background = _apply_surface(rng, surface, mask)
    ph, pw = mask.shape

    cw, ch = canvas
    out = _texture(rng, "table", (ch, cw))

    # Destination of the plane's corners: centred, rotated, scaled to fit, jittered.
    scale = min(0.75 * cw / pw, 0.6 * ch / ph, 1.6)
    angle = np.deg2rad(rotation_deg if rotation_deg is not None else rng.uniform(-6, 6))
    corners = np.array([[0, 0], [pw, 0], [pw, ph], [0, ph]], dtype=np.float32)
    centred = (corners - [pw / 2, ph / 2]) * scale
    rot = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]], np.float32)
    dst = centred @ rot.T + [cw / 2, ch / 2]
    dst += rng.uniform(-1, 1, (4, 2)).astype(np.float32) * perspective * pw * scale
    homography = cv2.getPerspectiveTransform(corners, dst.astype(np.float32))

    warped = cv2.warpPerspective(plane, homography, (cw, ch), flags=cv2.INTER_LINEAR)
    coverage = cv2.warpPerspective(np.ones((ph, pw), np.float32), homography, (cw, ch))[..., None]
    out = out * (1 - coverage) + warped * coverage

    # Lighting gradient across the scene, then optics and sensor.
    yy, xx = np.mgrid[0:ch, 0:cw].astype(np.float32)
    direction = rng.uniform(-1, 1, 2)
    light = 1.0 + 0.12 * ((xx / cw - 0.5) * direction[0] + (yy / ch - 0.5) * direction[1])
    out *= light[..., None]

    blur = float(blur_sigma if blur_sigma is not None else rng.uniform(0.4, 1.0))
    if blur > 0:
        out = cv2.GaussianBlur(out, (0, 0), blur)
    noise = float(noise_sigma if noise_sigma is not None else rng.uniform(1.0, 3.0))
    out = out + rng.normal(0, noise, out.shape).astype(np.float32)
    image = np.clip(out, 0, 255).astype(np.uint8)

    if jpeg_quality is not None:
        buffer = io.BytesIO()
        Image.fromarray(image, "RGB").save(buffer, "JPEG", quality=jpeg_quality)
        image = np.asarray(Image.open(io.BytesIO(buffer.getvalue())).convert("RGB")).copy()

    text_corners = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float32)
    quad = cv2.perspectiveTransform(text_corners.reshape(-1, 1, 2), homography).reshape(4, 2)
    return TokenFixture(
        image=image,
        text=text,
        quad=quad.astype(np.float32),
        surface=surface,
        background=background,
        blur_sigma=blur,
        noise_sigma=noise,
        jpeg_quality=jpeg_quality,
        seed=seed,
    )


def main() -> None:
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "fixture-samples")
    out_dir.mkdir(parents=True, exist_ok=True)
    for index, surface in enumerate(SURFACES):
        for seed in range(3):
            fixture = make_token_image(
                "A7-204913", surface, seed=index * 10 + seed, jpeg_quality=88
            )
            path = out_dir / f"{surface}-{seed}.png"
            preview = cv2.polylines(
                fixture.image.copy(),
                [np.round(fixture.quad).astype(np.int32)],
                True,
                (0, 220, 255),
                1,
            )
            Image.fromarray(preview).save(path)
            print(path)


if __name__ == "__main__":
    main()
