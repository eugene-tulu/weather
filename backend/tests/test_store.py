from __future__ import annotations

from datetime import UTC, datetime, timedelta

from store import Store


async def test_store_auth_quota_sites_and_calibration(tmp_path):
    store = Store(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await store.init()
    try:
        org = await store.create_org("Acme", monthly_quota=2)
        key_id, api_key = await store.create_api_key(org.id, "test")
        context = await store.authenticate(api_key)
        assert context is not None
        assert context.org_id == org.id

        quota = await store.check_quota(org.id)
        assert quota.allowed is True

        await store.record_usage(org.id, key_id, "test", 2)
        quota = await store.check_quota(org.id)
        assert quota.allowed is False
        assert quota.used == 2

        site = await store.create_site(
            org.id, "Site A", 41.88, -87.63, "America/Chicago", "earthworks"
        )
        sites = await store.list_sites(org.id)
        assert [item.id for item in sites] == [site.id]

        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        await store.record_forecast_samples(
            org.id,
            site.id,
            "temperature_2m",
            "ensemble_median",
            [
                {"time": now.isoformat(), "value": 10.0, "probability": None},
                {
                    "time": (now + timedelta(hours=1)).isoformat(),
                    "value": 12.0,
                    "probability": None,
                },
            ],
        )
        await store.record_observation(org.id, site.id, "temperature_2m", now, 11.0)
        rows = await store.calibration_rows(
            org.id, site.id, "temperature_2m", now, now + timedelta(hours=2)
        )
        assert rows == [{"forecast": 10.0, "observed": 11.0, "probability": None}]

        overview = await store.overview()
        assert overview["orgs"][0]["name"] == "Acme"
        assert overview["sites"] == 1
    finally:
        await store.close()
