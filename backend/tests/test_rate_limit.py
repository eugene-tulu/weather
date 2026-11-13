from __future__ import annotations

import pytest

from rate_limit import CircuitBreaker, InMemoryRateLimiter, OutboundTokenBucket


def test_inbound_sliding_window():
    now = [0.0]
    limiter = InMemoryRateLimiter(2, window_seconds=60, time_source=lambda: now[0], max_keys=10)

    assert limiter.check("a") is None
    assert limiter.check("a") is None
    retry_after = limiter.check("a")
    assert retry_after is not None and retry_after > 0

    now[0] = 61.0
    assert limiter.check("a") is None


def test_inbound_bounded_keys():
    now = [0.0]
    limiter = InMemoryRateLimiter(10, window_seconds=60, time_source=lambda: now[0], max_keys=2)

    for key in ("a", "b", "c"):
        limiter.check(key)

    assert len(limiter._buckets) <= 2


async def test_outbound_waits_for_a_slot():
    now = [0.0]
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    bucket = OutboundTokenBucket(
        1,
        2,
        time_source=lambda: now[0],
        sleep=fake_sleep,
        max_wait_seconds=20,
    )

    await bucket.acquire()
    await bucket.acquire()

    assert sleeps
    assert now[0] >= 10.0


async def test_outbound_times_out():
    now = [0.0]

    async def fake_sleep(seconds: float) -> None:
        now[0] += seconds

    bucket = OutboundTokenBucket(
        1,
        2,
        time_source=lambda: now[0],
        sleep=fake_sleep,
        max_wait_seconds=0.1,
    )

    await bucket.acquire()
    with pytest.raises(TimeoutError):
        await bucket.acquire()


def test_circuit_breaker_opens_and_half_opens():
    now = [0.0]
    breaker = CircuitBreaker(
        failure_threshold=2,
        open_seconds=5,
        time_source=lambda: now[0],
    )

    breaker.record_failure()
    assert breaker.state == "closed"
    breaker.record_failure()
    assert breaker.state == "open"
    assert not breaker.allow()

    now[0] = 6.0
    assert breaker.allow()
    assert breaker.state == "half-open"
    breaker.record_success()
    assert breaker.state == "closed"
