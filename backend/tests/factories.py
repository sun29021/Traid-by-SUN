"""Shared test data builders."""

import io

import numpy as np
from PIL import Image

from app.db.engine import Database
from app.db.models import User


def make_user(db: Database, username: str) -> str:
    with db.session() as session:
        user = User(username=username, display_name=username.title(), password_hash="x")
        session.add(user)
        session.flush()
        return user.id


def png_bytes(rgb: "np.ndarray") -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(rgb, "RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def image_bytes(
    fmt: str = "PNG",
    size: tuple[int, int] = (32, 16),
    mode: str = "RGB",
    **save_options: object,
) -> bytes:
    color: int | tuple[int, ...] = 128 if mode in ("L", "P", "I;16") else (200, 120, 40)
    if mode == "RGBA":
        color = (200, 120, 40, 255)
    buffer = io.BytesIO()
    Image.new(mode, size, color).save(buffer, format=fmt, **save_options)
    return buffer.getvalue()
