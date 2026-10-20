"""Single source of 'now' and of the timestamp text format, so everything is UTC."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def isoformat_utc(value: datetime) -> str:
    """`2026-10-20T14:03:11.123Z`: UTC, millisecond precision (DATABASE.md §2, API.md §1.1)."""
    if value.tzinfo is None:
        raise ValueError("Naive datetimes are not allowed; use app.core.clock.utcnow()")
    utc = value.astimezone(UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"
