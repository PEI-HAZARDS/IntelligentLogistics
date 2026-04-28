"""
Tests for Driver-Vehicle temporal history (BR-52).

BR-52 — Condutor_Veiculo (driver-vehicle assignment) must record temporal
         history via data_inicio / data_fim date columns, allowing multiple
         historical assignments per driver-vehicle pair.

Audit finding: no DriverVehicle ORM model or PG table exists in the current
implementation.  Driver-vehicle linkage is inferred via the FK chain
appointment → driver + appointment → truck, with no history tracking.
This file documents the gap as xfail and provides the contract that a
future DriverVehicle table must satisfy.

Structural tests run without running services.

Run:
    PYTHONPATH=. pytest tests/integration/test_driver_vehicle_history.py -v
"""

import pathlib
import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_MODELS_PATH = (
    pathlib.Path(__file__).parent.parent.parent
    / "infrastructure" / "persistence" / "sql_models.py"
)


# ---------------------------------------------------------------------------
# 1. Gap documentation
# ---------------------------------------------------------------------------

def test_driver_vehicle_model_exists():
    """BR-52: sql_models.py must have a DriverVehicle model with temporal columns."""
    src = _MODELS_PATH.read_text()
    assert "class DriverVehicle(Base):" in src or "class CondutorVeiculo(Base):" in src, (
        "No DriverVehicle ORM model in sql_models.py (BR-52)"
    )


def test_driver_vehicle_has_temporal_columns():
    """
    BR-52: the DriverVehicle model must have start_date and end_date columns.
    """
    src = _MODELS_PATH.read_text()
    start = src.find("class DriverVehicle(Base):")
    end = src.find("\nclass ", start + 1)
    block = src[start:end] if start != -1 and end != -1 else ""
    assert "start_date" in block or "data_inicio" in block, (
        "DriverVehicle model must have a start_date column (BR-52)"
    )
    assert "end_date" in block or "data_fim" in block, (
        "DriverVehicle model must have an end_date (nullable) column (BR-52)"
    )


# ---------------------------------------------------------------------------
# 2. Current implementation — verify FK chain is consistent
# ---------------------------------------------------------------------------

def test_appointment_links_driver_and_truck():
    """
    Until DriverVehicle exists, driver-vehicle linkage is via appointment.
    Confirm both FKs are present in the Appointment model.
    """
    src = _MODELS_PATH.read_text()
    appt_start = src.find("class Appointment(Base):")
    appt_end = src.find("\nclass ", appt_start + 1)
    appt_src = src[appt_start:appt_end]

    assert "driver_license" in appt_src or "drivers_license" in appt_src, (
        "Appointment must link to driver (BR-52 interim)"
    )
    assert "truck_license_plate" in appt_src, (
        "Appointment must link to truck (BR-52 interim)"
    )


def test_driver_vehicle_relationship_derivable_from_appointments():
    """
    Without a dedicated DriverVehicle table, the assignment history can be
    derived by querying appointment grouped by (driver_license, truck_license_plate).
    This test confirms the columns exist for such a query.
    """
    src = _MODELS_PATH.read_text()
    assert "scheduled_start_time" in src, (
        "appointment.scheduled_start_time is required to derive assignment history "
        "in the absence of a dedicated DriverVehicle table (BR-52 interim)"
    )


# ---------------------------------------------------------------------------
# 3. Contract tests for when DriverVehicle IS implemented
#    These are skipped now and will run once the model exists.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def driver_vehicle_model():
    """Import DriverVehicle model; skip if not yet implemented."""
    try:
        from infrastructure.persistence.sql_models import DriverVehicle
        return DriverVehicle
    except ImportError:
        pytest.skip("DriverVehicle model not yet implemented (BR-52)")


@pytest.mark.integration
def test_driver_vehicle_end_date_is_nullable(driver_vehicle_model, pg_session):
    """
    end_date must be nullable — a NULL end_date means the assignment is current.
    """
    col = driver_vehicle_model.__table__.c.get("end_date")
    if col is None:
        col = driver_vehicle_model.__table__.c.get("data_fim")
    assert col is not None, "end_date / data_fim column not found"
    assert col.nullable, "end_date must be nullable (current assignment has no end date)"
