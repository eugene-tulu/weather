from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    and_,
    func,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _new_id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    monthly_quota: Mapped[int] = mapped_column(Integer, default=100_000)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    prefix: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(120), default="default")
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    operation_profile: Mapped[str] = mapped_column(String(64), default="general")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    api_key_id: Mapped[str | None] = mapped_column(
        ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True
    )
    tool: Mapped[str] = mapped_column(String(120))
    units: Mapped[int] = mapped_column(Integer, default=1)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class ForecastSample(Base):
    __tablename__ = "forecast_samples"
    __table_args__ = (
        UniqueConstraint(
            "site_id",
            "variable",
            "valid_time",
            "model",
            name="uq_forecast_sample",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    variable: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(80))
    valid_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    forecast_value: Mapped[float] = mapped_column(Float)
    probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint(
            "site_id",
            "variable",
            "observed_time",
            "source",
            name="uq_observation",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), index=True)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    variable: Mapped[str] = mapped_column(String(80))
    observed_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    value: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(120), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


@dataclass(frozen=True)
class AuthContext:
    org_id: str
    org_name: str
    api_key_id: str
    scopes: tuple[str, ...]
    monthly_quota: int


@dataclass(frozen=True)
class QuotaState:
    allowed: bool
    used: int
    limit: int
    reset_at: datetime


def hash_api_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def site_to_dict(site: Site) -> dict[str, Any]:
    return {
        "id": site.id,
        "name": site.name,
        "latitude": site.latitude,
        "longitude": site.longitude,
        "timezone": site.timezone,
        "operation_profile": site.operation_profile,
        "created_at": site.created_at.isoformat(),
    }


