"""Opaque keyset cursors for list endpoints (API.md §1.5).

Lists are ordered `created_at DESC, id DESC`; a cursor encodes the last row's
(created_at, id). Clients must treat it as opaque.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime

from app.core.clock import isoformat_utc
from app.core.errors import ValidationFailed

DEFAULT_LIMIT = 25
MAX_LIMIT = 100


@dataclass(frozen=True)
class Cursor:
    created_at: datetime
    id: str


def encode_cursor(created_at: datetime, row_id: str) -> str:
    raw = json.dumps([isoformat_utc(created_at), row_id], separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


_INVALID_CURSOR_DETAILS = {
    "fields": [
        {
            "path": "cursor",
            "code": "VALIDATION_FAILED",
            "message": "Use meta.next_cursor from a previous page",
        }
    ]
}


def encode_offset(offset: int) -> str:
    """Opaque cursor for lists sorted by something other than creation time."""
    return base64.urlsafe_b64encode(f"o:{offset}".encode()).decode().rstrip("=")


def decode_offset(value: str) -> int:
    try:
        raw = base64.urlsafe_b64decode((value + "=" * (-len(value) % 4)).encode()).decode()
        prefix, number = raw.split(":", 1)
        offset = int(number)
        if prefix != "o" or offset < 0:
            raise ValueError
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise ValidationFailed("Invalid cursor", details=_INVALID_CURSOR_DETAILS) from exc
    return offset


def decode_cursor(value: str) -> Cursor:
    try:
        padded = value + "=" * (-len(value) % 4)
        created_at_text, row_id = json.loads(base64.urlsafe_b64decode(padded.encode()))
        created_at = datetime.fromisoformat(str(created_at_text).replace("Z", "+00:00"))
        if created_at.tzinfo is None or not isinstance(row_id, str):
            raise ValueError
    except (binascii.Error, ValueError, TypeError, UnicodeDecodeError) as exc:
        raise ValidationFailed(
            "Invalid cursor",
            details={
                "fields": [
                    {
                        "path": "cursor",
                        "code": "VALIDATION_FAILED",
                        "message": "Use meta.next_cursor from a previous page",
                    }
                ]
            },
        ) from exc
    return Cursor(created_at, row_id)
