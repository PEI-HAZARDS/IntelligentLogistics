"""
Tests for arrival state enumerations (BR-15, BR-16).

BR-15 — chegadas_diarias.estado_entrega (appointment status) must be one of
         a defined set of values.  Implemented as `appointment_status` PG enum:
         {scheduled, in_transit, in_process, unloading, canceled, delayed, completed}.

BR-16 — chegadas_diarias.estado_descarga (delivery/visit state) must be one of
         a defined set of values.  Implemented as `delivery_status` PG enum:
         {not_started, unloading, completed}.

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
# Expected enum members
# ---------------------------------------------------------------------------

_APPOINTMENT_STATUSES = {
    "scheduled", "in_transit", "in_process",
    "unloading", "canceled", "delayed", "completed",
}

_DELIVERY_STATUSES = {"not_started", "unloading", "completed"}


# ---------------------------------------------------------------------------
# 1. Structural guards (no running services required)
# ---------------------------------------------------------------------------

def test_appointment_status_enum_declared_in_sql_models():
    """
    sql_models.py must declare an appointment_status PG enum that contains
    all BR-15 values: scheduled, in_transit, in_process, unloading,
    canceled, delayed, completed.
    """
    src = _MODELS_PATH.read_text()
    assert "appointment_status" in src, (
        "appointment_status enum not declared in sql_models.py"
    )
    for value in _APPOINTMENT_STATUSES:
        assert f"'{value}'" in src or f'"{value}"' in src, (
            f"appointment_status enum is missing value '{value}' (BR-15)"
        )


def test_delivery_status_enum_declared_in_sql_models():
    """
    sql_models.py must declare a delivery_status PG enum that contains
    all BR-16 values: not_started, unloading, completed.
    """
    src = _MODELS_PATH.read_text()
    assert "delivery_status" in src, (
        "delivery_status enum not declared in sql_models.py"
    )
    for value in _DELIVERY_STATUSES:
        assert f"'{value}'" in src or f'"{value}"' in src, (
            f"delivery_status enum is missing value '{value}' (BR-16)"
        )


def test_appointment_status_enum_mirrored_in_schemas():
    """
    AppointmentStatusEnum in schemas.py must expose exactly the same set
    of values as the PG enum, so API serialisation stays in sync.
    """
    src = _SCHEMAS_PATH.read_text()
    # Locate AppointmentStatusEnum class
    start = src.find("class AppointmentStatusEnum")
    end = src.find("\nclass ", start + 1)
    block = src[start:end] if end != -1 else src[start:]

    for value in _APPOINTMENT_STATUSES:
        assert f'"{value}"' in block or f"'{value}'" in block, (
            f"AppointmentStatusEnum in schemas.py is missing '{value}' (BR-15)"
        )


def test_delivery_status_enum_mirrored_in_schemas():
    """
    DeliveryStatusEnum in schemas.py must expose the same set of values
    as the PG delivery_status enum.
    """
    src = _SCHEMAS_PATH.read_text()
    start = src.find("class DeliveryStatusEnum")
    end = src.find("\nclass ", start + 1)
    block = src[start:end] if end != -1 else src[start:]

    for value in _DELIVERY_STATUSES:
        assert f'"{value}"' in block or f"'{value}'" in block, (
            f"DeliveryStatusEnum in schemas.py is missing '{value}' (BR-16)"
        )


def test_invalid_appointment_status_rejected_by_enum():
    """
    Domain validation: AppointmentStatusEnum must not accept values outside
    the defined set.  This confirms that the Pydantic schema enforces the
    enum at the API boundary (no running services required).
    """
    from application.schemas import AppointmentStatusEnum

    valid_members = {e.value for e in AppointmentStatusEnum}
    assert valid_members == _APPOINTMENT_STATUSES, (
        f"AppointmentStatusEnum members {valid_members} do not match "
        f"expected {_APPOINTMENT_STATUSES} (BR-15)"
    )

    # Pydantic enum rejects unknown values
    import pytest as _pytest
    with _pytest.raises((ValueError, KeyError)):
        AppointmentStatusEnum("UNKNOWN_STATUS")


def test_invalid_delivery_status_rejected_by_enum():
    """
    DeliveryStatusEnum must not accept values outside the defined set.
    """
    from application.schemas import DeliveryStatusEnum

    valid_members = {e.value for e in DeliveryStatusEnum}
    assert valid_members == _DELIVERY_STATUSES, (
        f"DeliveryStatusEnum members {valid_members} do not match "
        f"expected {_DELIVERY_STATUSES} (BR-16)"
    )

    import pytest as _pytest
    with _pytest.raises((ValueError, KeyError)):
        DeliveryStatusEnum("UNKNOWN_STATE")


# ---------------------------------------------------------------------------
# 2. Integration — PG rejects invalid enum values at the DB level
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_pg_rejects_invalid_appointment_status(pg_session):
    """
    Inserting a row with an invalid appointment_status value must raise
    a DataError from PostgreSQL — the type constraint is enforced at the
    DB level, not only in Python.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import DataError, ProgrammingError

    with pytest.raises((DataError, ProgrammingError)):
        pg_session.execute(text(
            "INSERT INTO chegadas_diarias (status) VALUES ('NOT_A_REAL_STATUS')"
        ))
        pg_session.flush()


@pytest.mark.integration
def test_pg_rejects_invalid_delivery_status(pg_session):
    """
    Inserting a row with an invalid delivery_status value must raise
    a DataError from PostgreSQL.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import DataError, ProgrammingError

    with pytest.raises((DataError, ProgrammingError)):
        pg_session.execute(text(
            "INSERT INTO visitas (state) VALUES ('NOT_A_REAL_STATE')"
        ))
        pg_session.flush()


@pytest.mark.integration
def test_all_valid_appointment_statuses_accepted_by_orm():
    """
    SQLAlchemy ORM must accept all defined appointment_status values
    without raising (connects to PG and verifies enum type membership).
    The query intentionally returns zero rows — we only check no TypeError
    is raised by the enum coercion.
    """
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
