"""
Phase 3 schema tests — BR-11 alert.severity, BR-13 dock.estado,
BR-14 gate.estado, BR-52 driver_vehicle, PD-01 pending_reviews,
BR-20 appointment.arrival_id UNIQUE, driver session columns dropped.

Structural tests run without any services.
Integration tests require PostgreSQL (docker-compose up -d).

Run:
    PYTHONPATH=. pytest tests/integration/test_phase3_schema.py -v
    PYTHONPATH=. pytest tests/integration/test_phase3_schema.py -m integration -v
"""

import pathlib
import uuid

import pytest

_MODELS_PATH = (
    pathlib.Path(__file__).parent.parent.parent
    / "infrastructure" / "persistence" / "sql_models.py"
)


def _model_src(class_name: str) -> str:
    src = _MODELS_PATH.read_text()
    start = src.find(f"class {class_name}(Base):")
    end = src.find("\nclass ", start + 1)
    return src[start:end] if end != -1 else src[start:]


# ---------------------------------------------------------------------------
# Structural — no services required
# ---------------------------------------------------------------------------

def test_alert_severity_declared():
    """Alert.severity must be declared with SmallInteger and a CHECK constraint (BR-11)."""
    src = _model_src("Alert")
    assert "severity" in src, "Alert must have a severity column (BR-11)"
    assert "SmallInteger" in src, "severity must be SmallInteger (BR-11)"
    assert "chk_alert_severity" in src, "severity must have a CHECK constraint (BR-11)"


def test_gate_estado_declared():
    """Gate.estado must be declared with a CHECK constraint (BR-14)."""
    src = _model_src("Gate")
    assert "estado" in src, "Gate must have an estado column (BR-14)"
    assert "chk_gate_estado" in src, "estado must have a CHECK constraint (BR-14)"


def test_dock_estado_declared():
    """Dock.estado must be declared with a CHECK constraint (BR-13)."""
    src = _model_src("Dock")
    assert "estado" in src, "Dock must have an estado column (BR-13)"
    assert "chk_dock_estado" in src, "estado must have a CHECK constraint (BR-13)"


def test_driver_vehicle_model_exists():
    """DriverVehicle model must exist with FKs and date CHECK (BR-52)."""
    src = _MODELS_PATH.read_text()
    assert "class DriverVehicle(Base):" in src, "DriverVehicle model missing (BR-52)"
    dv_src = _model_src("DriverVehicle")
    assert "driver_license" in dv_src
    assert "truck_license_plate" in dv_src
    assert "start_date" in dv_src
    assert "end_date" in dv_src
    assert "chk_dv_dates" in dv_src


def test_pending_review_model_exists():
    """PendingReview model must exist with required fields (PD-01)."""
    src = _MODELS_PATH.read_text()
    assert "class PendingReview(Base):" in src, "PendingReview model missing (PD-01)"
    pr_src = _model_src("PendingReview")
    assert "event_id" in pr_src
    assert "truck_id" in pr_src
    assert "gate_id" in pr_src
    assert "license_plate" in pr_src
    assert "chk_pr_status" in pr_src


def test_driver_session_columns_removed():
    """driver.session_token and session_expires_at must be gone (Phase 2 auth moved to Redis)."""
    src = _model_src("Driver")
    assert "session_token" not in src, "driver.session_token must be removed (auth moved to Redis)"
    assert "session_expires_at" not in src, "driver.session_expires_at must be removed"


def test_schema_migrations_table_in_migration_sql():
    """migrationDBv3.sql must create the schema_migrations version-tracking table."""
    migration = (
        pathlib.Path(__file__).parent.parent.parent / "scripts" / "migrationDBv3.sql"
    ).read_text()
    assert "schema_migrations" in migration
    assert "CREATE TABLE IF NOT EXISTS schema_migrations" in migration


# ---------------------------------------------------------------------------
# Integration — require PostgreSQL
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_alert_severity_check_rejects_zero(pg_session):
    """Inserting an Alert with severity=0 must raise IntegrityError (BR-11)."""
    from sqlalchemy.exc import IntegrityError
    from infrastructure.persistence.sql_models import Alert

    pg_session.add(Alert(severity=0, type="generic", description="bad"))
    with pytest.raises(IntegrityError):
        pg_session.flush()
    pg_session.rollback()


