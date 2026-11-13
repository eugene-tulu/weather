from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FORECAST_PRODUCTS = {
    "noaa-gfs-forecast",
    "noaa-hrrr-forecast-48-hour",
    "ecmwf-aifs-single-forecast",
    "dwd-icon-eu-forecast-5-day",
    "noaa-gefs-forecast-35-day",
    "ecmwf-ifs-ens-forecast-15-day-0-25-degree",
}

ANALYSIS_PRODUCTS = {
    "noaa-gfs-analysis",
    "noaa-hrrr-analysis",
}

ALL_PRODUCTS = FORECAST_PRODUCTS | ANALYSIS_PRODUCTS

VARIABLES = {
    "temperature_2m",
    "total_precipitation",
    "wind_speed",
    "wind_u_10m",
    "wind_v_10m",
    "cloud_cover",
    "relative_humidity_2m",
    "surface_pressure",
    "boundary_layer_height",
}


def _validate_products(values: list[str], allowed: set[str], kind: str) -> list[str]:
    if not values:
        raise ValueError("at least one product is required")
    if len(values) > 10:
        raise ValueError("at most 10 products are allowed")
    if len(set(values)) != len(values):
        raise ValueError("duplicate products are not allowed")
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ValueError(f"unsupported {kind} product(s): {', '.join(unknown)}")
    return values


def _validate_variables(values: list[str]) -> list[str]:
    if not values:
        raise ValueError("at least one variable is required")
    if len(values) > 25:
        raise ValueError("at most 25 variables are allowed")
    if len(set(values)) != len(values):
        raise ValueError("duplicate variables are not allowed")
    unknown = sorted(set(values) - VARIABLES)
    if unknown:
        raise ValueError(f"unsupported variable(s): {', '.join(unknown)}")
    return values


def _require_timezone(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        raise ValueError("timestamps must include a timezone offset")
    return value


class PointQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    products: list[str] = Field(min_length=1, max_length=10)
    variables: list[str] = Field(min_length=1, max_length=25)
    maxLeadTimeHours: int = Field(default=24, ge=1, le=840)
    initTime: datetime | None = None

    @field_validator("products")
    @classmethod
    def check_products(cls, values: list[str]) -> list[str]:
        return _validate_products(values, FORECAST_PRODUCTS, "forecast")

    @field_validator("variables")
    @classmethod
    def check_variables(cls, values: list[str]) -> list[str]:
        return _validate_variables(values)

    @field_validator("initTime", mode="before")
    @classmethod
    def allow_latest_init_time(cls, value: datetime | str | None) -> datetime | str | None:
        if value == "latest":
            return None
        return value

    @field_validator("initTime")
    @classmethod
    def check_init_time(cls, value: datetime | None) -> datetime | None:
        return _require_timezone(value)


class AnalysisQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    products: list[str] = Field(min_length=1, max_length=10)
    variables: list[str] = Field(min_length=1, max_length=25)
    startTime: datetime
    endTime: datetime

    @field_validator("products")
    @classmethod
    def check_products(cls, values: list[str]) -> list[str]:
        return _validate_products(values, ANALYSIS_PRODUCTS, "analysis")

    @field_validator("variables")
    @classmethod
    def check_variables(cls, values: list[str]) -> list[str]:
        return _validate_variables(values)

    @field_validator("startTime", "endTime")
    @classmethod
    def check_time(cls, value: datetime) -> datetime:
        return _require_timezone(value)  # type: ignore[return-value]

    @model_validator(mode="after")
    def check_window(self) -> AnalysisQuery:
        if self.endTime <= self.startTime:
            raise ValueError("endTime must be after startTime")
        if self.endTime - self.startTime > timedelta(days=31):
            raise ValueError("analysis window must be 31 days or less")
        return self
