from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import create_app
from config import Settings


def make_settings(tmp_path: Path, **overrides) -> Settings:
    settings = Settings(
        allowed_origins=("http://localhost:3000",),
        cache_db_path=str(tmp_path / "cache.duckdb"),
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


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client
