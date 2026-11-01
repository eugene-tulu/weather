import json
import time
from typing import List, Optional

import duckdb
import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Weather Leverage API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DYNAMICAL = "https://api.dynamical.org/v1/forecasts"
GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"

db = duckdb.connect(":memory:")
db.execute(
    """CREATE TABLE IF NOT EXISTS cache (
        key VARCHAR PRIMARY KEY,
        payload JSON,
        ts DOUBLE
    )"""
)


class PointQuery(BaseModel):
    latitude: float
    longitude: float
    products: List[str] = ["noaa-gfs-forecast"]
    variables: List[str] = ["temperature_2m"]
    maxLeadTimeHours: int = 24


class AnalysisQuery(BaseModel):
    latitude: float
    longitude: float
    products: List[str] = ["noaa-gfs-analysis"]
    variables: List[str] = ["temperature_2m"]
    startTime: str
    endTime: str


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/geocode")
async def geocode(q: str = Query(..., min_length=2)):
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(GEOCODE, params={"name": q, "count": 8})
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()


@app.post("/api/analysis")
async def analysis(q: AnalysisQuery):
    queries = [
        {
            "dataProductId": pid,
            "location": {"latitude": q.latitude, "longitude": q.longitude},
            "variables": q.variables,
            "startTime": q.startTime,
            "endTime": q.endTime,
        }
        for pid in q.products
    ]
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post("https://api.dynamical.org/v1/analyses", json={"queries": queries})
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()


@app.get("/api/product/{product_id}")
async def product(product_id: str):
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"https://api.dynamical.org/v1/data-products/{product_id}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()


@app.post("/api/point")
async def point(q: PointQuery):
    key = json.dumps(
        {
            "lat": q.latitude,
            "lon": q.longitude,
            "products": q.products,
            "variables": q.variables,
            "maxLead": q.maxLeadTimeHours,
        },
        sort_keys=True,
    )
    row = db.execute(
        "SELECT payload, ts FROM cache WHERE key = ?", [key]
    ).fetchone()
    if row and (time.time() - row[1]) < 600:
        return json.loads(row[0])

    queries = [
        {
            "dataProductId": pid,
            "location": {"latitude": q.latitude, "longitude": q.longitude},
            "variables": q.variables,
            "maxLeadTimeHours": q.maxLeadTimeHours,
        }
        for pid in q.products
    ]
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(DYNAMICAL, json={"queries": queries})
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    payload = r.json()
    db.execute(
        "INSERT OR REPLACE INTO cache (key, payload, ts) VALUES (?, ?, ?)",
        [key, json.dumps(payload), time.time()],
    )
    return payload
