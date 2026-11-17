from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from prometheus_client import start_http_server

from auth import authenticate_mcp
from cache import Cache
from config import Settings, get_settings
from decision import DecisionEngine, list_operations
from forecast_service import ForecastService
from metrics import Metrics
from observability import MCP_CALLS
from rate_limit import CircuitBreaker, OutboundTokenBucket
from store import Store, site_to_dict
from upstream import UpstreamClient


@dataclass
class Services:
    settings: Settings
    store: Store
    cache: Cache
    upstream: UpstreamClient
    forecast: ForecastService
    decision: DecisionEngine


@asynccontextmanager
async def lifespan(server: FastMCP):
    settings = get_settings()
    store = Store(settings.database_url)
    await store.init()
    await store.ping()

    cache = Cache(
        settings.mcp_cache_db_path,
        settings.cache_ttl_seconds,
        settings.cache_max_rows,
    )
    await cache.prune()
    metrics = Metrics()
    outbound = OutboundTokenBucket(
        settings.outbound_per_10s,
        settings.outbound_per_60s,
        max_wait_seconds=settings.outbound_max_wait_seconds,
    )
    breaker = CircuitBreaker(
        settings.circuit_failure_threshold,
        settings.circuit_open_seconds,
    )
    upstream = UpstreamClient(settings, outbound, breaker, metrics)
    await upstream.start()
    forecast = ForecastService(cache, upstream)
    decision = DecisionEngine(forecast, store, products=settings.decision_products)

    try:
        start_http_server(int(os.getenv("MCP_METRICS_PORT", "9091")), addr="0.0.0.0")
    except OSError:
        pass

    services = Services(
        settings=settings,
        store=store,
        cache=cache,
        upstream=upstream,
        forecast=forecast,
        decision=decision,
    )
    try:
        yield services
    finally:
        await upstream.stop()
        cache.close()
        await store.close()


settings = get_settings()
mcp = FastMCP(
    "weather-decision",
    instructions=(
        "Decision-grade weather tools for a specific site. Use list_sites, "
        "forecast_site, workability_window, and risk_flags. All results "
        "include confidence and provenance; do not treat them as guarantees."
    ),
    host=settings.mcp_host,
    port=settings.mcp_port,
    streamable_http_path="/mcp",
    stateless_http=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    lifespan=lifespan,
)


def _services(ctx: Context) -> Services:
    return ctx.request_context.lifespan_context


def _tool_ok(name: str) -> None:
    MCP_CALLS.labels(name, "ok").inc()


@mcp.tool()
async def list_sites(ctx: Context) -> list[dict[str, Any]]:
    """List sites available to the API key's organization."""
    services = _services(ctx)
    context = await authenticate_mcp(ctx, "list_sites", "sites:read")
    sites = await services.store.list_sites(context.org_id)
    _tool_ok("list_sites")
    return [site_to_dict(site) for site in sites]


@mcp.tool()
async def get_site(ctx: Context, site_id: str) -> dict[str, Any]:
    """Read one site by id."""
    services = _services(ctx)
    context = await authenticate_mcp(ctx, "get_site", "sites:read")
    site = await services.store.get_site(context.org_id, site_id)
    if site is None:
        raise ValueError("Unknown site")
    _tool_ok("get_site")
    return site_to_dict(site)


@mcp.tool()
async def forecast_site(
    ctx: Context,
    site_id: str,
    horizon_hours: int = 48,
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """Return a compact hourly forecast and summary for a site."""
    services = _services(ctx)
    context = await authenticate_mcp(ctx, "forecast_site", "forecast:read")
    site = await services.store.get_site(context.org_id, site_id)
    if site is None:
        raise ValueError("Unknown site")
    _tool_ok("forecast_site")
    return await services.decision.forecast_site(context.org_id, site, horizon_hours, variables)


@mcp.tool()
async def workability_window(
    ctx: Context,
    site_id: str,
    operation: str,
    start_time: str | None = None,
    end_time: str | None = None,
    horizon_hours: int = 48,
) -> dict[str, Any]:
    """Find ranked workable windows for an operation at a site."""
    services = _services(ctx)
    context = await authenticate_mcp(ctx, "workability_window", "forecast:read")
    site = await services.store.get_site(context.org_id, site_id)
    if site is None:
        raise ValueError("Unknown site")
    _tool_ok("workability_window")
    return await services.decision.workability_window(
        context.org_id,
        site,
        operation,
        start_time,
        end_time,
        horizon_hours,
    )


@mcp.tool()
async def risk_flags(
    ctx: Context,
    site_id: str,
    operation: str = "general",
    horizon_hours: int = 48,
) -> dict[str, Any]:
    """Return weather risk flags for an operation at a site."""
    services = _services(ctx)
    context = await authenticate_mcp(ctx, "risk_flags", "forecast:read")
    site = await services.store.get_site(context.org_id, site_id)
    if site is None:
        raise ValueError("Unknown site")
    _tool_ok("risk_flags")
    return await services.decision.risk_flags(context.org_id, site, operation, horizon_hours)


@mcp.tool()
async def get_usage(ctx: Context) -> dict[str, Any]:
    """Return the current monthly usage and quota for this API key."""
    services = _services(ctx)
    context = await authenticate_mcp(ctx, "get_usage", "usage:read")
    _tool_ok("get_usage")
    return await services.store.usage_summary(context.org_id)


@mcp.tool()
async def get_operations(ctx: Context) -> list[dict[str, Any]]:
    """List supported workability operation profiles."""
    await authenticate_mcp(ctx, "get_operations", "forecast:read")
    _tool_ok("get_operations")
    return list_operations()


@mcp.tool()
async def get_data_provenance(
    ctx: Context,
    site_id: str,
    variable: str = "temperature_2m",
) -> dict[str, Any]:
    """Return the model products, versions, run time, and summary behind a site forecast."""
    services = _services(ctx)
    context = await authenticate_mcp(ctx, "get_data_provenance", "forecast:read")
    site = await services.store.get_site(context.org_id, site_id)
    if site is None:
        raise ValueError("Unknown site")
    _tool_ok("get_data_provenance")
    forecast = await services.decision.forecast_site(
        context.org_id, site, 24, [variable], persist=False
    )
    return {
        "site": forecast["site"],
        "generated_at": forecast["generated_at"],
        "init_time": forecast["init_time"],
        "products": forecast["products"],
        "product_versions": forecast["product_versions"],
        "variable": variable,
        "summary": forecast["summary"].get(variable),
        "source": "Dynamical point API",
    }


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
