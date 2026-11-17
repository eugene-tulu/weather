from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from forecast_service import ForecastService
from observability import DECISION_WINDOWS
from schemas import PointQuery
from store import Site, Store, site_to_dict


@dataclass(frozen=True)
class OperationProfile:
    id: str
    label: str
    description: str
    precip_max: float
    wind_max: float
    temp_min: float
    temp_max: float
    rh_min: float | None = None
    rh_max: float | None = None


OPERATIONS: dict[str, OperationProfile] = {
    "general": OperationProfile(
        "general",
        "General outdoor work",
        "Light rain and moderate wind are acceptable.",
        0.0001,
        12.0,
        -10.0,
        40.0,
    ),
    "earthworks": OperationProfile(
        "earthworks",
        "Earthworks",
        "Excavation, grading, and hauling; wet ground is the constraint.",
        0.00005,
        10.0,
        2.0,
        40.0,
    ),
    "concrete_pour": OperationProfile(
        "concrete_pour",
        "Concrete pour",
        "Rain-free, moderate temperature, and low wind.",
        0.00002,
        8.0,
        5.0,
        32.0,
    ),
    "crane_lift": OperationProfile(
        "crane_lift",
        "Crane lift",
        "Wind and precipitation limits for lifting operations.",
        0.00005,
        9.0,
        -5.0,
        40.0,
    ),
    "spraying": OperationProfile(
        "spraying",
        "Spraying / application",
        "Low wind, no rain, and suitable humidity.",
        0.00002,
        5.0,
        5.0,
        30.0,
        40.0,
        90.0,
    ),
    "planting": OperationProfile(
        "planting",
        "Planting",
        "Soil workability and temperature for establishment.",
        0.00005,
        8.0,
        8.0,
        35.0,
    ),
    "harvest": OperationProfile(
        "harvest",
        "Harvest",
        "Dry, low-humidity, low-wind conditions.",
        0.00002,
        7.0,
        -2.0,
        38.0,
        None,
        85.0,
    ),
    "mining": OperationProfile(
        "mining",
        "Mining / heavy civil",
        "Heavy equipment work with wider weather tolerance.",
        0.0001,
        12.0,
        -10.0,
        45.0,
    ),
}

DEFAULT_VARIABLES = (
    "temperature_2m",
    "precipitation_surface",
    "wind_u_10m",
    "wind_v_10m",
    "relative_humidity_2m",
)

VARIABLE_SCALE = {
    "temperature_2m": 10.0,
    "precipitation_surface": 0.005,
    "wind_speed": 8.0,
    "relative_humidity_2m": 25.0,
}


def list_operations() -> list[dict[str, Any]]:
    return [asdict(profile) for profile in OPERATIONS.values()]


def _to_float(value: Any) -> float | None:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = sum(values) / len(values)
    return math.sqrt(sum((value - avg) ** 2 for value in values) / len(values))


def _wind_speed(u: Any, v: Any) -> float | None:
    uu = _to_float(u)
    vv = _to_float(v)
    if uu is None or vv is None:
        return None
    return math.sqrt(uu * uu + vv * vv)


