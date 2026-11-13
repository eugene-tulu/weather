from __future__ import annotations

import threading
from collections import defaultdict


class Metrics:
    """Thread-safe counters exposed at /metrics."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def inc(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += value

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counters)
