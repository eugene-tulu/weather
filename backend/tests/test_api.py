from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace

import httpx
import respx
from fastapi.testclient import TestClient

from app import create_app


@contextmanager
def app_client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


FORECAST_RESPONSE = {
    "results": [
        {
            "dataProduct": {
                "id": "noaa-gfs-forecast",
                "version": "0.2.7",
            },
            "forecasts": [
                {
                    "initTime": "2026-11-12T06:00:00Z",
                    "validTimes": [
                        "2026-11-12T06:00:00Z",
                        "2026-11-12T07:00:00Z",
                    ],
                    "data": {"temperature_2m": [1.0, 2.0]},
                }
            ],
            "variables": {"temperature_2m": {"unit": "degree_Celsius"}},
        }
    ]
}

ANALYSIS_RESPONSE = {
    "results": [
        {
            "dataProduct": {"id": "noaa-gfs-analysis"},
            "analysisTimes": [
                "2026-11-01T00:00:00Z",
                "2026-11-01T01:00:00Z",
            ],
            "data": {"temperature_2m": [1.0, 2.0]},
        }
    ]
}

POINT_BODY = {
    "latitude": 41.88,
    "longitude": -87.63,
    "products": ["noaa-gfs-forecast"],
    "variables": ["temperature_2m"],
    "maxLeadTimeHours": 6,
}


def test_point_is_normalized_and_cached(settings):
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post("https://api.dynamical.org/v1/forecasts").mock(
            return_value=httpx.Response(200, json=FORECAST_RESPONSE)
        )

        with app_client(settings) as client:
            first = client.post("/api/point", json=POINT_BODY)
            assert first.status_code == 200
            first_result = first.json()["results"][0]
            assert first_result["status"] == "ok"
            assert first_result["dataProduct"]["id"] == "noaa-gfs-forecast"

            second = client.post("/api/point", json=POINT_BODY)
            assert second.status_code == 200
            assert route.call_count == 1


def test_point_validation(settings):
    with app_client(settings) as client:
        invalid_location = dict(POINT_BODY, latitude=100)
        assert client.post("/api/point", json=invalid_location).status_code == 422

        empty_products = dict(POINT_BODY, products=[])
        assert client.post("/api/point", json=empty_products).status_code == 422

        unknown_variable = dict(POINT_BODY, variables=["nope"])
        assert client.post("/api/point", json=unknown_variable).status_code == 422

        legacy_variable = dict(POINT_BODY, variables=["total_precipitation"])
        assert client.post("/api/point", json=legacy_variable).status_code == 422

        bad_lead = dict(POINT_BODY, maxLeadTimeHours=0)
        assert client.post("/api/point", json=bad_lead).status_code == 422


def test_analysis_window_validation(settings):
    with respx.mock(assert_all_called=False) as mock:
        mock.post("https://api.dynamical.org/v1/analyses").mock(
            return_value=httpx.Response(200, json=ANALYSIS_RESPONSE)
        )

        base = {
            "latitude": 41.88,
            "longitude": -87.63,
            "products": ["noaa-gfs-analysis"],
            "variables": ["temperature_2m"],
        }

        with app_client(settings) as client:
            valid = client.post(
                "/api/analysis",
                json=dict(
                    base,
                    startTime="2026-11-01T00:00:00Z",
                    endTime="2026-12-01T00:00:00Z",
                ),
            )
            assert valid.status_code == 200

            too_long = client.post(
                "/api/analysis",
                json=dict(
                    base,
                    startTime="2026-11-01T00:00:00Z",
                    endTime="2026-12-03T00:00:00Z",
                ),
            )
            assert too_long.status_code == 422

            naive = client.post(
                "/api/analysis",
                json=dict(
                    base,
                    startTime="2026-11-01T00:00:00",
                    endTime="2026-11-02T00:00:00",
                ),
            )
            assert naive.status_code == 422


