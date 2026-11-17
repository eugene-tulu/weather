from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from admin import register_admin
from cache import Cache
from config import Settings, get_settings
from decision import DecisionEngine
from forecast_service import ForecastService
from metrics import Metrics
from observability import instrument_app
from rate_limit import (
    CircuitBreaker,
    InMemoryRateLimiter,
    OutboundTokenBucket,
    RedisRateLimiter,
)
from schemas import (
    ALL_PRODUCTS,
    FORECAST_PRODUCTS,
    MAP_PRODUCT_IDS,
    AnalysisQuery,
    PointQuery,
)
from store import Store
from upstream import UpstreamClient, UpstreamError, http_from_upstream
from v1 import router as v1_router


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in (
            "request_id",
            "method",
            "path",
            "status",
            "duration_ms",
            "cache_hit",
            "upstream_status",
            "product",
            "attempt",
            "retry_after",
            "error",
        ):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)


logger = logging.getLogger("weather.app")


def client_key(scope: Scope, trust_proxy_headers: bool) -> str:
    if trust_proxy_headers:
        forwarded = Headers(scope=scope).get("x-forwarded-for")
        if forwarded:
            first = forwarded.split(",")[0].strip()
            if first:
                return first
    client = scope.get("client")
    if client:
        return str(client[0])
    return "unknown"


class RequestIDMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        state = scope.get("state")
        if not isinstance(state, dict):
            state = {}
            scope["state"] = state
        state["request_id"] = request_id

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append("x-request-id", request_id)
            await send(message)

        await self.app(scope, receive, send_wrapper)


class AccessLogMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            state = scope.get("state") or {}
            logger.info(
                "request",
                extra={
                    "request_id": state.get("request_id") if isinstance(state, dict) else None,
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status": status,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                },
            )


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("x-content-type-options", "nosniff")
                headers.setdefault("x-frame-options", "DENY")
                headers.setdefault("referrer-policy", "strict-origin-when-cross-origin")
                headers.setdefault(
                    "strict-transport-security",
                    "max-age=31536000; includeSubDomains",
                )
                headers.setdefault(
                    "permissions-policy",
                    "geolocation=(self), microphone=(), camera=()",
                )
            await send(message)

        await self.app(scope, receive, send_wrapper)


class RateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        limiter: InMemoryRateLimiter,
        metrics: Metrics,
        trust_proxy_headers: bool,
    ) -> None:
        self.app = app
        self.limiter = limiter
        self.metrics = metrics
        self.trust_proxy_headers = trust_proxy_headers

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        key = client_key(scope, self.trust_proxy_headers)
        retry_after = self.limiter.check(key)
        if inspect.isawaitable(retry_after):
            retry_after = await retry_after
        if retry_after is not None:
            self.metrics.inc("rate_limited")
            body = json.dumps({"detail": "rate limit exceeded"}).encode()
            headers = [
                (b"content-type", b"application/json"),
                (b"retry-after", str(max(1, int(retry_after))).encode()),
                (b"x-ratelimit-limit", str(self.limiter.limit).encode()),
                (b"x-ratelimit-remaining", b"0"),
            ]
            await send(
                {
                    "type": "http.response.start",
                    "status": 429,
                    "headers": headers,
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)


def _map_options(product_id: str, collection: dict[str, Any]) -> dict[str, Any]:
    assets = collection.get("assets") or {}
    asset = assets.get("icechunk-https") or assets.get("icechunk") or {}
    href = asset.get("href")
    if not href:
        raise UpstreamError(502, "map product has no Icechunk asset")

    if href.startswith("s3://"):
        bucket, _, key = href[5:].partition("/")
        storage = asset.get("xarray:storage_options") or {}
        client = storage.get("client_kwargs") or {}
        region = client.get("region_name", "us-west-2")
        href = f"https://{bucket}.s3.{region}.amazonaws.com/{key}"

    raw_variables = collection.get("cube:variables") or {}
    variables: list[dict[str, Any]] = []
    for name, meta in raw_variables.items():
        dims = meta.get("dimensions") or meta.get("dims") or []
        if not isinstance(dims, list):
            continue
        if any(dim in dims for dim in ("pressure_level", "height_above_mean_sea_level")):
            continue
        if not ("time" in dims or ("init_time" in dims and "lead_time" in dims)):
            continue
        variables.append(
            {
                "path": name,
                "name": name,
                "long_name": meta.get("long_name") or name,
                "units": meta.get("unit") or meta.get("units") or "",
                "dims": dims,
            }
        )

    if not variables:
        raise UpstreamError(502, "map product has no surface variables")

    variables.sort(key=lambda variable: variable["name"])
    default = (
        "temperature_2m"
        if any(variable["name"] == "temperature_2m" for variable in variables)
        else variables[0]["name"]
    )

    bbox = ((collection.get("extent") or {}).get("spatial") or {}).get("bbox") or [
        [-180, -90, 180, 90]
    ]
    bounds = bbox[0]
    if len(bounds) == 4 and bounds[0] <= -170 and bounds[2] >= 170:
        bounds = [-180, -60, 180, 75]

    return {
        "id": product_id,
        "href": href,
        "variables": variables,
        "defaultVariable": default,
        "initialView": {"bounds": bounds},
        "proj4": None,
        "virtual": True,
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    settings = settings or get_settings()
    metrics = Metrics()
    limiter = (
        RedisRateLimiter(settings.redis_url, settings.rate_limit_per_minute)
        if settings.redis_url
        else InMemoryRateLimiter(settings.rate_limit_per_minute)
    )
    outbound = OutboundTokenBucket(
        settings.outbound_per_10s,
        settings.outbound_per_60s,
        max_wait_seconds=settings.outbound_max_wait_seconds,
    )
    breaker = CircuitBreaker(
        settings.circuit_failure_threshold,
        settings.circuit_open_seconds,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = Store(settings.database_url)
        await store.init()
        await store.ping()

        cache = Cache(
            settings.cache_db_path,
            settings.cache_ttl_seconds,
            settings.cache_max_rows,
        )
        await cache.prune()

        upstream = UpstreamClient(settings, outbound, breaker, metrics)
        await upstream.start()
        forecast = ForecastService(cache, upstream)
        decision = DecisionEngine(forecast, store, products=settings.decision_products)

        app.state.store = store
        app.state.cache = cache
        app.state.upstream = upstream
        app.state.forecast = forecast
        app.state.decision = decision
        app.state.metrics = metrics
        app.state.settings = settings
        app.state.breaker = breaker

        async def cleanup_loop() -> None:
            while True:
                await asyncio.sleep(300)
                try:
                    await cache.prune()
                except Exception:
                    logger.exception("cache prune failed")

        task = asyncio.create_task(cleanup_loop())
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await upstream.stop()
            cache.close()
            await store.close()

    app = FastAPI(title="Weather Leverage API", lifespan=lifespan)
    app.state.metrics = metrics
    app.state.settings = settings
    app.state.outbound = outbound
    app.state.breaker = breaker

    app.add_middleware(
        RateLimitMiddleware,
        limiter=limiter,
        metrics=metrics,
        trust_proxy_headers=settings.trust_proxy_headers,
    )
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
        max_age=600,
    )
    instrument_app(app, settings)
    app.include_router(v1_router)
    register_admin(app)

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready(request: Request) -> dict[str, str]:
        cache: Cache = request.app.state.cache
        store: Store = request.app.state.store
        try:
            await cache.ping()
            await store.ping()
        except Exception as exc:
            raise HTTPException(503, "cache or database unavailable") from exc
        return {"status": "ok", "cache": "ok", "database": "ok"}

    @app.get("/metrics")
    async def metrics_route(request: Request) -> dict[str, Any]:
        cache: Cache = request.app.state.cache
        breaker: CircuitBreaker = request.app.state.breaker
        outbound: OutboundTokenBucket = request.app.state.outbound
        data: dict[str, Any] = request.app.state.metrics.snapshot()
        data["cache_hits"] = cache.hits
        data["cache_misses"] = cache.misses
        data["cache_rows"] = await cache.size()
        data["circuit_state"] = breaker.state
        data["outbound_queued"] = outbound.queued
        return data

    @app.get("/api/runs")
    async def runs(
        request: Request,
        dataProductId: str = Query(pattern=r"^[a-z0-9][a-z0-9-]{0,127}$"),
        limit: int = Query(5, ge=1, le=100),
    ) -> Any:
        if dataProductId not in FORECAST_PRODUCTS:
            raise HTTPException(400, "dataProductId must be a forecast product")
        cache: Cache = request.app.state.cache
        upstream: UpstreamClient = request.app.state.upstream

        async def fetch() -> Any:
            return await upstream.get_json(
                "/forecasts/runs",
                params={"dataProductId": dataProductId, "limit": limit},
            )

        try:
            data, _ = await cache.get_or_fetch(f"runs:{dataProductId}:{limit}", fetch, 60)
        except UpstreamError as exc:
            raise http_from_upstream(exc) from exc
        return data

    @app.get("/api/geocode")
    async def geocode(
        request: Request,
        q: str = Query(min_length=2, max_length=100),
    ) -> Any:
        cache: Cache = request.app.state.cache
        upstream: UpstreamClient = request.app.state.upstream
        settings: Settings = request.app.state.settings

        async def fetch() -> Any:
            return await upstream.get_json(
                settings.geocode_url,
                params={"name": q, "count": 8},
            )

        try:
            data, _ = await cache.get_or_fetch(f"geocode:{q.strip().lower()}", fetch, 3600)
        except UpstreamError as exc:
            raise http_from_upstream(exc) from exc
        return data

    @app.get("/api/product/{product_id}")
    async def product(
        request: Request,
        product_id: str = Path(pattern=r"^[a-z0-9][a-z0-9-]{0,127}$"),
    ) -> Any:
        if product_id not in ALL_PRODUCTS:
            raise HTTPException(404, "unknown product")
        cache: Cache = request.app.state.cache
        upstream: UpstreamClient = request.app.state.upstream

        async def fetch() -> Any:
            return await upstream.get_json(f"/data-products/{quote(product_id)}")

        try:
            data, _ = await cache.get_or_fetch(f"product:{product_id}", fetch, 3600)
        except UpstreamError as exc:
            raise http_from_upstream(exc) from exc
        return data

    @app.get("/api/map-product/{product_id}")
    async def map_product(
        request: Request,
        product_id: str = Path(pattern=r"^[a-z0-9][a-z0-9-]{0,127}$"),
    ) -> Any:
        if product_id not in MAP_PRODUCT_IDS:
            raise HTTPException(404, "unknown map product")
        cache: Cache = request.app.state.cache
        upstream: UpstreamClient = request.app.state.upstream

        async def fetch() -> Any:
            collection = await upstream.get_json(
                f"https://stac.dynamical.org/{quote(product_id)}/collection.json"
            )
            return _map_options(product_id, collection)

        try:
            data, _ = await cache.get_or_fetch(f"map-product:{product_id}", fetch, 3600)
        except UpstreamError as exc:
            raise http_from_upstream(exc) from exc
        return data

    @app.post("/api/point")
    async def point(request: Request, q: PointQuery) -> dict[str, Any]:
        return await request.app.state.forecast.point(q)

    @app.post("/api/analysis")
    async def analysis(request: Request, q: AnalysisQuery) -> dict[str, Any]:
        return await request.app.state.forecast.analysis(q)

    return app


app = create_app()
