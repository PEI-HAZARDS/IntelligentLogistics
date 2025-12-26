#!/usr/bin/env python3
"""
Unit Tests for Data Module Services
Run with: pytest tests/test_services.py -v

Simple unit tests using mocks - no running services required.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime

import sys
sys.path.insert(0, '..')


# ============================================================================
# DRIVER SERVICE TESTS
# ============================================================================

class TestDriverService:
    """Unit tests for driver authentication"""

    def test_authenticate_driver_not_found(self, mock_db):
        """Driver not found returns None"""
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        from services.driver_service import authenticate_driver
        result = authenticate_driver(mock_db, "INVALID", "password")
        
        assert result is None

    def test_authenticate_driver_inactive(self, mock_db, mock_driver):
        """Inactive driver returns None"""
        mock_driver.active = False
        mock_db.query.return_value.filter.return_value.first.return_value = mock_driver
        
        from services.driver_service import authenticate_driver
        result = authenticate_driver(mock_db, "PT12345678", "password")
        
        assert result is None

    @patch('services.driver_service.verify_password')
    def test_authenticate_driver_success(self, mock_verify, mock_db, mock_driver):
        """Valid credentials return driver"""
        mock_verify.return_value = True
        mock_db.query.return_value.filter.return_value.first.return_value = mock_driver
        
        from services.driver_service import authenticate_driver
        result = authenticate_driver(mock_db, "PT12345678", "password")
        
        assert result is not None
        assert result.drivers_license == "PT12345678"

    def test_claim_invalid_pin(self, mock_db):
        """Invalid PIN returns error"""
        mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = None
        
        from services.driver_service import claim_appointment_by_pin
        appointment, error = claim_appointment_by_pin(mock_db, "PT12345678", "INVALID")
        
        assert appointment is None
        assert "Invalid" in error


# ============================================================================
# ARRIVAL SERVICE TESTS
# ============================================================================

class TestArrivalService:
    """Unit tests for arrival/appointment service"""

    def test_get_appointments_empty(self, mock_db):
        """Empty list when no appointments"""
        mock_db.query.return_value.options.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []
        
        from services.arrival_service import get_appointments
        result = get_appointments(mock_db, skip=0, limit=10)
        
        assert result == []

    def test_get_appointment_by_id_found(self, mock_db, mock_appointment):
        """Returns appointment when found"""
        mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = mock_appointment
        
        from services.arrival_service import get_appointment_by_id
        result = get_appointment_by_id(mock_db, 1)
        
        assert result is not None
        assert result.id == 1

    def test_get_appointment_by_id_not_found(self, mock_db):
        """Returns None when not found"""
        mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = None
        
        from services.arrival_service import get_appointment_by_id
        result = get_appointment_by_id(mock_db, 999)
        
        assert result is None


# ============================================================================
# WORKER SERVICE TESTS
# ============================================================================

class TestWorkerService:
    """Unit tests for worker authentication"""

    def test_authenticate_worker_not_found(self, mock_db):
        """Worker not found returns None"""
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        from services.worker_service import authenticate_worker
        result, role = authenticate_worker(mock_db, "invalid@test.com", "password")
        
        assert result is None

    def test_get_workers_empty(self, mock_db):
        """Empty list when no workers"""
        mock_db.query.return_value.filter.return_value.offset.return_value.limit.return_value.all.return_value = []
        
        from services.worker_service import get_workers
        result = get_workers(mock_db, skip=0, limit=10)
        
        assert result == []


# ============================================================================
# ALERT SERVICE TESTS
# ============================================================================

class TestAlertService:
    """Unit tests for alert service"""

    def test_get_alerts_empty(self, mock_db):
        """Empty list when no alerts"""
        mock_db.query.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []
        
        from services.alert_service import get_alerts
        result = get_alerts(mock_db, skip=0, limit=10)
        
        assert result == []

    def test_get_adr_codes(self):
        """ADR codes dictionary is not empty"""
        from services.alert_service import get_adr_reference_codes
        result = get_adr_reference_codes()
        
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_get_kemler_codes(self):
        """Kemler codes dictionary is not empty"""
        from services.alert_service import get_kemler_reference_codes
        result = get_kemler_reference_codes()
        
        assert isinstance(result, dict)
        assert len(result) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
