#!/usr/bin/env python3
"""
API Gateway Tests - Simple service tests
Run with: pytest tests/test_gateway.py -v
"""

import pytest
import httpx
import os

# Base URL for tests
BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000/api")
TIMEOUT = 30.0


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    """Creates HTTP client for tests"""
    return httpx.Client(base_url=BASE_URL, timeout=TIMEOUT)


# ============================================================================
# HEALTH CHECK
# ============================================================================

class TestHealth:
    """Health check tests"""

    def test_gateway_health(self, client: httpx.Client):
        """Verifies API Gateway is responding"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


# ============================================================================
# DRIVERS
# ============================================================================

class TestDrivers:
    """Tests for drivers endpoints via gateway"""

    def test_driver_login(self, client: httpx.Client):
        """Tests driver login"""
        response = client.post(
            "/drivers/login",
            json={
                "drivers_license": "PT12345678",
                "password": "driver123"
            }
        )
        assert response.status_code in [200, 401]
        if response.status_code == 200:
            data = response.json()
            assert "drivers_license" in data
            assert data["drivers_license"] == "PT12345678"

    def test_driver_login_invalid(self, client: httpx.Client):
        """Tests invalid driver login"""
        response = client.post(
            "/drivers/login",
            json={
                "drivers_license": "INVALID",
                "password": "wrong"
            }
        )
        assert response.status_code == 401

    def test_list_drivers(self, client: httpx.Client):
        """Lists drivers"""
        response = client.get("/drivers?skip=0&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_driver(self, client: httpx.Client):
        """Gets specific driver"""
        response = client.get("/drivers/PT12345678")
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert data["drivers_license"] == "PT12345678"

    def test_get_driver_today_arrivals(self, client: httpx.Client):
        """Gets driver's today appointments"""
        response = client.get("/drivers/me/today?drivers_license=PT12345678")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_driver_active(self, client: httpx.Client):
        """Gets driver's active appointment"""
        response = client.get("/drivers/me/active?drivers_license=PT12345678")
        assert response.status_code == 200

    def test_get_driver_history(self, client: httpx.Client):
        """Gets driver's history"""
        response = client.get("/drivers/me/history?drivers_license=PT12345678&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_claim_with_pin(self, client: httpx.Client):
        """Tests claiming with PIN"""
        response = client.post(
            "/drivers/claim?drivers_license=PT12345678",
            json={"arrival_id": "PRT-0001"}
        )
        # 200 if valid, 400 if not found or not in sequence
        assert response.status_code in [200, 400]


# ============================================================================
# ARRIVALS
# ============================================================================

class TestArrivals:
    """Tests for arrivals endpoints via gateway"""

    def test_list_arrivals(self, client: httpx.Client):
        """Lists arrivals"""
        response = client.get("/arrivals?skip=0&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_arrival_by_id(self, client: httpx.Client):
        """Gets arrival by ID"""
        response = client.get("/arrivals/1")
        assert response.status_code in [200, 404]

    def test_get_arrival_stats(self, client: httpx.Client):
        """Gets arrival statistics"""
        response = client.get("/arrivals/stats")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)


# ============================================================================
# WORKERS
# ============================================================================

class TestWorkers:
    """Tests for workers endpoints via gateway"""

    def test_worker_login(self, client: httpx.Client):
        """Tests worker login"""
        response = client.post(
            "/workers/login",
            json={
                "email": "worker@porto.pt",
                "password": "password123"
            }
        )
        assert response.status_code in [200, 401]

    def test_list_workers(self, client: httpx.Client):
        """Lists workers"""
        response = client.get("/workers?skip=0&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


# ============================================================================
# ALERTS
# ============================================================================

class TestAlerts:
    """Tests for alerts endpoints via gateway"""

    def test_list_alerts(self, client: httpx.Client):
        """Lists alerts"""
        response = client.get("/alerts?skip=0&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_active_alerts(self, client: httpx.Client):
        """Gets active alerts"""
        response = client.get("/alerts/active?limit=10")
        assert response.status_code == 200


# ============================================================================
# INTEGRATION
# ============================================================================

class TestIntegration:
    """Integration tests"""

    def test_driver_flow(self, client: httpx.Client):
        """Tests complete driver flow"""
        # 1. Login
        login = client.post(
            "/drivers/login",
            json={"drivers_license": "PT12345678", "password": "driver123"}
        )
        if login.status_code != 200:
            pytest.skip("Driver not in DB")

        # 2. View today's deliveries
        today = client.get("/drivers/me/today?drivers_license=PT12345678")
        assert today.status_code == 200

        # 3. View active
        active = client.get("/drivers/me/active?drivers_license=PT12345678")
        assert active.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
