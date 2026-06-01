"""
Test — AppointmentManagerView RGPD redaction (Pydantic v2).

Checks:
1. AppointmentManagerView accepts valid Appointment data including driver_license.
2. After validation, driver_license is always None (redacted).
3. After validation, driver is always None (redacted).
4. Non-driver fields (truck_license_plate, status, arrival_id) are preserved.
"""

import pytest
from datetime import datetime
from application.schemas import AppointmentManagerView, AppointmentStatusEnum


def _make_raw_appointment(**overrides):
    base = {
        "id": 1,
        "arrival_id": "PRT-0001",
        "booking_reference": "BK-2026-001",
        "truck_license_plate": "AA-00-BB",
        "terminal_id": 1,
        "status": AppointmentStatusEnum.scheduled,
        "highway_infraction": False,
        "scheduled_start_time": datetime(2026, 5, 25, 8, 0),
        # PII fields — must be redacted
        "driver_license": "PT12345678",
        "driver": {
            "drivers_license": "PT12345678",
            "name": "João Silva",
            "active": True,
        },
    }
    base.update(overrides)
    return base


@pytest.mark.unit
class TestAppointmentManagerViewRedaction:

    def test_driver_license_is_redacted(self):
        raw = _make_raw_appointment()
        view = AppointmentManagerView.model_validate(raw)
        assert view.driver_license is None, "driver_license must be None for manager view"

    def test_driver_is_redacted(self):
        raw = _make_raw_appointment()
        view = AppointmentManagerView.model_validate(raw)
        assert view.driver is None, "driver must be None for manager view"

    def test_non_driver_fields_preserved(self):
        raw = _make_raw_appointment()
        view = AppointmentManagerView.model_validate(raw)
        assert view.truck_license_plate == "AA-00-BB"
        assert view.status == AppointmentStatusEnum.scheduled
        assert view.arrival_id == "PRT-0001"
        assert view.id == 1

    def test_validates_without_driver_license(self):
        raw = _make_raw_appointment(driver_license=None, driver=None)
        view = AppointmentManagerView.model_validate(raw)
        assert view.driver_license is None
        assert view.driver is None

    def test_json_output_excludes_driver_pii(self):
        raw = _make_raw_appointment()
        view = AppointmentManagerView.model_validate(raw)
        output = view.model_dump()
        assert output["driver_license"] is None
        assert output["driver"] is None
