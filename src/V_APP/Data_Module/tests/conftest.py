"""
pytest configuration for Data Module tests
"""

import pytest
import os
import sys
from pathlib import Path
from unittest.mock import Mock
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

# Provide a stable test encryption key so tests that touch encrypted columns
# (Worker.email, Worker.phone, Driver.mobile_device_token) don't raise RuntimeError.
# This is a fixed test-only key — never use in production.
if not os.environ.get("ENCRYPTION_KEY"):
    # 32 bytes of 0x41 ('A'), base64url-encoded — deterministic across test runs.
    os.environ["ENCRYPTION_KEY"] = "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE="


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_db():
    """Mock database session"""
    db = Mock()
    db.commit = Mock()
    db.refresh = Mock()
    return db


@pytest.fixture
def mock_driver():
    """Mock driver"""
    driver = Mock()
    driver.drivers_license = "PT12345678"
    driver.name = "Test Driver"
    driver.password_hash = "hash"
    driver.active = True
    driver.company = Mock(name="Test Co")
    driver.company.name = "Test Co"
    return driver


@pytest.fixture
def mock_appointment():
    """Mock appointment"""
    appt = Mock()
    appt.id = 1
    appt.arrival_id = "PRT-0001"
    appt.driver_license = "PT12345678"
    appt.status = "in_transit"
    appt.truck_license_plate = "XX-XX-XX"
    return appt


@pytest.fixture
def driver_credentials():
    return {"drivers_license": "PT12345678", "password": "driver123"}


@pytest.fixture
def worker_credentials():
    return {"email": "worker@porto.pt", "password": "password123"}


# ============================================================================
# CONFIG
# ============================================================================

def pytest_configure(config):
    config.addinivalue_line("markers", "integration: integration tests")
    config.addinivalue_line("markers", "unit: unit tests")


# ============================================================================
# INTEGRATION FIXTURES
# ============================================================================

@pytest.fixture(scope="function")
def pg_session():
    """
    Real PostgreSQL session for integration tests.
    Rolls back any uncommitted state on teardown.
    Tests that need a committed row must commit explicitly and clean up.
    Requires running PostgreSQL (docker-compose up -d).
    """
    from infrastructure.persistence.postgres import SessionLocal
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()
