"""In-process token buckets (API.md §6). Local single user: this guards against
runaway clients and scripts, not traffic, so memory is the right store."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import Request

from app.core.errors import TooManyRequests

UPLOADS_PER_MINUTE = 30


@dataclass
class TokenBucket:
    capacity: int
    per_seconds: float
    clock: Callable[[], float] = time.monotonic
    _tokens: dict[str, float] = field(default_factory=dict)
    _stamp: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def take(self, key: str) -> float:
        """Use one token; returns 0, or the seconds to wait when the bucket is empty."""
        rate = self.capacity / self.per_seconds
        with self._lock:
            now = self.clock()
            tokens = min(
                self.capacity,
                self._tokens.get(key, self.capacity) + (now - self._stamp.get(key, now)) * rate,
            )
            self._stamp[key] = now
            if tokens >= 1:
                self._tokens[key] = tokens - 1
                return 0.0
            self._tokens[key] = tokens
            return (1 - tokens) / rate


class RateLimited(TooManyRequests):
    def __init__(self, retry_after: float) -> None:
        super().__init__(
            "Too many uploads; wait a moment",
            details={"retry_after": math.ceil(retry_after)},
        )
        self.retry_after = math.ceil(retry_after)


def upload_limit(request: Request) -> None:
    """Dependency for upload endpoints: 30 requests per minute per client address."""
    bucket: TokenBucket = request.app.state.upload_bucket
    client = request.client.host if request.client else "local"
    wait = bucket.take(client)
    if wait > 0:
        raise RateLimited(wait)
