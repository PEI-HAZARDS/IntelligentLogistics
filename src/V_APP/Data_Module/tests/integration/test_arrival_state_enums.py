"""
Tests for arrival state enumerations (BR-15, BR-16).

BR-15 — appointment status must be one of the defined persisted values.
         Implemented as `appointment_status` PG enum:
         {scheduled, in_transit, in_process, completed, canceled}
         Sub-states (delayed, unloading, in_port) are computed, never stored.

BR-16 — visit/delivery state must be one of the defined values.
         Implemented as `delivery_status` PG enum:
         {in_port, unloading, done}
         'not_started' removed — Visit is only created on port entry, so initial
         state is always 'in_port'.

Test layers:
  1. Structural — sql_models.py declares the enum values; schemas.py mirrors them.
  2. Integration — inserting a row with an invalid status value raises an error
     from PostgreSQL (type mismatch / invalid enum label).

Integration tests require PostgreSQL (docker-compose up -d).

Run:
    PYTHONPATH=. pytest tests/integration/test_arrival_state_enums.py -v
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

_SCHEMAS_PATH = (
    pathlib.Path(__file__).parent.parent.parent
    / "application" / "schemas.py"
)

# ---------------------------------------------------------------------------
# Expected enum members (post-v4 refactor)
# ---------------------------------------------------------------------------

# Persisted appointment states — 'delayed' and 'unloading' are computed sub-states only.
_APPOINTMENT_STATUSES = {
    "scheduled", "in_transit", "in_process", "completed", "canceled",
}

# Persisted visit/delivery states — 'not_started' and 'completed' removed.
# Visit is only created on port entry, so initial state is always 'in_port'.
_DELIVERY_STATUSES = {"in_port", "unloading", "done"}

# Sub-states that must NOT appear as persisted enum values
_APPOINTMENT_COMPUTED_SUBSTATES = {"unloading", "delayed"}
_DELIVERY_REMOVED_VALUES = {"completed", "not_started"}


# ---------------------------------------------------------------------------
# 1. Structural guards (no running services required)
# ---------------------------------------------------------------------------

def test_appointment_status_enum_declared_in_sql_models():
    """sql_models.py must declare appointment_status with all BR-15 persisted values."""
    src = _MODELS_PATH.read_text()
    assert "appointment_status" in src, (
        "appointment_status enum not declared in sql_models.py"
    )
    for value in _APPOINTMENT_STATUSES:
        assert f"'{value}'" in src or f'"{value}"' in src, (
            f"appointment_status enum is missing value '{value}' (BR-15)"
        )


def test_appointment_status_enum_excludes_computed_substates():
    """'unloading' and 'delayed' must not be persisted enum values (computed only)."""
    src = _MODELS_PATH.read_text()
    # Find the SEnum declaration for appointment_status
    start = src.find("appointment_status_enum = SEnum(")
    end = src.find(")", start)
    block = src[start:end]
    for substate in _APPOINTMENT_COMPUTED_SUBSTATES:
        assert f"'{substate}'" not in block and f'"{substate}"' not in block, (
            f"'{substate}' must not be a persisted appointment_status value — "
            "it is a computed sub-state (BR-15 refactor)"
        )


def test_delivery_status_enum_declared_in_sql_models():
    """sql_models.py must declare delivery_status with all BR-16 values."""
    src = _MODELS_PATH.read_text()
    assert "delivery_status" in src, (
        "delivery_status enum not declared in sql_models.py"
    )
    for value in _DELIVERY_STATUSES:
        assert f"'{value}'" in src or f'"{value}"' in src, (
            f"delivery_status enum is missing value '{value}' (BR-16)"
        )


def test_delivery_status_enum_excludes_old_completed():
    """'completed' must not be a delivery_status value — replaced by 'done' (BR-16 refactor)."""
    src = _MODELS_PATH.read_text()
    start = src.find("delivery_status_enum = SEnum(")
    end = src.find(")", start)
    block = src[start:end]
    assert "'completed'" not in block and '"completed"' not in block, (
        "'completed' was removed from delivery_status enum — use 'done' instead (BR-16)"
    )


def test_delivery_status_enum_excludes_not_started():
    """'not_started' must not be a delivery_status value.
    Visit is only created on port entry — initial state is always 'in_port' (BR-16 refactor)."""
    src = _MODELS_PATH.read_text()
    start = src.find("delivery_status_enum = SEnum(")
    end = src.find(")", start)
    block = src[start:end]
    assert "'not_started'" not in block and '"not_started"' not in block, (
        "'not_started' was removed from delivery_status enum — "
        "Visit initial state is 'in_port' (BR-16 refactor)"
    )


def test_appointment_status_enum_mirrored_in_schemas():
    """AppointmentStatusEnum in schemas.py must expose the persisted set only."""
    src = _SCHEMAS_PATH.read_text()
    start = src.find("class AppointmentStatusEnum")
    end = src.find("\nclass ", start + 1)
    block = src[start:end] if end != -1 else src[start:]

    for value in _APPOINTMENT_STATUSES:
        assert f'"{value}"' in block or f"'{value}'" in block, (
            f"AppointmentStatusEnum in schemas.py is missing '{value}' (BR-15)"
        )
    for substate in _APPOINTMENT_COMPUTED_SUBSTATES:
        assert f'"{substate}"' not in block and f"'{substate}'" not in block, (
            f"AppointmentStatusEnum must not contain computed sub-state '{substate}'"
        )


def test_delivery_status_enum_mirrored_in_schemas():
    """DeliveryStatusEnum in schemas.py must expose the same set as the PG enum."""
    src = _SCHEMAS_PATH.read_text()
    start = src.find("class DeliveryStatusEnum")
    end = src.find("\nclass ", start + 1)
    block = src[start:end] if end != -1 else src[start:]

    for value in _DELIVERY_STATUSES:
        assert f'"{value}"' in block or f"'{value}'" in block, (
            f"DeliveryStatusEnum in schemas.py is missing '{value}' (BR-16)"
        )
    for removed in _DELIVERY_REMOVED_VALUES:
        assert f'"{removed}"' not in block and f"'{removed}'" not in block, (
            f"DeliveryStatusEnum must not contain removed value '{removed}' (BR-16 refactor)"
        )


def test_invalid_appointment_status_rejected_by_enum():
    """AppointmentStatusEnum must not accept values outside the defined persisted set."""
    from application.schemas import AppointmentStatusEnum

    valid_members = {e.value for e in AppointmentStatusEnum}
    assert valid_members == _APPOINTMENT_STATUSES, (
        f"AppointmentStatusEnum members {valid_members} do not match "
        f"expected {_APPOINTMENT_STATUSES} (BR-15)"
    )

    import pytest as _pytest
    with _pytest.raises((ValueError, KeyError)):
        AppointmentStatusEnum("UNKNOWN_STATUS")

    # Computed sub-states must also be rejected as enum values
    for substate in _APPOINTMENT_COMPUTED_SUBSTATES:
        with _pytest.raises((ValueError, KeyError)):
            AppointmentStatusEnum(substate)


def test_invalid_delivery_status_rejected_by_enum():
    """DeliveryStatusEnum must not accept values outside the defined set."""
    from application.schemas import DeliveryStatusEnum

    valid_members = {e.value for e in DeliveryStatusEnum}
    assert valid_members == _DELIVERY_STATUSES, (
        f"DeliveryStatusEnum members {valid_members} do not match "
        f"expected {_DELIVERY_STATUSES} (BR-16)"
    )

    import pytest as _pytest
    with _pytest.raises((ValueError, KeyError)):
        DeliveryStatusEnum("UNKNOWN_STATE")
    with _pytest.raises((ValueError, KeyError)):
        DeliveryStatusEnum("completed")


# ---------------------------------------------------------------------------
# 2. Integration — PG rejects invalid enum values at the DB level
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_pg_rejects_invalid_appointment_status(pg_session):
    """Inserting a row with an invalid appointment_status value must raise from PostgreSQL."""
    from sqlalchemy import text
    from sqlalchemy.exc import DataError, ProgrammingError

    with pytest.raises((DataError, ProgrammingError)):
        pg_session.execute(text(
            "INSERT INTO chegadas_diarias (status) VALUES ('NOT_A_REAL_STATUS')"
        ))
        pg_session.flush()


@pytest.mark.integration
def test_pg_rejects_invalid_delivery_status(pg_session):
    """Inserting a row with an invalid delivery_status value must raise from PostgreSQL."""
    from sqlalchemy import text
    from sqlalchemy.exc import DataError, ProgrammingError

    with pytest.raises((DataError, ProgrammingError)):
        pg_session.execute(text(
            "INSERT INTO visitas (state) VALUES ('NOT_A_REAL_STATE')"
        ))
        pg_session.flush()


@pytest.mark.integration
def test_all_valid_appointment_statuses_accepted_by_orm():
    """SQLAlchemy ORM must accept all defined appointment_status values without raising."""
    from infrastructure.persistence.sql_models import Appointment
    from infrastructure.persistence.postgres import SessionLocal

    session = SessionLocal()
    try:
        for status in _APPOINTMENT_STATUSES:
            session.query(Appointment).filter(
                Appointment.status == status
            ).count()
    finally:
        session.close()