@pytest.mark.integration
def test_alert_severity_check_rejects_six(pg_session):
    """Inserting an Alert with severity=6 must raise IntegrityError (BR-11)."""
    from sqlalchemy.exc import IntegrityError
    from infrastructure.persistence.sql_models import Alert

    pg_session.add(Alert(severity=6, type="generic", description="bad"))
    with pytest.raises(IntegrityError):
        pg_session.flush()
    pg_session.rollback()


@pytest.mark.integration
@pytest.mark.parametrize("sev", [1, 2, 3, 4, 5])
def test_alert_severity_valid_values_accepted(pg_session, sev):
    """Alert severities 1–5 must not raise (BR-11)."""
    from infrastructure.persistence.sql_models import Alert

    a = Alert(severity=sev, type="generic", description=f"sev-{sev}")
    pg_session.add(a)
    pg_session.flush()
    pg_session.rollback()


@pytest.mark.integration
def test_gate_estado_check_rejects_invalid(pg_session):
    """Inserting a Gate with estado='Unknown' must raise IntegrityError (BR-14)."""
    from sqlalchemy.exc import IntegrityError
    from infrastructure.persistence.sql_models import Gate

    pg_session.add(Gate(label="G-BAD", estado="Unknown"))
    with pytest.raises(IntegrityError):
        pg_session.flush()
    pg_session.rollback()


@pytest.mark.integration
@pytest.mark.parametrize("estado", ["Ativo", "Inativo"])
def test_gate_estado_valid_values_accepted(pg_session, estado):
    """Gate estado values {Ativo, Inativo} must be accepted (BR-14)."""
    from infrastructure.persistence.sql_models import Gate

    g = Gate(label=f"G-{estado}", estado=estado)
    pg_session.add(g)
    pg_session.flush()
    pg_session.rollback()


@pytest.mark.integration
def test_driver_vehicle_date_check_rejects_end_before_start(pg_session):
    """driver_vehicle with end_date < start_date must raise IntegrityError (BR-52)."""
    import datetime
    from sqlalchemy.exc import IntegrityError
    from infrastructure.persistence.sql_models import DriverVehicle

    pg_session.add(DriverVehicle(
        driver_license="LIC-NONEXISTENT",
        truck_license_plate="XX-00-XX",
        start_date=datetime.date(2026, 6, 1),
        end_date=datetime.date(2026, 5, 1),
    ))
    with pytest.raises(IntegrityError):
        pg_session.flush()
    pg_session.rollback()


@pytest.mark.integration
def test_pending_review_status_check_rejects_invalid(pg_session):
    """PendingReview with status='UNKNOWN' must raise IntegrityError (PD-01)."""
    from sqlalchemy.exc import IntegrityError
    from infrastructure.persistence.sql_models import PendingReview

    pg_session.add(PendingReview(
        event_id=uuid.uuid4(),
        truck_id="TRUCK-1",
        gate_id=1,
        license_plate="AB-12-CD",
        status="UNKNOWN",
    ))
    with pytest.raises(IntegrityError):
        pg_session.flush()
    pg_session.rollback()


@pytest.mark.integration
@pytest.mark.parametrize("status", ["PENDING", "APPROVED", "REJECTED"])
def test_pending_review_valid_statuses_accepted(pg_session, status):
    """PendingReview status values {PENDING, APPROVED, REJECTED} must be accepted (PD-01)."""
    from infrastructure.persistence.sql_models import PendingReview

    pr = PendingReview(
        event_id=uuid.uuid4(),
        truck_id="TRUCK-1",
        gate_id=1,
        license_plate="AB-12-CD",
        status=status,
    )
    pg_session.add(pr)
    pg_session.flush()
    pg_session.rollback()


@pytest.mark.integration
def test_schema_migrations_table_exists(pg_session):
    """schema_migrations table must exist after migration is applied."""
    result = pg_session.execute(
        __import__("sqlalchemy").text(
            "SELECT version FROM schema_migrations WHERE version = 3"
        )
    ).fetchone()
    assert result is not None, "v3 row missing from schema_migrations — run migrationDBv3.sql"
