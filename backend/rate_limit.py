from __future__ import annotations

import asyncio
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable


class InMemoryRateLimiter:
    """Bounded sliding-window limiter for inbound client IPs."""

    def __init__(
        self,
        limit: int,
        window_seconds: float = 60.0,
        *,
        time_source: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
    ) -> None:
        self.limit = limit
        self.window = window_seconds
        self._time = time_source
        self._max_keys = max_keys
        self._buckets: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def check(self, key: str) -> float | None:
        """Return seconds to wait if the caller is over the limit, else None."""

        now = self._time()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = deque()
                self._buckets[key] = bucket

            while bucket and now - bucket[0] >= self.window:
                bucket.popleft()

            if len(bucket) >= self.limit:
                return max(0.0, self.window - (now - bucket[0]))

            bucket.append(now)
            self._buckets.move_to_end(key)
            if len(self._buckets) > self._max_keys:
                self._sweep(now)
            return None

    def _sweep(self, now: float) -> None:
        for key in list(self._buckets):
            bucket = self._buckets[key]
            while bucket and now - bucket[0] >= self.window:
                bucket.popleft()
            if not bucket:
                del self._buckets[key]
        while len(self._buckets) > self._max_keys:
            self._buckets.popitem(last=False)


class OutboundTokenBucket:
    """Process-wide sliding-window limiter for calls to the upstream API.

    The provider enforces separate 10-second and 60-second budgets. Every
    upstream request must pass through ``acquire`` before it is sent.
    """

    def __init__(
        self,
        limit_10s: int,
        limit_60s: int,
        *,
        time_source: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        max_wait_seconds: float = 5.0,
    ) -> None:
        if limit_10s <= 0 or limit_60s <= 0:
            raise ValueError("outbound limits must be positive")
        self._limits = ((limit_10s, 10.0), (limit_60s, 60.0))
        self._time = time_source
        self._sleep = sleep
        self._max_wait = max_wait_seconds
        self._events: deque[float] = deque()
        self._lock = asyncio.Lock()

    @property
    def queued(self) -> int:
        return len(self._events)

    async def acquire(self) -> None:
        deadline = self._time() + self._max_wait

        while True:
            async with self._lock:
                now = self._time()
                self._evict(now)

                wait = self._wait_time(now)
                if wait <= 0:
                    self._events.append(now)
                    return

            remaining = deadline - self._time()
            if remaining <= 0:
                raise TimeoutError("outbound rate limit wait exceeded")

            await self._sleep(min(wait, remaining))

    def _evict(self, now: float) -> None:
        horizon = max(window for _, window in self._limits)
        while self._events and now - self._events[0] >= horizon:
            self._events.popleft()

    def _wait_time(self, now: float) -> float:
        wait = 0.0
        for limit, window in self._limits:
            in_window = [stamp for stamp in self._events if now - stamp < window]
            if len(in_window) < limit:
                continue
            oldest = in_window[0]
            wait = max(wait, window - (now - oldest) + 0.001)
        return wait


class CircuitBreaker:
    """Small failure circuit for an unhealthy upstream dependency."""

    def __init__(
        self,
        failure_threshold: int = 5,
        open_seconds: float = 30.0,
        *,
        time_source: Callable[[], float] = time.monotonic,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.open_seconds = open_seconds
        self._time = time_source
        self._state = "closed"
        self._failures = 0
        self._opened_at = 0.0

    @property
    def state(self) -> str:
        return self._state

    @property
    def failures(self) -> int:
        return self._failures

    def allow(self) -> bool:
        if self._state != "open":
            return True
        if self._time() - self._opened_at >= self.open_seconds:
            self._state = "half-open"
            return True
        return False

    def record_success(self) -> None:
        self._state = "closed"
        self._failures = 0
        self._opened_at = 0.0

    def record_failure(self) -> None:
        self._failures += 1
        if self._state == "half-open" or self._failures >= self.failure_threshold:
            self._state = "open"
            self._opened_at = self._time()
