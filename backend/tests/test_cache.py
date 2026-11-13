from __future__ import annotations

import asyncio

from cache import Cache


async def test_set_get_roundtrip(tmp_path):
    cache = Cache(str(tmp_path / "cache.duckdb"), ttl_seconds=600)
    try:
        await cache.set("a", {"x": 1})
        assert await cache.get("a") == {"x": 1}
        assert await cache.size() == 1
    finally:
        cache.close()


async def test_zero_ttl_expires(tmp_path):
    cache = Cache(str(tmp_path / "cache.duckdb"), ttl_seconds=0)
    try:
        await cache.set("a", {"x": 1})
        assert await cache.get("a") is None
    finally:
        cache.close()


async def test_prune_enforces_max_rows(tmp_path):
    cache = Cache(str(tmp_path / "cache.duckdb"), ttl_seconds=600, max_rows=2)
    try:
        for index in range(5):
            await cache.set(f"k{index}", {"index": index})
        await cache.prune()
        assert await cache.size() == 2
    finally:
        cache.close()


async def test_single_flight(tmp_path):
    cache = Cache(str(tmp_path / "cache.duckdb"), ttl_seconds=600)
    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return {"ok": True}

    try:
        results = await asyncio.gather(*(cache.get_or_fetch("same", fetch) for _ in range(5)))
        assert calls == 1
        assert all(value == {"ok": True} for value, _ in results)
    finally:
        cache.close()


async def test_prune_removes_expired(tmp_path):
    cache = Cache(str(tmp_path / "cache.duckdb"), ttl_seconds=0)
    try:
        await cache.set("a", {"x": 1})
        await cache.prune()
        assert await cache.size() == 0
    finally:
        cache.close()
