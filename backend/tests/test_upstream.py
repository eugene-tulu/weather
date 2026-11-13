from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import httpx
import pytest
import respx

from config import Settings
from metrics import Metrics
from rate_limit import CircuitBreaker, OutboundTokenBucket
from upstream import (
    UpstreamClient,
    UpstreamError,
    http_from_upstream,
    parse_retry_after,
)


def make_settings(tmp_path: Path, **overrides) -> Settings:
    settings = Settings(
        allowed_origins=("http://localhost:3000",),
        cache_db_path=str(tmp_path / "unused.duckdb"),
        cache_ttl_seconds=600,
        cache_max_rows=100,
        rate_limit_per_minute=1000,
        outbound_per_10s=1000,
        outbound_per_60s=1000,
        outbound_max_wait_seconds=0.01,
        upstream_base="https://api.dynamical.org/v1",
        geocode_url="https://geocoding-api.open-meteo.com/v1/search",
        upstream_timeout_seconds=1.0,
        connect_timeout_seconds=1.0,
        max_retries=0,
        circuit_failure_threshold=100,
        circuit_open_seconds=1.0,
        trust_proxy_headers=True,
        environment="test",
    )
    return replace(settings, **overrides) if overrides else settings


async def make_client(tmp_path: Path, **overrides) -> UpstreamClient:
    settings = make_settings(tmp_path, **overrides)
    outbound = OutboundTokenBucket(
        settings.outbound_per_10s,
        settings.outbound_per_60s,
        max_wait_seconds=settings.outbound_max_wait_seconds,
    )
    breaker = CircuitBreaker(
        settings.circuit_failure_threshold,
        settings.circuit_open_seconds,
    )
    client = UpstreamClient(settings, outbound, breaker, Metrics())
    await client.start()
    return client


async def test_429_raises_with_retry_after(tmp_path):
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post("https://api.dynamical.org/v1/forecasts").mock(
            return_value=httpx.Response(
                429,
                headers={"retry-after": "2"},
                json={"detail": "slow down"},
            )
        )
        client = await make_client(tmp_path, max_retries=0)
        try:
            with pytest.raises(UpstreamError) as exc_info:
                await client.post_json("/forecasts", {"queries": []})
            assert exc_info.value.status_code == 429
            assert exc_info.value.retry_after == 2
            assert route.call_count == 1
        finally:
            await client.stop()


async def test_503_is_retried_then_succeeds(tmp_path):
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post("https://api.dynamical.org/v1/forecasts").mock(
            side_effect=[
                httpx.Response(503, json={"detail": "busy"}),
                httpx.Response(200, json={"ok": True}),
            ]
        )
        client = await make_client(tmp_path, max_retries=1)
        try:
            data = await client.post_json("/forecasts", {"queries": []})
            assert data == {"ok": True}
            assert route.call_count == 2
        finally:
            await client.stop()


async def test_circuit_opens_after_repeated_failures(tmp_path):
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post("https://api.dynamical.org/v1/forecasts").mock(
            return_value=httpx.Response(500, json={"detail": "boom"})
        )
        client = await make_client(tmp_path, max_retries=0, circuit_failure_threshold=1)
        try:
            with pytest.raises(UpstreamError) as first:
                await client.post_json("/forecasts", {"queries": []})
            assert first.value.status_code == 502

            with pytest.raises(UpstreamError) as second:
                await client.post_json("/forecasts", {"queries": []})
            assert second.value.status_code == 503
            assert route.call_count == 1
        finally:
            await client.stop()


async def test_transport_error_maps_to_502(tmp_path):
    with respx.mock(assert_all_called=False) as mock:
        mock.post("https://api.dynamical.org/v1/forecasts").mock(
            side_effect=httpx.ConnectError("boom")
        )
        client = await make_client(tmp_path, max_retries=0)
        try:
            with pytest.raises(UpstreamError) as exc_info:
                await client.post_json("/forecasts", {"queries": []})
            assert exc_info.value.status_code == 502
        finally:
            await client.stop()


def test_http_mapping():
    with_headers = http_from_upstream(UpstreamError(429, "slow down", retry_after=2))
    assert with_headers.status_code == 429
    assert with_headers.headers["retry-after"] == "2"

    assert http_from_upstream(UpstreamError(503, "busy")).status_code == 503
    assert http_from_upstream(UpstreamError(422, "bad")).status_code == 400
    assert http_from_upstream(UpstreamError(500, "boom")).status_code == 502


def test_parse_retry_after():
    assert parse_retry_after("2") == 2
    assert parse_retry_after("not-a-date") is None
    assert parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT") == 0.0
