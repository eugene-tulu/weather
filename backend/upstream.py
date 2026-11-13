from __future__ import annotations

import asyncio
import json
import logging
import math
import random
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from fastapi import HTTPException

from config import Settings
from metrics import Metrics
from rate_limit import CircuitBreaker, OutboundTokenBucket

logger = logging.getLogger("weather.upstream")


class UpstreamError(Exception):
    def __init__(
        self,
        status_code: int,
        detail: str,
        retry_after: float | None = None,
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        self.retry_after = retry_after
        super().__init__(detail)


def parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        seconds = None
    if seconds is not None:
        if not math.isfinite(seconds):
            return None
        return max(0.0, seconds)
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    return max(0.0, (parsed - now).total_seconds())


def _error_detail(response: httpx.Response) -> str:
    try:
        data = response.json()
    except Exception:
        data = None
    if isinstance(data, dict):
        detail = data.get("detail")
        if isinstance(detail, str) and detail:
            return detail[:500]
        if isinstance(detail, list):
            return json.dumps(detail)[:500]
    text = response.text.strip()
    return text[:500] if text else f"upstream returned {response.status_code}"


def http_from_upstream(exc: UpstreamError) -> HTTPException:
    headers: dict[str, str] = {}
    if exc.retry_after is not None:
        headers["retry-after"] = str(max(0, int(exc.retry_after)))

    if exc.status_code == 429:
        return HTTPException(429, "upstream rate limit", headers=headers)
    if exc.status_code == 503:
        return HTTPException(503, "upstream temporarily unavailable", headers=headers)
    if exc.status_code == 404:
        return HTTPException(404, "upstream resource not found")
    if exc.status_code == 422:
        return HTTPException(400, "upstream rejected the request")
    if exc.status_code in (401, 403):
        return HTTPException(502, "upstream authorization failed")
    return HTTPException(502, "upstream request failed")


class UpstreamClient:
    def __init__(
        self,
        settings: Settings,
        outbound: OutboundTokenBucket,
        breaker: CircuitBreaker,
        metrics: Metrics,
    ) -> None:
        self.settings = settings
        self.outbound = outbound
        self.breaker = breaker
        self.metrics = metrics
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        timeout = httpx.Timeout(
            self.settings.upstream_timeout_seconds,
            connect=self.settings.connect_timeout_seconds,
        )
        limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
        self._client = httpx.AsyncClient(timeout=timeout, limits=limits, follow_redirects=True)

    async def stop(self) -> None:
        if self._client is None:
            return
        try:
            await self._client.aclose()
        finally:
            self._client = None

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        if self._client is None:
            raise RuntimeError("upstream client is not started")
        if not self.breaker.allow():
            self.metrics.inc("upstream_circuit_rejected")
            raise UpstreamError(503, "upstream circuit is open")

        url = (
            path
            if path.startswith(("http://", "https://"))
            else f"{self.settings.upstream_base}{path}"
        )

        for attempt in range(self.settings.max_retries + 1):
            try:
                await self.outbound.acquire()
            except TimeoutError as exc:
                self.metrics.inc("outbound_rejections")
                raise UpstreamError(503, "outbound rate limit wait exceeded") from exc

            try:
                self.metrics.inc("upstream_calls")
                response = await self._client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                )
            except httpx.HTTPError as exc:
                self.metrics.inc("upstream_errors")
                self.breaker.record_failure()
                logger.warning(
                    "upstream transport error",
                    extra={
                        "method": method,
                        "path": path,
                        "attempt": attempt + 1,
                        "error": str(exc),
                    },
                )
                if attempt < self.settings.max_retries:
                    self.metrics.inc("upstream_retries")
                    await asyncio.sleep(self._backoff(attempt))
                    continue
                raise UpstreamError(502, f"upstream request failed: {exc}") from exc

            if response.status_code in (429, 503) or response.status_code >= 500:
                retry_after = parse_retry_after(response.headers.get("retry-after"))
                self.metrics.inc("upstream_errors")
                if attempt < self.settings.max_retries:
                    self.metrics.inc("upstream_retries")
                    delay = retry_after if retry_after is not None else self._backoff(attempt)
                    logger.warning(
                        "upstream retry",
                        extra={
                            "method": method,
                            "path": path,
                            "status": response.status_code,
                            "attempt": attempt + 1,
                            "retry_after": retry_after,
                        },
                    )
                    await asyncio.sleep(max(0.05, delay) + random.uniform(0, 0.2))
                    continue
                self.breaker.record_failure()
                raise UpstreamError(
                    response.status_code if response.status_code in (429, 503) else 502,
                    _error_detail(response),
                    retry_after,
                )

            if response.status_code >= 400:
                self.metrics.inc("upstream_errors")
                logger.warning(
                    "upstream client error",
                    extra={
                        "method": method,
                        "path": path,
                        "status": response.status_code,
                    },
                )
                raise UpstreamError(response.status_code, _error_detail(response))

            self.breaker.record_success()
            return response

        raise UpstreamError(502, "upstream request failed")

    def _backoff(self, attempt: int) -> float:
        return min(2.0**attempt, 8.0)

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = await self.request("GET", path, params=params)
        return response.json()

    async def post_json(self, path: str, json_body: dict[str, Any]) -> Any:
        response = await self.request("POST", path, json_body=json_body)
        return response.json()
