from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace

from fastapi.testclient import TestClient

from app import create_app


@contextmanager
def app_client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def test_admin_create_org_key_site_and_usage(settings):
    headers = {"x-admin-token": "test-admin"}
    with app_client(settings) as client:
        page = client.get("/admin")
        assert page.status_code == 200
        assert "Weather Decision / Admin" in page.text

        overview = client.get("/admin/api/overview", headers=headers)
        assert overview.status_code == 200

        org = client.post(
            "/admin/api/orgs",
            headers=headers,
            json={"name": "Acme", "monthly_quota": 10},
        )
        assert org.status_code == 200
        org_id = org.json()["id"]

        key_response = client.post(
            f"/admin/api/orgs/{org_id}/keys",
            headers=headers,
            json={"name": "agent"},
        )
        assert key_response.status_code == 200
        api_key = key_response.json()["api_key"]
        auth = {"x-api-key": api_key}

        site = client.post(
            "/v1/sites",
            headers=auth,
            json={
                "name": "Yard",
                "latitude": 41.88,
                "longitude": -87.63,
                "timezone": "America/Chicago",
                "operation_profile": "earthworks",
            },
        )
        assert site.status_code == 200
        assert site.json()["name"] == "Yard"
        assert client.get("/v1/sites", headers=auth).status_code == 200
        usage = client.get("/v1/usage", headers=auth)
        assert usage.status_code == 200
        assert usage.json()["used"] >= 1


def test_quota_is_enforced(settings):
    limited = replace(settings, quota_default=1)
    headers = {"x-admin-token": "test-admin"}
    with app_client(limited) as client:
        org = client.post(
            "/admin/api/orgs",
            headers=headers,
            json={"name": "Tiny", "monthly_quota": 1},
        ).json()
        key = client.post(
            f"/admin/api/orgs/{org['id']}/keys",
            headers=headers,
            json={"name": "agent"},
        ).json()["api_key"]
        auth = {"x-api-key": key}

        assert client.get("/v1/sites", headers=auth).status_code == 200
        blocked = client.get("/v1/sites", headers=auth)
        assert blocked.status_code == 429
        assert "retry-after" in blocked.headers
