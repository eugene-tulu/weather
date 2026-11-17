from __future__ import annotations

from datetime import UTC, datetime

from decision import DecisionEngine
from store import Site


class FakeForecast:
    async def point(self, query):
        times = [f"2026-01-01T0{hour}:00:00Z" for hour in range(6)]
        return {
            "results": [
                {
                    "status": "ok",
                    "dataProduct": {
                        "id": "noaa-gfs-forecast",
                        "version": "test",
                    },
                    "forecasts": [
                        {
                            "initTime": "2026-01-01T00:00:00Z",
                            "validTimes": times,
                            "data": {
                                "temperature_2m": [10.0] * 6,
                                "precipitation_surface": [0.0] * 6,
                                "wind_u_10m": [3.0] * 6,
                                "wind_v_10m": [4.0] * 6,
                                "relative_humidity_2m": [60.0] * 6,
                            },
                        }
                    ],
                }
            ]
        }


class FakeStore:
    def __init__(self):
        self.samples = 0

    async def record_forecast_samples(self, *args, **kwargs):
        self.samples += 1


def make_site() -> Site:
    return Site(
        id="site1",
        org_id="org1",
        name="Site",
        latitude=41.88,
        longitude=-87.63,
        timezone="UTC",
        operation_profile="earthworks",
        created_at=datetime.now(UTC),
    )


async def test_forecast_and_workability():
    engine = DecisionEngine(FakeForecast(), FakeStore(), products=("noaa-gfs-forecast",))
    forecast = await engine.forecast_site("org1", make_site(), 6, persist=False)
    assert len(forecast["series"]) == 6
    assert forecast["series"][0]["values"]["wind_speed"] == 5.0
    assert forecast["series"][0]["confidence"] == 70.0

    windows = await engine.workability_window(
        "org1",
        make_site(),
        "earthworks",
        "2026-01-01T00:00:00Z",
        "2026-01-01T05:00:00Z",
        6,
    )
    assert windows["windows"]
    assert windows["windows"][0]["hours"] == 6


async def test_risk_flags_detect_precipitation():
    class WetForecast(FakeForecast):
        async def point(self, query):
            data = await super().point(query)
            data["results"][0]["forecasts"][0]["data"]["precipitation_surface"] = [0.001] * 6
            return data

    engine = DecisionEngine(WetForecast(), FakeStore(), products=("noaa-gfs-forecast",))
    result = await engine.risk_flags("org1", make_site(), "earthworks", horizon_hours=6)
    assert any(flag["type"] == "precipitation" for flag in result["flags"])
