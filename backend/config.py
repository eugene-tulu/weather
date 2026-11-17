from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _origins(name: str, default: str) -> tuple[str, ...]:
    raw = os.getenv(name, default)
    return tuple(part.strip() for part in raw.split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    allowed_origins: tuple[str, ...]
    cache_db_path: str
    cache_ttl_seconds: int
    cache_max_rows: int
    rate_limit_per_minute: int
    outbound_per_10s: int
    outbound_per_60s: int
    outbound_max_wait_seconds: float
    upstream_base: str
    geocode_url: str
    upstream_timeout_seconds: float
    connect_timeout_seconds: float
    max_retries: int
    circuit_failure_threshold: int
    circuit_open_seconds: float
    trust_proxy_headers: bool
    environment: str
    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    redis_url: str = ""
    admin_token: str = ""
    require_auth: bool = False
    mcp_cache_db_path: str = "mcp-cache.duckdb"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8001
    otel_endpoint: str | None = None
    sentry_dsn: str | None = None
    quota_default: int = 100_000
    decision_products: tuple[str, ...] = (
        "noaa-gfs-forecast",
        "noaa-gefs-forecast-35-day",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        allowed_origins=_origins("ALLOWED_ORIGINS", "http://localhost:3000"),
        cache_db_path=os.getenv("CACHE_DB_PATH", "cache.duckdb"),
        cache_ttl_seconds=_int("CACHE_TTL_SECONDS", 600),
        cache_max_rows=_int("CACHE_MAX_ROWS", 10_000),
        rate_limit_per_minute=_int("RATE_LIMIT_PER_MINUTE", 60),
        outbound_per_10s=_int("OUTBOUND_RATE_PER_10S", 20),
        outbound_per_60s=_int("OUTBOUND_RATE_PER_60S", 250),
        outbound_max_wait_seconds=_float("OUTBOUND_MAX_WAIT_SECONDS", 5.0),
        upstream_base=os.getenv("UPSTREAM_BASE", "https://api.dynamical.org/v1").rstrip("/"),
        geocode_url=os.getenv("GEOCODE_URL", "https://geocoding-api.open-meteo.com/v1/search"),
        upstream_timeout_seconds=_float("UPSTREAM_TIMEOUT_SECONDS", 60.0),
        connect_timeout_seconds=_float("UPSTREAM_CONNECT_TIMEOUT_SECONDS", 5.0),
        max_retries=_int("UPSTREAM_MAX_RETRIES", 2),
        circuit_failure_threshold=_int("UPSTREAM_FAILURE_THRESHOLD", 5),
        circuit_open_seconds=_float("UPSTREAM_OPEN_SECONDS", 30.0),
        trust_proxy_headers=_bool("TRUST_PROXY_HEADERS", True),
        environment=os.getenv("ENVIRONMENT", "production"),
        database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/app.db"),
        redis_url=os.getenv("REDIS_URL", ""),
        admin_token=os.getenv("ADMIN_TOKEN", ""),
        require_auth=_bool("REQUIRE_AUTH", False),
        mcp_cache_db_path=os.getenv("MCP_CACHE_DB_PATH", "mcp-cache.duckdb"),
        mcp_host=os.getenv("MCP_HOST", "0.0.0.0"),
        mcp_port=_int("MCP_PORT", 8001),
        otel_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or None,
        sentry_dsn=os.getenv("SENTRY_DSN") or None,
        quota_default=_int("QUOTA_DEFAULT", 100_000),
        decision_products=_origins(
            "DECISION_PRODUCTS",
            "noaa-gfs-forecast,noaa-gefs-forecast-35-day",
        ),
    )
