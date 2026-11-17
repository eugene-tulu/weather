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
    "precipitation_surface",
    "total_cloud_cover_atmosphere",
    "relative_humidity_2m",
    "pressure_surface",
    "wind_u_10m",
    "wind_v_10m",
}

MAP_PRODUCT_IDS = {
    "noaa-gfs-forecast-virtual",
    "noaa-gfs-analysis-virtual",
    "noaa-gefs-forecast-10-day-0-25-degree-virtual",
    "noaa-gefs-forecast-16-day-0-5-degree-virtual",
    "noaa-gefs-forecast-35-day-0-5-degree-virtual",
    "noaa-gefs-analysis-0-25-degree-virtual",
    "ecmwf-aifs-single-forecast-virtual",
    "ecmwf-ifs-ens-forecast-6-day-0-25-degree-virtual",
    "ecmwf-ifs-ens-forecast-15-day-0-25-degree-virtual",
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


class SiteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    operation_profile: str = Field(default="general", max_length=64)


class SiteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    operation_profile: str | None = Field(default=None, max_length=64)


class ObservationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variable: str
    observed_time: datetime
    value: float
    source: str = Field(default="manual", min_length=1, max_length=120)

    @field_validator("variable")
    @classmethod
    def check_variable(cls, value: str) -> str:
        if value not in VARIABLES:
            raise ValueError(f"unsupported variable: {value}")
        return value

    @field_validator("observed_time")
    @classmethod
    def check_observed_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("observed_time must include a timezone offset")
        return value


class WorkabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: str = Field(min_length=1, max_length=64)
    start_time: datetime | None = None
    end_time: datetime | None = None
    horizon_hours: int = Field(default=48, ge=1, le=168)


class ForecastRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    horizon_hours: int = Field(default=48, ge=1, le=840)
    variables: list[str] | None = None

    @field_validator("variables")
    @classmethod
    def check_variables(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        unknown = sorted(set(values) - VARIABLES - {"wind_speed"})
        if unknown:
            raise ValueError(f"unsupported variable(s): {', '.join(unknown)}")
        return values


class RiskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: str = Field(default="general", max_length=64)
    horizon_hours: int = Field(default=48, ge=1, le=168)


class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    monthly_quota: int = Field(default=100_000, ge=0)


class KeyCreate(BaseModel):
    name: str = Field(default="default", min_length=1, max_length=120)
    scopes: list[str] = Field(
        default_factory=lambda: [
            "sites:read",
            "sites:write",
            "forecast:read",
            "usage:read",
        ]
    )


class QuotaUpdate(BaseModel):
    monthly_quota: int = Field(ge=0)
