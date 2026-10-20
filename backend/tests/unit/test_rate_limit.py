import pytest

from app.core.rate_limit import TokenBucket


def test_bucket_allows_a_burst_then_refills() -> None:
    now = [0.0]
    bucket = TokenBucket(capacity=3, per_seconds=60.0, clock=lambda: now[0])

    assert [bucket.take("a") for _ in range(3)] == [0.0, 0.0, 0.0]
    assert bucket.take("a") == pytest.approx(20.0)  # one token per 20 s
    assert bucket.take("b") == 0.0  # separate clients

    now[0] = 20.0
    assert bucket.take("a") == 0.0
