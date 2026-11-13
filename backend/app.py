from __future__ import annotations

import asyncio
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

from cache import Cache
from config import Settings, get_settings
from metrics import Metrics
from rate_limit import CircuitBreaker, InMemoryRateLimiter, OutboundTokenBucket
from schemas import (
    ALL_PRODUCTS,
    FORECAST_PRODUCTS,
    AnalysisQuery,
    PointQuery,
)
from upstream import UpstreamClient, UpstreamError, http_from_upstream


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


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    settings = settings or get_settings()
    metrics = Metrics()
    limiter = InMemoryRateLimiter(settings.rate_limit_per_minute)
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
        cache = Cache(
            settings.cache_db_path,
            settings.cache_ttl_seconds,
            settings.cache_max_rows,
        )
        await cache.prune()

        upstream = UpstreamClient(settings, outbound, breaker, metrics)
        await upstream.start()

        app.state.cache = cache
        app.state.upstream = upstream
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

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready(request: Request) -> dict[str, str]:
        cache: Cache = request.app.state.cache
        try:
            await cache.ping()
        except Exception as exc:
            raise HTTPException(503, "cache unavailable") from exc
        return {"status": "ok", "cache": "ok"}

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

    @app.post("/api/point")
    async def point(request: Request, q: PointQuery) -> dict[str, Any]:
        cache: Cache = request.app.state.cache
        upstream: UpstreamClient = request.app.state.upstream

        payload_base: dict[str, Any] = {
            "location": {
                "latitude": q.latitude,
                "longitude": q.longitude,
            },
            "variables": q.variables,
            "maxLeadTimeHours": q.maxLeadTimeHours,
        }
        if q.initTime is not None:
            payload_base["initTime"] = q.initTime.isoformat()

        async def fetch_one(product_id: str) -> dict[str, Any]:
            key = "point:" + json.dumps(
                {
                    "lat": q.latitude,
                    "lon": q.longitude,
                    "product": product_id,
                    "variables": q.variables,
                    "maxLead": q.maxLeadTimeHours,
                    "initTime": (q.initTime.isoformat() if q.initTime else None),
                },
                sort_keys=True,
            )

            async def fetch() -> dict[str, Any]:
                payload = {"queries": [{"dataProductId": product_id, **payload_base}]}
                data = await upstream.post_json("/forecasts", payload)
                results = data.get("results") if isinstance(data, dict) else None
                result = results[0] if results else None
                if not isinstance(result, dict):
                    raise UpstreamError(502, "empty upstream response")
                result.setdefault("dataProduct", {"id": product_id})
                result["status"] = "ok"
                return result

            try:
                value, _ = await cache.get_or_fetch(key, fetch)
                return value
            except UpstreamError as exc:
                return {
                    "product": product_id,
                    "dataProduct": {"id": product_id},
                    "status": "error",
                    "code": exc.status_code,
                    "error": exc.detail,
                    "retryAfter": exc.retry_after,
                }

        results = await asyncio.gather(*(fetch_one(product_id) for product_id in q.products))
        return {"results": list(results)}

    @app.post("/api/analysis")
    async def analysis(request: Request, q: AnalysisQuery) -> dict[str, Any]:
        cache: Cache = request.app.state.cache
        upstream: UpstreamClient = request.app.state.upstream

        payload_base: dict[str, Any] = {
            "location": {
                "latitude": q.latitude,
                "longitude": q.longitude,
            },
            "variables": q.variables,
            "startTime": q.startTime.isoformat(),
            "endTime": q.endTime.isoformat(),
        }

        async def fetch_one(product_id: str) -> dict[str, Any]:
            key = "analysis:" + json.dumps(
                {
                    "lat": q.latitude,
                    "lon": q.longitude,
                    "product": product_id,
                    "variables": q.variables,
                    "start": q.startTime.isoformat(),
                    "end": q.endTime.isoformat(),
                },
                sort_keys=True,
            )

            async def fetch() -> dict[str, Any]:
                payload = {"queries": [{"dataProductId": product_id, **payload_base}]}
                data = await upstream.post_json("/analyses", payload)
                results = data.get("results") if isinstance(data, dict) else None
                result = results[0] if results else None
                if not isinstance(result, dict):
                    raise UpstreamError(502, "empty upstream response")
                result.setdefault("dataProduct", {"id": product_id})
                result["status"] = "ok"
                return result

            try:
                value, _ = await cache.get_or_fetch(key, fetch)
                return value
            except UpstreamError as exc:
                return {
                    "product": product_id,
                    "dataProduct": {"id": product_id},
                    "status": "error",
                    "code": exc.status_code,
                    "error": exc.detail,
                    "retryAfter": exc.retry_after,
                }

        results = await asyncio.gather(*(fetch_one(product_id) for product_id in q.products))
        return {"results": list(results)}

    return app


app = create_app()
