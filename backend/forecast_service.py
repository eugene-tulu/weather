from __future__ import annotations

import asyncio
import json
from typing import Any

from cache import Cache
from schemas import AnalysisQuery, PointQuery
from upstream import UpstreamClient, UpstreamError


class ForecastService:
    """Shared point/analysis fetch used by REST and MCP."""

    def __init__(self, cache: Cache, upstream: UpstreamClient) -> None:
        self.cache = cache
        self.upstream = upstream

    async def point(self, query: PointQuery) -> dict[str, Any]:
        payload_base: dict[str, Any] = {
            "location": {
                "latitude": query.latitude,
                "longitude": query.longitude,
            },
            "variables": query.variables,
            "maxLeadTimeHours": query.maxLeadTimeHours,
        }
        if query.initTime is not None:
            payload_base["initTime"] = query.initTime.isoformat()

        async def fetch_one(product_id: str) -> dict[str, Any]:
            key = "point:" + json.dumps(
                {
                    "lat": query.latitude,
                    "lon": query.longitude,
                    "product": product_id,
                    "variables": query.variables,
                    "maxLead": query.maxLeadTimeHours,
                    "initTime": (query.initTime.isoformat() if query.initTime else None),
                },
                sort_keys=True,
            )

            async def fetch() -> dict[str, Any]:
                payload = {"queries": [{"dataProductId": product_id, **payload_base}]}
                data = await self.upstream.post_json("/forecasts", payload)
                results = data.get("results") if isinstance(data, dict) else None
                result = results[0] if results else None
                if not isinstance(result, dict):
                    raise UpstreamError(502, "empty upstream response")
                result.setdefault("dataProduct", {"id": product_id})
                result["status"] = "ok"
                return result

            try:
                value, _ = await self.cache.get_or_fetch(key, fetch)
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

        results = await asyncio.gather(*(fetch_one(product_id) for product_id in query.products))
        return {"results": list(results)}

    async def analysis(self, query: AnalysisQuery) -> dict[str, Any]:
        payload_base: dict[str, Any] = {
            "location": {
                "latitude": query.latitude,
                "longitude": query.longitude,
            },
            "variables": query.variables,
            "startTime": query.startTime.isoformat(),
            "endTime": query.endTime.isoformat(),
        }

        async def fetch_one(product_id: str) -> dict[str, Any]:
            key = "analysis:" + json.dumps(
                {
                    "lat": query.latitude,
                    "lon": query.longitude,
                    "product": product_id,
                    "variables": query.variables,
                    "start": query.startTime.isoformat(),
                    "end": query.endTime.isoformat(),
                },
                sort_keys=True,
            )

            async def fetch() -> dict[str, Any]:
                payload = {"queries": [{"dataProductId": product_id, **payload_base}]}
                data = await self.upstream.post_json("/analyses", payload)
                results = data.get("results") if isinstance(data, dict) else None
                result = results[0] if results else None
                if not isinstance(result, dict):
                    raise UpstreamError(502, "empty upstream response")
                result.setdefault("dataProduct", {"id": product_id})
                result["status"] = "ok"
                return result

            try:
                value, _ = await self.cache.get_or_fetch(key, fetch)
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

        results = await asyncio.gather(*(fetch_one(product_id) for product_id in query.products))
        return {"results": list(results)}