def test_runs_rate_limit_is_propagated(settings):
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url__regex=r"https://api\.dynamical\.org/v1/forecasts/runs.*").mock(
            return_value=httpx.Response(
                429,
                headers={"retry-after": "2"},
                json={"detail": "rate limit"},
            )
        )

        with app_client(settings) as client:
            response = client.get(
                "/api/runs",
                params={"dataProductId": "noaa-gfs-forecast", "limit": 3},
            )
            assert response.status_code == 429
            assert response.headers["retry-after"] == "2"


def test_point_upstream_rate_limit_is_per_product(settings):
    with respx.mock(assert_all_called=False) as mock:
        mock.post("https://api.dynamical.org/v1/forecasts").mock(
            return_value=httpx.Response(
                429,
                headers={"retry-after": "2"},
                json={"detail": "rate limit"},
            )
        )

        with app_client(settings) as client:
            response = client.post("/api/point", json=POINT_BODY)
            assert response.status_code == 200
            result = response.json()["results"][0]
            assert result["status"] == "error"
            assert result["code"] == 429
            assert result["retryAfter"] == 2


def test_geocode(settings):
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://geocoding-api.open-meteo.com/v1/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 1,
                            "name": "Chicago",
                            "latitude": 41.88,
                            "longitude": -87.63,
                        }
                    ]
                },
            )
        )

        with app_client(settings) as client:
            response = client.get("/api/geocode", params={"q": "Chicago"})
            assert response.status_code == 200
            assert response.json()["results"][0]["name"] == "Chicago"


def test_product_metadata(settings):
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://api.dynamical.org/v1/data-products/noaa-gfs-forecast").mock(
            return_value=httpx.Response(200, json={"id": "noaa-gfs-forecast"})
        )

        with app_client(settings) as client:
            response = client.get("/api/product/noaa-gfs-forecast")
            assert response.status_code == 200
            assert response.json()["id"] == "noaa-gfs-forecast"

            unknown = client.get("/api/product/nope")
            assert unknown.status_code == 404


MAP_COLLECTION = {
    "id": "noaa-gfs-forecast-virtual",
    "assets": {"icechunk-https": {"href": "https://example.com/data.icechunk"}},
    "cube:variables": {
        "temperature_2m": {
            "dimensions": [
                "init_time",
                "lead_time",
                "latitude",
                "longitude",
            ],
            "long_name": "Temperature",
            "unit": "degree_Celsius",
        },
        "pressure_level/cloud_cover": {
            "dimensions": [
                "init_time",
                "lead_time",
                "latitude",
                "longitude",
                "pressure_level",
            ],
            "unit": "percent",
        },
    },
    "extent": {"spatial": {"bbox": [[-180, -90, 179.75, 90]]}},
}


def test_map_product_options(settings):
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://stac.dynamical.org/noaa-gfs-forecast-virtual/collection.json").mock(
            return_value=httpx.Response(200, json=MAP_COLLECTION)
        )

        with app_client(settings) as client:
            response = client.get("/api/map-product/noaa-gfs-forecast-virtual")
            assert response.status_code == 200
            body = response.json()
            assert body["href"] == "https://example.com/data.icechunk"
            assert [variable["name"] for variable in body["variables"]] == ["temperature_2m"]
            assert body["defaultVariable"] == "temperature_2m"
            assert body["initialView"]["bounds"] == [-180, -60, 180, 75]

            unknown = client.get("/api/map-product/nope")
            assert unknown.status_code == 404


def test_health_metrics_and_security_headers(settings):
    with app_client(settings) as client:
        live = client.get("/health/live")
        assert live.status_code == 200
        assert live.headers["x-content-type-options"] == "nosniff"
        assert live.headers["x-frame-options"] == "DENY"
        assert "x-request-id" in live.headers

        ready = client.get("/health/ready")
        assert ready.status_code == 200
        assert ready.json()["cache"] == "ok"

        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert "cache_hits" in metrics.json()

        prometheus = client.get("/prometheus/metrics")
        assert prometheus.status_code == 200
        assert "weather_http_requests_total" in prometheus.text


def test_inbound_rate_limit(settings):
    limited = replace(settings, rate_limit_per_minute=1)
    with app_client(limited) as client:
        assert client.get("/health/live").status_code == 200
        blocked = client.get("/health/live")
        assert blocked.status_code == 429
        assert "retry-after" in blocked.headers
