from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import require_auth
from calibration import summarize
from decision import list_operations
from schemas import (
    ForecastRequest,
    ObservationCreate,
    RiskRequest,
    SiteCreate,
    SiteUpdate,
    WorkabilityRequest,
)
from store import AuthContext, Site, Store, site_to_dict

router = APIRouter(prefix="/v1", tags=["v1"])


async def _site(store: Store, context: AuthContext, site_id: str) -> Site:
    site = await store.get_site(context.org_id, site_id)
    if site is None:
        raise HTTPException(404, "Unknown site")
    return site


@router.get("/sites")
async def list_sites(
    request: Request, context: AuthContext = Depends(require_auth)
) -> list[dict[str, Any]]:
    store: Store = request.app.state.store
    return [site_to_dict(site) for site in await store.list_sites(context.org_id)]


@router.post("/sites")
async def create_site(
    request: Request,
    body: SiteCreate,
    context: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    store: Store = request.app.state.store
    site = await store.create_site(
        context.org_id,
        body.name,
        body.latitude,
        body.longitude,
        body.timezone,
        body.operation_profile,
    )
    return site_to_dict(site)


@router.get("/sites/{site_id}")
async def get_site(
    request: Request,
    site_id: str,
    context: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    store: Store = request.app.state.store
    return site_to_dict(await _site(store, context, site_id))


@router.patch("/sites/{site_id}")
async def update_site(
    request: Request,
    site_id: str,
    body: SiteUpdate,
    context: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    store: Store = request.app.state.store
    await _site(store, context, site_id)
    site = await store.update_site(context.org_id, site_id, **body.model_dump(exclude_none=True))
    if site is None:
        raise HTTPException(404, "Unknown site")
    return site_to_dict(site)


@router.delete("/sites/{site_id}")
async def delete_site(
    request: Request,
    site_id: str,
    context: AuthContext = Depends(require_auth),
) -> dict[str, str]:
    store: Store = request.app.state.store
    if not await store.delete_site(context.org_id, site_id):
        raise HTTPException(404, "Unknown site")
    return {"status": "deleted"}


@router.get("/operations")
async def operations(
    context: AuthContext = Depends(require_auth),
) -> list[dict[str, Any]]:
    return list_operations()


@router.get("/usage")
async def usage(request: Request, context: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    store: Store = request.app.state.store
    return await store.usage_summary(context.org_id)


@router.post("/sites/{site_id}/forecast")
async def forecast_site(
    request: Request,
    site_id: str,
    body: ForecastRequest,
    context: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    store: Store = request.app.state.store
    site = await _site(store, context, site_id)
    return await request.app.state.decision.forecast_site(
        context.org_id,
        site,
        body.horizon_hours,
        body.variables,
    )


@router.post("/sites/{site_id}/workability")
async def workability(
    request: Request,
    site_id: str,
    body: WorkabilityRequest,
    context: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    store: Store = request.app.state.store
    site = await _site(store, context, site_id)
    try:
        return await request.app.state.decision.workability_window(
            context.org_id,
            site,
            body.operation,
            body.start_time.isoformat() if body.start_time else None,
            body.end_time.isoformat() if body.end_time else None,
            body.horizon_hours,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/sites/{site_id}/risk")
async def risk(
    request: Request,
    site_id: str,
    body: RiskRequest,
    context: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    store: Store = request.app.state.store
    site = await _site(store, context, site_id)
    try:
        return await request.app.state.decision.risk_flags(
            context.org_id, site, body.operation, body.horizon_hours
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/sites/{site_id}/observations")
async def create_observation(
    request: Request,
    site_id: str,
    body: ObservationCreate,
    context: AuthContext = Depends(require_auth),
) -> dict[str, str]:
    store: Store = request.app.state.store
    await _site(store, context, site_id)
    await store.record_observation(
        context.org_id,
        site_id,
        body.variable,
        body.observed_time,
        body.value,
        body.source,
    )
    return {"status": "recorded"}


@router.get("/sites/{site_id}/calibration")
async def calibration(
    request: Request,
    site_id: str,
    variable: str = Query(default="temperature_2m"),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    threshold: float | None = Query(default=None),
    context: AuthContext = Depends(require_auth),
) -> dict[str, Any]:
    store: Store = request.app.state.store
    await _site(store, context, site_id)
    end_time = end or datetime.now(UTC)
    start_time = start or end_time - timedelta(days=30)
    rows = await store.calibration_rows(context.org_id, site_id, variable, start_time, end_time)
    result = summarize(rows, threshold)
    result["variable"] = variable
    result["site_id"] = site_id
    return result
