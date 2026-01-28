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