def _parse_time(value: str | None, fallback: datetime) -> datetime:
    if not value:
        return fallback
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class DecisionEngine:
    def __init__(
        self,
        forecast: ForecastService,
        store: Store,
        *,
        products: tuple[str, ...],
    ) -> None:
        self.forecast = forecast
        self.store = store
        self.products = products

    async def forecast_site(
        self,
        org_id: str,
        site: Site,
        horizon_hours: int = 48,
        variables: list[str] | None = None,
        *,
        persist: bool = True,
    ) -> dict[str, Any]:
        horizon = max(1, min(int(horizon_hours), 840))
        requested = list(variables or DEFAULT_VARIABLES)
        fetch_variables = list(requested)
        if "wind_speed" in fetch_variables:
            fetch_variables = [variable for variable in fetch_variables if variable != "wind_speed"]
            fetch_variables.extend(["wind_u_10m", "wind_v_10m"])

        query = PointQuery(
            latitude=site.latitude,
            longitude=site.longitude,
            products=list(self.products),
            variables=list(dict.fromkeys(fetch_variables)),
            maxLeadTimeHours=horizon,
        )
        response = await self.forecast.point(query)
        results = [result for result in response.get("results", []) if result.get("status") == "ok"]

        model_values: dict[str, dict[str, list[float]]] = {}
        precip_members: dict[str, list[float]] = {}
        init_time: str | None = None
        product_versions: dict[str, str] = {}

        for result in results:
            data_product = result.get("dataProduct") or {}
            product_id = data_product.get("id", "unknown")
            product_versions[product_id] = str(data_product.get("version", "unknown"))
            if init_time is None:
                init_time = self._init_time(result)
            self._collect_result(
                result,
                product_id,
                model_values,
                precip_members,
                requested,
            )

        times = sorted(model_values)
        series: list[dict[str, Any]] = []
        summary: dict[str, dict[str, float | None]] = {}

        for time in times:
            values: dict[str, float | None] = {}
            for variable in requested:
                if variable == "wind_speed":
                    candidates = model_values[time].get("wind_speed", [])
                else:
                    candidates = model_values[time].get(variable, [])
                values[variable] = _median(candidates) if candidates else None

            wind_candidates = model_values[time].get("wind_speed", [])
            values["wind_speed"] = _median(wind_candidates) if wind_candidates else None
            confidence = self._confidence(model_values[time], requested)
            precip_values = precip_members.get(time, [])
            probability = (
                sum(value > OPERATIONS["general"].precip_max for value in precip_values)
                / len(precip_values)
                if precip_values
                else None
            )
            series.append(
                {
                    "time": time,
                    "values": values,
                    "confidence": confidence,
                    "probability_precip": probability,
                }
            )

        for variable in requested:
            values = [
                value for entry in series if (value := entry["values"].get(variable)) is not None
            ]
            summary[variable] = {
                "min": min(values) if values else None,
                "max": max(values) if values else None,
                "median": _median(values) if values else None,
            }

        if persist:
            samples_by_variable: dict[str, list[dict[str, Any]]] = {}
            for entry in series:
                for variable, value in entry["values"].items():
                    if value is None:
                        continue
                    samples_by_variable.setdefault(variable, []).append(
                        {
                            "time": entry["time"],
                            "value": value,
                            "probability": (
                                entry["probability_precip"]
                                if variable == "precipitation_surface"
                                else None
                            ),
                        }
                    )
            for variable, samples in samples_by_variable.items():
                await self.store.record_forecast_samples(
                    org_id,
                    site.id,
                    variable,
                    "ensemble_median",
                    samples,
                )

        return {
            "site": site_to_dict(site),
            "generated_at": datetime.now(UTC).isoformat(),
            "horizon_hours": horizon,
            "init_time": init_time,
            "products": [result["dataProduct"]["id"] for result in results],
            "product_versions": product_versions,
            "variables": requested,
            "series": series,
            "summary": summary,
        }

    async def workability_window(
        self,
        org_id: str,
        site: Site,
        operation: str,
        start_time: str | None = None,
        end_time: str | None = None,
        horizon_hours: int = 48,
    ) -> dict[str, Any]:
        profile = OPERATIONS.get(operation)
        if profile is None:
            raise ValueError(f"Unknown operation. Choose one of: {', '.join(OPERATIONS)}")
        DECISION_WINDOWS.labels(operation).inc()
        forecast = await self.forecast_site(org_id, site, horizon_hours, persist=True)
        now = datetime.now(UTC)
        start = _parse_time(start_time, now)
        end = _parse_time(end_time, start + timedelta(hours=min(horizon_hours, 168)))
        entries = [
            entry
            for entry in forecast["series"]
            if start <= datetime.fromisoformat(entry["time"].replace("Z", "+00:00")) <= end
        ]

        if not entries:
            return {
                "site": site_to_dict(site),
                "operation": asdict(profile),
                "generated_at": forecast["generated_at"],
                "init_time": forecast["init_time"],
                "windows": [],
                "best_effort": None,
                "note": (
                    "No future forecast hours are available for this window. "
                    "Try a larger horizon or wait for a newer model run."
                ),
            }

        windows: list[dict[str, Any]] = []
        current: list[dict[str, Any]] = []
        for entry in entries:
            evaluation = self._evaluate(profile, entry)
            if evaluation["workable"]:
                current.append({**entry, **evaluation})
            elif current:
                windows.append(self._window(current))
                current = []
        if current:
            windows.append(self._window(current))

        windows.sort(
            key=lambda window: (window["score"], window["confidence"]),
            reverse=True,
        )
        best = max(
            ({**entry, **self._evaluate(profile, entry)} for entry in entries),
            key=lambda entry: entry["score"],
            default=None,
        )
        return {
            "site": site_to_dict(site),
            "operation": asdict(profile),
            "generated_at": forecast["generated_at"],
            "init_time": forecast["init_time"],
            "windows": windows[:10],
            "best_effort": best,
        }

    async def risk_flags(
        self,
        org_id: str,
        site: Site,
        operation: str = "general",
        horizon_hours: int = 48,
    ) -> dict[str, Any]:
        profile = OPERATIONS.get(operation)
        if profile is None:
            raise ValueError(f"Unknown operation. Choose one of: {', '.join(OPERATIONS)}")
        DECISION_WINDOWS.labels(operation).inc()
        forecast = await self.forecast_site(org_id, site, horizon_hours, persist=True)
        flags: list[dict[str, Any]] = []
        for entry in forecast["series"]:
            values = entry["values"]
            precip = _to_float(values.get("precipitation_surface"))
            wind = _to_float(values.get("wind_speed"))
            temp = _to_float(values.get("temperature_2m"))
            rh = _to_float(values.get("relative_humidity_2m"))

            if precip is not None and precip > profile.precip_max:
                flags.append(
                    self._flag(
                        "precipitation",
                        "high",
                        entry["time"],
                        precip,
                        profile.precip_max,
                        "Precipitation above the operation threshold.",
                    )
                )
            if wind is not None and wind > profile.wind_max:
                flags.append(
                    self._flag(
                        "wind",
                        "high",
                        entry["time"],
                        wind,
                        profile.wind_max,
                        "Wind above the operation threshold.",
                    )
                )
            if temp is not None and (temp < profile.temp_min or temp > profile.temp_max):
                flags.append(
                    self._flag(
                        "temperature",
                        "medium",
                        entry["time"],
                        temp,
                        profile.temp_max,
                        "Temperature outside the operation range.",
                    )
                )
            if rh is not None and (
                (profile.rh_min is not None and rh < profile.rh_min)
                or (profile.rh_max is not None and rh > profile.rh_max)
            ):
                flags.append(
                    self._flag(
                        "relative_humidity",
                        "medium",
                        entry["time"],
                        rh,
                        profile.rh_max or profile.rh_min,
                        "Humidity outside the operation range.",
                    )
                )

        return {
            "site": site_to_dict(site),
            "operation": asdict(profile),
            "generated_at": forecast["generated_at"],
            "flags": flags,
        }

    def _collect_result(
        self,
        result: dict[str, Any],
        product_id: str,
        model_values: dict[str, dict[str, list[float]]],
        precip_members: dict[str, list[float]],
        requested: list[str],
    ) -> None:
        forecasts = result.get("forecasts") or []
        forecast = forecasts[0] if forecasts else {}
        times = forecast.get("validTimes") or []
        data = forecast.get("data") or {}
        ensemble = forecast.get("ensembleMembers") or []

        for index, time in enumerate(times):
            bucket = model_values.setdefault(time, {})
            if ensemble:
                values = {
                    variable: [
                        value
                        for member in ensemble
                        if (value := self._member_value(member, variable, index)) is not None
                    ]
                    for variable in requested
                    if variable != "wind_speed"
                }
                wind_values = [
                    value
                    for member in ensemble
                    if (value := self._member_wind(member, index)) is not None
                ]
                precip_values = values.get("precipitation_surface", [])
                if precip_values:
                    precip_members.setdefault(time, []).extend(precip_values)
            else:
                values: dict[str, list[float]] = {}
                for variable in requested:
                    if variable == "wind_speed":
                        continue
                    series = data.get(variable) or []
                    if index < len(series):
                        value = _to_float(series[index])
                        if value is not None:
                            values[variable] = [value]
                u_series = data.get("wind_u_10m") or []
                v_series = data.get("wind_v_10m") or []
                wind_values = []
                if index < len(u_series) and index < len(v_series):
                    value = _wind_speed(u_series[index], v_series[index])
                    if value is not None:
                        wind_values = [value]

            for variable, values_for_model in values.items():
                if values_for_model:
                    bucket.setdefault(variable, []).append(_median(values_for_model))
            if wind_values:
                bucket.setdefault("wind_speed", []).append(_median(wind_values))

    def _member_value(self, member: dict[str, Any], variable: str, index: int) -> float | None:
        data = member.get("data") or {}
        values = data.get(variable) or []
        if index >= len(values):
            return None
        return _to_float(values[index])

    def _member_wind(self, member: dict[str, Any], index: int) -> float | None:
        data = member.get("data") or {}
        u = data.get("wind_u_10m") or []
        v = data.get("wind_v_10m") or []
        if index >= len(u) or index >= len(v):
            return None
        return _wind_speed(u[index], v[index])

    def _confidence(
        self,
        values: dict[str, list[float]],
        requested: list[str],
    ) -> float:
        scores: list[float] = []
        for variable in requested:
            candidates = values.get(variable, [])
            if len(candidates) < 2:
                continue
            scale = VARIABLE_SCALE.get(variable, 10.0)
            scores.append(max(0.0, 100.0 - min(100.0, _std(candidates) / scale * 80)))
        return round(sum(scores) / len(scores), 1) if scores else 70.0

    def _evaluate(
        self,
        profile: OperationProfile,
        entry: dict[str, Any],
    ) -> dict[str, Any]:
        values = entry["values"]
        precip = _to_float(values.get("precipitation_surface"))
        wind = _to_float(values.get("wind_speed"))
        temp = _to_float(values.get("temperature_2m"))
        rh = _to_float(values.get("relative_humidity_2m"))

        score = 100.0
        reasons: list[str] = []

        if precip is not None:
            ratio = min(1.0, precip / profile.precip_max)
            score -= ratio * 40
            if precip > profile.precip_max:
                reasons.append("precipitation above threshold")
        if wind is not None:
            ratio = min(1.0, wind / profile.wind_max)
            score -= ratio * 25
            if wind > profile.wind_max:
                reasons.append("wind above threshold")
        if temp is not None:
            if temp < profile.temp_min:
                score -= min(25.0, (profile.temp_min - temp) * 4)
                reasons.append("temperature below range")
            elif temp > profile.temp_max:
                score -= min(25.0, (temp - profile.temp_max) * 4)
                reasons.append("temperature above range")
        if rh is not None:
            if profile.rh_min is not None and rh < profile.rh_min:
                score -= 10
                reasons.append("humidity below range")
            if profile.rh_max is not None and rh > profile.rh_max:
                score -= 10
                reasons.append("humidity above range")

        return {
            "workable": not reasons,
            "score": round(max(0.0, min(100.0, score)), 1),
            "confidence": entry.get("confidence", 0.0),
            "reasons": reasons,
        }

    def _window(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        reasons: list[str] = []
        for entry in entries:
            reasons.extend(entry["reasons"])
        return {
            "start": entries[0]["time"],
            "end": entries[-1]["time"],
            "hours": len(entries),
            "score": round(sum(entry["score"] for entry in entries) / len(entries), 1),
            "confidence": round(
                sum(entry["confidence"] for entry in entries) / len(entries),
                1,
            ),
            "reasons": sorted(set(reasons)),
        }

    def _flag(
        self,
        kind: str,
        severity: str,
        time: str,
        value: float,
        threshold: float | None,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "type": kind,
            "severity": severity,
            "time": time,
            "value": value,
            "threshold": threshold,
            "reason": reason,
        }

    def _init_time(self, result: dict[str, Any]) -> str | None:
        forecasts = result.get("forecasts") or []
        if forecasts:
            return forecasts[0].get("initTime")
        analysis = result.get("analysisTimes") or []
        return analysis[0] if analysis else None
