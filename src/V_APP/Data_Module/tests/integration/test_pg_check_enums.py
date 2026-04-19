"""
Tests for PG-level enumeration constraints (BR-11, BR-13, BR-14, BR-17).

BR-11 — alert.severidade (severity) INT 1–5.
         GAP: the Alert ORM model has no severity column; AlertPayload in
         schemas.py carries severity as an unvalidated int (no CHECK 1–5).

BR-13 — dock.estado ∈ {Ativo, Inativo}.
         Partially implemented: dock.current_usage uses operational_status_enum
         {maintenance, operational, closed} — Portuguese spec values absent.

BR-14 — gate.estado ∈ {Ativo, Inativo}.
         GAP: Gate model has no status column at all.

BR-17 — detection.origem ∈ {IA, Manual}.
         GAP: no PG detection table; detections live in MongoDB only.

Test layers:
  1. Structural — sql_models.py / schemas.py declarations (no services needed).
  2. Integration — PG enforces enum type at INSERT for implemented columns.

Run:
    PYTHONPATH=. pytest tests/integration/test_pg_check_enums.py -v
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
# 1. Structural guards
# ---------------------------------------------------------------------------

# BR-11 ─ alert severity gap

@pytest.mark.xfail(
    reason=(
        "BR-11 gap: alert.severity (severidade INT 1–5) is absent from the Alert ORM "
        "model and the PG alert table. schemas.py has AlertPayload.severity: int but "
        "no CHECK constraint enforces the 1–5 range. "
        "Fix: add severity = Column(Integer, CheckConstraint('severity >= 1 AND severity <= 5')) "
        "to the Alert model and a corresponding Pydantic Field(ge=1, le=5) validator."
    ),
    strict=True,
)
def test_alert_severity_column_exists_in_orm():
    """BR-11: Alert ORM model must have a severity column (INT 1–5)."""
    src = _MODELS_PATH.read_text()
    alert_start = src.find("class Alert(Base):")
    alert_end = src.find("\nclass ", alert_start + 1)
    alert_src = src[alert_start:alert_end] if alert_end != -1 else src[alert_start:]
    assert "severity" in alert_src, (
        "Alert ORM model must have a severity column (BR-11)"
    )


def test_alert_type_enum_declared_in_orm():
    """
    Alert type (generic, safety, problem, operational) IS enforced via
    type_alert_enum PG enum — this is what the DB actually constrains.
    """
    src = _MODELS_PATH.read_text()
    assert "type_alert" in src, "type_alert enum not found in sql_models.py"
    for value in ("generic", "safety", "problem", "operational"):
        assert f"'{value}'" in src or f'"{value}"' in src, (
            f"type_alert enum missing value '{value}'"
        )


def test_alert_type_schema_enum_matches_orm():
    """TypeAlertEnum in schemas.py must mirror the ORM type_alert values."""
    from application.schemas import TypeAlertEnum
    assert {e.value for e in TypeAlertEnum} == {"generic", "safety", "problem", "operational"}


# BR-13 ─ dock status

def test_dock_current_usage_enum_declared():
    """
    dock.current_usage uses operational_status_enum
    {maintenance, operational, closed} — the implemented constraint (BR-13 partial).
    """
    src = _MODELS_PATH.read_text()
    assert "operational_status" in src, "operational_status enum not declared"
    for value in ("maintenance", "operational", "closed"):
        assert f"'{value}'" in src, (
            f"operational_status enum missing value '{value}'"
        )
    dock_start = src.find("class Dock(Base):")
    dock_end = src.find("\nclass ", dock_start + 1)
    dock_src = src[dock_start:dock_end]
    assert "current_usage" in dock_src, (
        "Dock model must have current_usage column"
    )


@pytest.mark.xfail(
    reason=(
        "BR-13 gap: spec requires dock.estado ∈ {Ativo, Inativo} (Portuguese) "
        "but the actual enum is operational_status {maintenance, operational, closed}. "
        "The values differ from the spec. "
        "Fix: either align the spec to the English enum or add an is_active boolean column."
    ),
    strict=True,
)
def test_dock_ativo_inativo_values_present():
    """BR-13 original spec: dock status must include 'Ativo' and 'Inativo'."""
    src = _MODELS_PATH.read_text()
    assert "'Ativo'" in src or "'ativo'" in src, (
        "dock status enum missing 'Ativo' value (BR-13 original spec)"
    )


# BR-14 ─ gate status gap

@pytest.mark.xfail(
    reason=(
        "BR-14 gap: Gate model has no status column. "
        "The spec requires gate.estado ∈ {Ativo, Inativo} but Gate has only "
        "id, label, latitude, longitude. "
        "Fix: add status = Column(SEnum('active', 'inactive'), default='active') to Gate."
    ),
    strict=True,
)
def test_gate_status_column_exists():
    """BR-14: Gate model must have a status/estado column."""
    src = _MODELS_PATH.read_text()
    gate_start = src.find("class Gate(Base):")
    gate_end = src.find("\nclass ", gate_start + 1)
    gate_src = src[gate_start:gate_end] if gate_end != -1 else src[gate_start:]
    assert "status" in gate_src or "estado" in gate_src, (
        "Gate model has no status column (BR-14)"
    )


# BR-17 ─ detection origin gap

@pytest.mark.xfail(
    reason=(
        "BR-17 gap: detection.origem ∈ {IA, Manual} requires a PG detection table. "
        "Detections are in MongoDB agent_detections collection only. "
        "Fix: add a PG detection table with origin = Column(SEnum('IA', 'Manual')) "
        "and a UNIQUE FK to appointment, or enforce via a domain model check."
    ),
    strict=True,
)
def test_detection_origin_enum_declared_in_orm():
    """BR-17: sql_models.py must have a Detection model with an origin enum."""
    src = _MODELS_PATH.read_text()
    assert "class Detection(Base):" in src or "class Deteccao(Base):" in src, (
        "No Detection ORM model in sql_models.py (BR-17)"
    )


# ---------------------------------------------------------------------------
# 2. Integration tests (require PostgreSQL)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_invalid_alert_type_rejected_by_pg(pg_session):
    """
    Inserting an alert with an invalid type value raises DataError from PG.
    Confirms the type_alert enum is enforced at the database level.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import DataError, ProgrammingError

    with pytest.raises((DataError, ProgrammingError)):
        pg_session.execute(text(
            "INSERT INTO alert (type) VALUES ('NOT_A_REAL_TYPE')"
        ))
        pg_session.flush()


@pytest.mark.integration
def test_invalid_dock_status_rejected_by_pg(pg_session):
    """
    Inserting a dock with an invalid current_usage value raises DataError.
    Confirms the operational_status enum is enforced at the database level.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import DataError, ProgrammingError

    with pytest.raises((DataError, ProgrammingError)):
        pg_session.execute(text(
            "INSERT INTO dock (terminal_id, bay_number, current_usage) "
            "VALUES (1, 'TEST-BAY', 'INVALID_STATUS')"
        ))
        pg_session.flush()
