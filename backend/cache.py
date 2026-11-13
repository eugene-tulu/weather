from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import duckdb


class Cache:
    """Small DuckDB response cache with TTL, LRU cap, and single-flight reads."""

    def __init__(self, path: str, ttl_seconds: int, max_rows: int = 10_000) -> None:
        self.path = path
        self.ttl_seconds = ttl_seconds
        self.max_rows = max_rows
        self.hits = 0
        self.misses = 0

        self._lock = threading.Lock()
        self._locks_guard = asyncio.Lock()
        self._locks: dict[str, asyncio.Lock] = {}
        self._insert_count = 0

        if path != ":memory:":
            Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

        self._db = duckdb.connect(path)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key VARCHAR PRIMARY KEY,
                payload JSON,
                ts DOUBLE,
                expires_at DOUBLE
            )
            """)
        columns = {row[1] for row in self._query_all("PRAGMA table_info('cache')")}
        if "expires_at" not in columns:
            self._db.execute("ALTER TABLE cache ADD COLUMN expires_at DOUBLE")
            self._db.execute("UPDATE cache SET expires_at = ts + ?", [self.ttl_seconds])
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_cache_expires_at ON cache(expires_at)")
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_cache_ts ON cache(ts)")

    def _execute(self, query: str, params: list[Any] | None = None) -> None:
        with self._lock:
            self._db.execute(query, params or [])

    def _query_one(self, query: str, params: list[Any] | None = None) -> Any | None:
        with self._lock:
            return self._db.execute(query, params or []).fetchone()

    def _query_all(self, query: str, params: list[Any] | None = None) -> list[Any]:
        with self._lock:
            return self._db.execute(query, params or []).fetchall()

    async def get(self, key: str) -> Any | None:
        def work() -> Any | None:
            row = self._query_one("SELECT payload, expires_at FROM cache WHERE key = ?", [key])
            if row is None:
                return None
            payload, expires_at = row
            if expires_at is None or float(expires_at) <= time.time():
                self._execute("DELETE FROM cache WHERE key = ?", [key])
                return None
            if isinstance(payload, (str, bytes, bytearray)):
                return json.loads(payload)
            return payload

        return await asyncio.to_thread(work)

    async def set(self, key: str, payload: Any, ttl_seconds: int | None = None) -> None:
        ttl = self.ttl_seconds if ttl_seconds is None else ttl_seconds
        now = time.time()
        body = json.dumps(payload, separators=(",", ":"))

        def work() -> None:
            self._execute(
                "INSERT OR REPLACE INTO cache (key, payload, ts, expires_at) "
                "VALUES (?, ?, ?, ?)",
                [key, body, now, now + ttl],
            )
            self._insert_count += 1
            if self._insert_count >= 100:
                self._insert_count = 0
                self._prune_sync(now)

        await asyncio.to_thread(work)

    async def get_or_fetch(
        self,
        key: str,
        fetcher: Callable[[], Awaitable[Any]],
        ttl_seconds: int | None = None,
    ) -> tuple[Any, bool]:
        cached = await self.get(key)
        if cached is not None:
            self.hits += 1
            return cached, True

        lock = await self._lock_for(key)
        async with lock:
            cached = await self.get(key)
            if cached is not None:
                self.hits += 1
                return cached, True

            self.misses += 1
            value = await fetcher()
            await self.set(key, value, ttl_seconds)
            return value, False

    async def _lock_for(self, key: str) -> asyncio.Lock:
        async with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
            return lock

    def _prune_sync(self, now: float) -> None:
        self._execute("DELETE FROM cache WHERE expires_at <= ?", [now])
        count = int(self._query_one("SELECT count(*) FROM cache")[0])
        if count > self.max_rows:
            self._execute(
                "DELETE FROM cache WHERE key IN " "(SELECT key FROM cache ORDER BY ts ASC LIMIT ?)",
                [count - self.max_rows],
            )

    async def prune(self) -> None:
        await asyncio.to_thread(self._prune_sync, time.time())

    async def size(self) -> int:
        def work() -> int:
            return int(self._query_one("SELECT count(*) FROM cache")[0])

        return await asyncio.to_thread(work)

    async def ping(self) -> None:
        await asyncio.to_thread(lambda: self._query_one("SELECT 1"))

    def close(self) -> None:
        try:
            self._db.close()
        except Exception:
            pass
