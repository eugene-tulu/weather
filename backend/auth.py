from __future__ import annotations

import secrets
from datetime import UTC, datetime

from fastapi import HTTPException, Request
from mcp.server.fastmcp import Context

from observability import QUOTA_REJECTIONS
from store import AuthContext, QuotaState, Store


def extract_api_key(headers) -> str | None:
    value = headers.get("x-api-key")
    if value:
        return value.strip()
    authorization = headers.get("authorization")
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def _quota_headers(quota: QuotaState) -> dict[str, str]:
    remaining = max(0, quota.limit - quota.used) if quota.limit > 0 else 0
    retry_after = max(1, int((quota.reset_at - datetime.now(UTC)).total_seconds()))
    return {
        "X-Quota-Limit": str(quota.limit),
        "X-Quota-Remaining": str(remaining),
        "Retry-After": str(retry_after),
    }


def require_scope(context: AuthContext, scope: str) -> None:
    if scope not in context.scopes and "admin" not in context.scopes:
        raise HTTPException(403, f"API key is missing required scope: {scope}")


async def require_auth(request: Request) -> AuthContext:
    store: Store = request.app.state.store
    api_key = extract_api_key(request.headers)
    if not api_key:
        raise HTTPException(401, "X-API-Key or Bearer token is required")

    context = await store.authenticate(api_key)
    if context is None:
        raise HTTPException(401, "Invalid or revoked API key")

    quota = await store.check_quota(context.org_id)
    if not quota.allowed:
        raise HTTPException(429, "Monthly quota exceeded", headers=_quota_headers(quota))

    await store.record_usage(
        context.org_id,
        context.api_key_id,
        request.url.path,
        1,
        {"method": request.method},
    )
    return context


async def require_admin(request: Request) -> None:
    settings = request.app.state.settings
    if not settings.admin_token:
        raise HTTPException(404, "Admin is not configured")
    supplied = request.headers.get("x-admin-token", "")
    if not secrets.compare_digest(supplied, settings.admin_token):
        raise HTTPException(403, "Invalid admin token")


async def authenticate_mcp(ctx: Context, tool_name: str, scope: str | None = None) -> AuthContext:
    request = ctx.request_context.request
    if request is None:
        raise ValueError("MCP tool requires an HTTP request with an API key")
    api_key = extract_api_key(request.headers)
    if not api_key:
        raise ValueError("X-API-Key or Bearer token is required")

    services = ctx.request_context.lifespan_context
    store: Store = services.store
    context = await store.authenticate(api_key)
    if context is None:
        raise ValueError("Invalid or revoked API key")
    if scope is not None:
        if scope not in context.scopes and "admin" not in context.scopes:
            raise ValueError(f"API key is missing required scope: {scope}")

    quota = await store.check_quota(context.org_id)
    if not quota.allowed:
        QUOTA_REJECTIONS.inc()
        raise ValueError("Monthly quota exceeded")

    await store.record_usage(context.org_id, context.api_key_id, f"mcp:{tool_name}", 1)
    return context
