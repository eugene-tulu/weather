from __future__ import annotations

import logging
import time
from typing import Any

from prometheus_client import Counter, Histogram, make_asgi_app
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from config import Settings

logger = logging.getLogger("weather.observability")

HTTP_REQUESTS = Counter(
    "weather_http_requests_total",
    "HTTP requests",
    ["method", "path", "status"],
)
HTTP_LATENCY = Histogram(
    "weather_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
)
MCP_CALLS = Counter(
    "weather_mcp_tool_calls_total",
    "MCP tool calls",
    ["tool", "status"],
)
QUOTA_REJECTIONS = Counter(
    "weather_quota_rejections_total",
    "Requests rejected by monthly quota",
)
DECISION_WINDOWS = Counter(
    "weather_decision_windows_total",
    "Workability evaluations",
    ["operation"],
)


class PrometheusMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path", "").startswith("/metrics"):
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
            method = scope.get("method", "UNKNOWN")
            path = scope.get("path", "unknown")
            HTTP_REQUESTS.labels(method, path, str(status)).inc()
            HTTP_LATENCY.labels(method, path).observe(time.perf_counter() - start)


def instrument_app(app: Any, settings: Settings) -> None:
    app.add_middleware(PrometheusMiddleware)
    app.mount("/prometheus", make_asgi_app())

    if settings.otel_endpoint:
        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.instrumentation.fastapi import (
                FastAPIInstrumentor,
            )
            from opentelemetry.instrumentation.httpx import (
                HTTPXClientInstrumentor,
            )
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            provider = TracerProvider(resource=Resource.create({"service.name": "weather-api"}))
            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_endpoint))
            )
            trace.set_tracer_provider(provider)
            FastAPIInstrumentor.instrument_app(app)
            HTTPXClientInstrumentor().instrument()
        except Exception:
            logger.exception("OpenTelemetry setup failed")

    if settings.sentry_dsn:
        try:
            import sentry_sdk

            sentry_sdk.init(
                dsn=settings.sentry_dsn,
                environment=settings.environment,
                traces_sample_rate=0.1,
                send_default_pii=False,
            )
        except Exception:
            logger.exception("Sentry setup failed")
