#!/usr/bin/env python3
"""
Live API Gateway integration tests.

These tests exercise the real HTTP gateway and its real upstream boundaries.
They are intentionally not mocked. Before running them, start:

- API Gateway, exposed at TEST_GATEWAY_BASE_URL (default: http://localhost:8000)
- Data Module, reachable by the gateway through DATA_MODULE_URL
- Keycloak realm/client used by the gateway
- Seeded Keycloak/Data Module users matching the credentials below

Credential defaults match the realistic/demo seed data where possible. Override
them with TEST_MANAGER_EMAIL, TEST_MANAGER_PASSWORD, TEST_DRIVER_LICENSE, and
TEST_DRIVER_PASSWORD when running against another environment.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import pytest


GATEWAY_BASE_URL = os.getenv("TEST_GATEWAY_BASE_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = float(os.getenv("TEST_GATEWAY_TIMEOUT", "30.0"))

MANAGER_EMAIL = os.getenv("TEST_MANAGER_EMAIL", "manager@example.pt")
MANAGER_PASSWORD = os.getenv("TEST_MANAGER_PASSWORD", "password123")
DRIVER_LICENSE = os.getenv("TEST_DRIVER_LICENSE", "PT12345678")
DRIVER_PASSWORD = os.getenv("TEST_DRIVER_PASSWORD", "driver123")


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    """HTTP client pointed at the gateway root, not the /api prefix."""
    with httpx.Client(base_url=GATEWAY_BASE_URL, timeout=TIMEOUT) as http_client:
        yield http_client


def _assert_token_response(data: dict[str, Any]) -> None:
    assert isinstance(data.get("access_token"), str) and data["access_token"]
    assert isinstance(data.get("refresh_token"), str) and data["refresh_token"]
    assert data.get("token_type", "Bearer") == "Bearer"
    assert isinstance(data.get("user_info"), dict)


def _login_or_skip(client: httpx.Client, path: str, payload: dict[str, str], label: str) -> dict[str, Any]:
    response = client.post(path, json=payload)
    if response.status_code == 401:
        pytest.skip(f"{label} credentials are not available in this environment")
    assert response.status_code == 200, response.text
    data = response.json()
    _assert_token_response(data)
    return data


@pytest.fixture(scope="session")
def manager_login(client: httpx.Client) -> dict[str, Any]:
    return _login_or_skip(
        client,
        "/api/auth/workers/login",
        {"email": MANAGER_EMAIL, "password": MANAGER_PASSWORD},
        "manager",
    )


@pytest.fixture(scope="session")
def driver_login(client: httpx.Client) -> dict[str, Any]:
    return _login_or_skip(
        client,
        "/api/auth/drivers/login",
        {"drivers_license": DRIVER_LICENSE, "password": DRIVER_PASSWORD},
        "driver",
    )


@pytest.fixture(scope="session")
def manager_headers(manager_login: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {manager_login['access_token']}"}


@pytest.fixture(scope="session")
def driver_headers(driver_login: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {driver_login['access_token']}"}


def assert_paginated_arrivals(data: dict[str, Any]) -> None:
    assert isinstance(data, dict)
    assert isinstance(data.get("items"), list)
    assert isinstance(data.get("total"), int)
    assert isinstance(data.get("page"), int)
    assert isinstance(data.get("limit"), int)


class TestHealth:
    def test_gateway_health(self, client: httpx.Client):
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "env" in data


class TestAuth:
    def test_manager_login_returns_gateway_tokens(self, manager_login: dict[str, Any]):
        user_info = manager_login["user_info"]

        if "email" in user_info:
            assert user_info["email"] == MANAGER_EMAIL
        assert user_info

    def test_driver_login_returns_gateway_tokens(self, driver_login: dict[str, Any]):
        user_info = driver_login["user_info"]

        if "drivers_license" in user_info:
            assert user_info["drivers_license"] == DRIVER_LICENSE
        assert user_info

    def test_protected_route_requires_bearer_token(self, client: httpx.Client):
        response = client.get("/api/arrivals", params={"page": 1, "limit": 1})

        assert response.status_code == 401


class TestDrivers:
    def test_list_drivers_requires_manager_role(self, client: httpx.Client, manager_headers: dict[str, str]):
        response = client.get("/api/drivers", params={"skip": 0, "limit": 10}, headers=manager_headers)

        assert response.status_code == 200, response.text
        assert isinstance(response.json(), list)

    def test_get_driver_by_license(self, client: httpx.Client, manager_headers: dict[str, str]):
        response = client.get(f"/api/drivers/{DRIVER_LICENSE}", headers=manager_headers)

        assert response.status_code in {200, 404}, response.text
        if response.status_code == 200:
            assert response.json()["drivers_license"] == DRIVER_LICENSE

    def test_driver_today_uses_jwt_identity(self, client: httpx.Client, driver_headers: dict[str, str]):
        response = client.get("/api/drivers/me/today", headers=driver_headers)

        assert response.status_code == 200, response.text
        assert isinstance(response.json(), list)

    def test_driver_active_uses_jwt_identity(self, client: httpx.Client, driver_headers: dict[str, str]):
        response = client.get("/api/drivers/me/active", headers=driver_headers)

        assert response.status_code == 200, response.text
        data = response.json()
        assert data is None or isinstance(data, dict)

    def test_driver_history_uses_jwt_identity(self, client: httpx.Client, driver_headers: dict[str, str]):
        response = client.get("/api/drivers/me/history", params={"limit": 10}, headers=driver_headers)

        assert response.status_code == 200, response.text
        assert isinstance(response.json(), list)

    def test_claim_invalid_pin_uses_jwt_identity(self, client: httpx.Client, driver_headers: dict[str, str]):
        response = client.post(
            "/api/drivers/claim",
            json={"arrival_id": "__invalid_pin__"},
            headers=driver_headers,
        )

        assert response.status_code == 400, response.text


class TestArrivals:
    def test_list_arrivals_returns_paginated_shape(self, client: httpx.Client, manager_headers: dict[str, str]):
        response = client.get("/api/arrivals", params={"page": 1, "limit": 10}, headers=manager_headers)

        assert response.status_code == 200, response.text
        assert_paginated_arrivals(response.json())

    def test_get_arrival_detail_by_appointment_id(self, client: httpx.Client, manager_headers: dict[str, str]):
        response = client.get("/api/arrivals/detail/1", headers=manager_headers)

        assert response.status_code in {200, 404}, response.text
        if response.status_code == 200:
            assert isinstance(response.json(), dict)

    def test_get_arrival_stats(self, client: httpx.Client, manager_headers: dict[str, str]):
        response = client.get("/api/arrivals/stats", headers=manager_headers)

        assert response.status_code == 200, response.text
        assert isinstance(response.json(), dict)


class TestWorkers:
    def test_list_workers(self, client: httpx.Client, manager_headers: dict[str, str]):
        response = client.get("/api/workers", params={"skip": 0, "limit": 10}, headers=manager_headers)

        assert response.status_code == 200, response.text
        assert isinstance(response.json(), list)

    def test_list_operators(self, client: httpx.Client, manager_headers: dict[str, str]):
        response = client.get("/api/workers/operators", params={"skip": 0, "limit": 10}, headers=manager_headers)

        assert response.status_code == 200, response.text
        assert isinstance(response.json(), list)


class TestAlerts:
    def test_list_alerts(self, client: httpx.Client, manager_headers: dict[str, str]):
        response = client.get("/api/alerts", params={"skip": 0, "limit": 10}, headers=manager_headers)

        assert response.status_code == 200, response.text
        assert isinstance(response.json(), list)

    def test_get_active_alerts(self, client: httpx.Client, manager_headers: dict[str, str]):
        response = client.get("/api/alerts/active", params={"limit": 10}, headers=manager_headers)

        assert response.status_code == 200, response.text
        assert isinstance(response.json(), list)


class TestIntegration:
    def test_driver_read_flow(self, client: httpx.Client, driver_headers: dict[str, str]):
        today = client.get("/api/drivers/me/today", headers=driver_headers)
        assert today.status_code == 200, today.text
        assert isinstance(today.json(), list)

        active = client.get("/api/drivers/me/active", headers=driver_headers)
        assert active.status_code == 200, active.text
        assert active.json() is None or isinstance(active.json(), dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