class Store:
    def __init__(self, database_url: str) -> None:
        if database_url.startswith("sqlite+aiosqlite:///"):
            raw_path = database_url.removeprefix("sqlite+aiosqlite:///")
            if raw_path and raw_path != ":memory:":
                Path(raw_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_async_engine(database_url, pool_pre_ping=True, future=True)
        self.sessionmaker = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def init(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self.engine.dispose()

    async def ping(self) -> None:
        async with self.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def create_org(self, name: str, monthly_quota: int = 100_000) -> Org:
        async with self.sessionmaker() as session:
            org = Org(name=name, monthly_quota=monthly_quota)
            session.add(org)
            await session.commit()
            await session.refresh(org)
            return org

    async def get_org(self, org_id: str) -> Org | None:
        async with self.sessionmaker() as session:
            return await session.get(Org, org_id)

    async def update_org_quota(self, org_id: str, monthly_quota: int) -> Org | None:
        async with self.sessionmaker() as session:
            org = await session.get(Org, org_id)
            if org is None:
                return None
            org.monthly_quota = monthly_quota
            await session.commit()
            await session.refresh(org)
            return org

    async def list_orgs(self) -> list[dict[str, Any]]:
        async with self.sessionmaker() as session:
            orgs = (await session.execute(select(Org).order_by(Org.created_at))).scalars().all()
            result = []
            for org in orgs:
                summary = await self._usage_summary(session, org)
                result.append(
                    {
                        "id": org.id,
                        "name": org.name,
                        "monthly_quota": org.monthly_quota,
                        "created_at": org.created_at.isoformat(),
                        **summary,
                    }
                )
            return result

    async def create_api_key(
        self,
        org_id: str,
        name: str = "default",
        scopes: list[str] | None = None,
    ) -> tuple[str, str]:
        plaintext = f"wth_{secrets.token_urlsafe(32)}"
        async with self.sessionmaker() as session:
            key = ApiKey(
                org_id=org_id,
                key_hash=hash_api_key(plaintext),
                prefix=plaintext[:12],
                name=name,
                scopes=scopes or ["sites:read", "sites:write", "forecast:read", "usage:read"],
            )
            session.add(key)
            await session.commit()
            await session.refresh(key)
            return key.id, plaintext

    async def list_api_keys(self, org_id: str) -> list[dict[str, Any]]:
        async with self.sessionmaker() as session:
            keys = (
                (
                    await session.execute(
                        select(ApiKey).where(ApiKey.org_id == org_id).order_by(ApiKey.created_at)
                    )
                )
                .scalars()
                .all()
            )
            return [
                {
                    "id": key.id,
                    "prefix": key.prefix,
                    "name": key.name,
                    "scopes": key.scopes,
                    "created_at": key.created_at.isoformat(),
                    "last_used_at": (key.last_used_at.isoformat() if key.last_used_at else None),
                    "revoked_at": (key.revoked_at.isoformat() if key.revoked_at else None),
                }
                for key in keys
            ]

    async def revoke_api_key(self, key_id: str) -> bool:
        async with self.sessionmaker() as session:
            key = await session.get(ApiKey, key_id)
            if key is None:
                return False
            key.revoked_at = _now()
            await session.commit()
            return True

    async def authenticate(self, api_key: str) -> AuthContext | None:
        key_hash = hash_api_key(api_key)
        async with self.sessionmaker() as session:
            row = (
                await session.execute(
                    select(ApiKey, Org)
                    .join(Org, ApiKey.org_id == Org.id)
                    .where(ApiKey.key_hash == key_hash)
                )
            ).one_or_none()
            if row is None:
                return None
            key, org = row
            if key.revoked_at is not None:
                return None
            key.last_used_at = _now()
            await session.commit()
            return AuthContext(
                org_id=org.id,
                org_name=org.name,
                api_key_id=key.id,
                scopes=tuple(key.scopes or []),
                monthly_quota=org.monthly_quota,
            )

    async def check_quota(self, org_id: str) -> QuotaState:
        async with self.sessionmaker() as session:
            org = await session.get(Org, org_id)
            if org is None:
                return QuotaState(allowed=False, used=0, limit=0, reset_at=_month_start())
            used = await self._used_since(session, org_id, _month_start())
            limit = org.monthly_quota
            return QuotaState(
                allowed=limit <= 0 or used < limit,
                used=used,
                limit=limit,
                reset_at=_month_start() + timedelta(days=32),
            )

    async def record_usage(
        self,
        org_id: str,
        api_key_id: str | None,
        tool: str,
        units: int = 1,
        meta: dict[str, Any] | None = None,
    ) -> None:
        async with self.sessionmaker() as session:
            session.add(
                UsageEvent(
                    org_id=org_id,
                    api_key_id=api_key_id,
                    tool=tool,
                    units=units,
                    meta=meta or {},
                )
            )
            await session.commit()

    async def usage_summary(self, org_id: str) -> dict[str, Any]:
        async with self.sessionmaker() as session:
            org = await session.get(Org, org_id)
            if org is None:
                return {}
            return await self._usage_summary(session, org)

    async def create_site(
        self,
        org_id: str,
        name: str,
        latitude: float,
        longitude: float,
        timezone: str = "UTC",
        operation_profile: str = "general",
    ) -> Site:
        async with self.sessionmaker() as session:
            site = Site(
                org_id=org_id,
                name=name,
                latitude=latitude,
                longitude=longitude,
                timezone=timezone,
                operation_profile=operation_profile,
            )
            session.add(site)
            await session.commit()
            await session.refresh(site)
            return site

    async def list_sites(self, org_id: str) -> list[Site]:
        async with self.sessionmaker() as session:
            return list(
                (
                    await session.execute(
                        select(Site).where(Site.org_id == org_id).order_by(Site.created_at)
                    )
                )
                .scalars()
                .all()
            )

    async def get_site(self, org_id: str, site_id: str) -> Site | None:
        async with self.sessionmaker() as session:
            return (
                await session.execute(select(Site).where(Site.id == site_id, Site.org_id == org_id))
            ).scalar_one_or_none()

    async def update_site(self, org_id: str, site_id: str, **values: Any) -> Site | None:
        async with self.sessionmaker() as session:
            site = (
                await session.execute(select(Site).where(Site.id == site_id, Site.org_id == org_id))
            ).scalar_one_or_none()
            if site is None:
                return None
            for field in (
                "name",
                "latitude",
                "longitude",
                "timezone",
                "operation_profile",
            ):
                if field in values and values[field] is not None:
                    setattr(site, field, values[field])
            await session.commit()
            await session.refresh(site)
            return site

    async def delete_site(self, org_id: str, site_id: str) -> bool:
        async with self.sessionmaker() as session:
            site = (
                await session.execute(select(Site).where(Site.id == site_id, Site.org_id == org_id))
            ).scalar_one_or_none()
            if site is None:
                return False
            await session.delete(site)
            await session.commit()
            return True

    async def record_forecast_samples(
        self,
        org_id: str,
        site_id: str,
        variable: str,
        model: str,
        samples: list[dict[str, Any]],
    ) -> None:
        async with self.sessionmaker() as session:
            for sample in samples:
                valid_time = _as_utc(sample["time"])
                existing = (
                    await session.execute(
                        select(ForecastSample).where(
                            ForecastSample.site_id == site_id,
                            ForecastSample.variable == variable,
                            ForecastSample.valid_time == valid_time,
                            ForecastSample.model == model,
                        )
                    )
                ).scalar_one_or_none()
                if existing is None:
                    session.add(
                        ForecastSample(
                            org_id=org_id,
                            site_id=site_id,
                            variable=variable,
                            model=model,
                            valid_time=valid_time,
                            forecast_value=float(sample["value"]),
                            probability=(
                                float(sample["probability"])
                                if sample.get("probability") is not None
                                else None
                            ),
                        )
                    )
                else:
                    existing.forecast_value = float(sample["value"])
                    existing.probability = (
                        float(sample["probability"])
                        if sample.get("probability") is not None
                        else None
                    )
            await session.commit()

    async def record_observation(
        self,
        org_id: str,
        site_id: str,
        variable: str,
        observed_time: datetime,
        value: float,
        source: str = "manual",
    ) -> None:
        async with self.sessionmaker() as session:
            existing = (
                await session.execute(
                    select(Observation).where(
                        Observation.site_id == site_id,
                        Observation.variable == variable,
                        Observation.observed_time == _as_utc(observed_time),
                        Observation.source == source,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    Observation(
                        org_id=org_id,
                        site_id=site_id,
                        variable=variable,
                        observed_time=_as_utc(observed_time),
                        value=value,
                        source=source,
                    )
                )
            else:
                existing.value = value
            await session.commit()

    async def calibration_rows(
        self,
        org_id: str,
        site_id: str,
        variable: str,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        async with self.sessionmaker() as session:
            rows = (
                await session.execute(
                    select(
                        ForecastSample.forecast_value,
                        Observation.value,
                        ForecastSample.probability,
                    )
                    .join(
                        Observation,
                        and_(
                            Observation.site_id == ForecastSample.site_id,
                            Observation.variable == ForecastSample.variable,
                            Observation.observed_time == ForecastSample.valid_time,
                        ),
                    )
                    .where(
                        ForecastSample.org_id == org_id,
                        ForecastSample.site_id == site_id,
                        ForecastSample.variable == variable,
                        ForecastSample.valid_time >= _as_utc(start),
                        ForecastSample.valid_time <= _as_utc(end),
                    )
                    .order_by(ForecastSample.valid_time)
                )
            ).all()
            return [
                {
                    "forecast": row[0],
                    "observed": row[1],
                    "probability": row[2],
                }
                for row in rows
            ]

    async def overview(self) -> dict[str, Any]:
        async with self.sessionmaker() as session:
            orgs = await self.list_orgs()
            keys = (await session.execute(select(func.count(ApiKey.id)))).scalar_one()
            sites = (await session.execute(select(func.count(Site.id)))).scalar_one()
            recent = (
                await session.execute(
                    select(UsageEvent.tool, func.sum(UsageEvent.units))
                    .where(UsageEvent.created_at >= _now() - timedelta(days=30))
                    .group_by(UsageEvent.tool)
                    .order_by(func.sum(UsageEvent.units).desc())
                    .limit(10)
                )
            ).all()
            return {
                "orgs": orgs,
                "api_keys": keys,
                "sites": sites,
                "top_tools": [{"tool": row[0], "units": int(row[1])} for row in recent],
            }

    async def _used_since(self, session: AsyncSession, org_id: str, since: datetime) -> int:
        return int(
            (
                await session.execute(
                    select(func.coalesce(func.sum(UsageEvent.units), 0)).where(
                        UsageEvent.org_id == org_id,
                        UsageEvent.created_at >= since,
                    )
                )
            ).scalar_one()
        )

    async def _usage_summary(self, session: AsyncSession, org: Org) -> dict[str, Any]:
        used = await self._used_since(session, org.id, _month_start())
        return {
            "used": used,
            "remaining": max(0, org.monthly_quota - used) if org.monthly_quota > 0 else None,
            "period_start": _month_start().isoformat(),
        }


def _month_start() -> datetime:
    now = _now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _as_utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
