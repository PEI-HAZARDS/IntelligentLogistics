"""
Tests for PostgreSQL uniqueness and FK constraints (BR-01, BR-04, BR-07, BR-08, BR-09, BR-10).

BR-01 — company.nif UNIQUE (implemented as PRIMARY KEY).
BR-04 — worker.email UNIQUE.
BR-07 — driver.company_nif FK → company.nif.
BR-08 — appointment FKs to booking, driver, truck, terminal, gate.
BR-09 — appointment has exactly 1 entry gate (gate_in_id) and 0..1 exit gate (gate_out_id).
BR-10 — Detection 1:1 with appointment — GAP: detections live in MongoDB, not PostgreSQL.
         A dedicated PG table with a UNIQUE FK is absent; flagged as xfail.

Test layers:
  1. Structural — sql_models.py confirms ORM-level declarations (no services required).
  2. Integration — real PG enforces constraints at INSERT time.

Integration tests require PostgreSQL (docker-compose up -d).

Run:
    PYTHONPATH=. pytest tests/integration/test_pg_constraints.py -v
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
# 1. Structural guards
# ---------------------------------------------------------------------------

def _model_src(class_name: str) -> str:
    """Return the ORM class body from sql_models.py."""
    src = _MODELS_PATH.read_text()
    start = src.find(f"class {class_name}(Base):")
    end = src.find("\nclass ", start + 1)
    return src[start:end] if end != -1 else src[start:]


# BR-01
def test_company_nif_is_primary_key():
    """company.nif is declared as PRIMARY KEY, which implies UNIQUE (BR-01)."""
    src = _model_src("Company")
    assert "nif" in src and "primary_key=True" in src, (
        "company.nif must be the primary key — PK guarantees uniqueness (BR-01)"
    )


# BR-04
def test_worker_email_declared_unique():
    """worker.email must have unique=True in the ORM model (BR-04)."""
    src = _model_src("Worker")
    # Find the email column and confirm unique=True appears near it
    email_pos = src.find("email")
    block = src[email_pos:email_pos + 100]
    assert "unique=True" in block, (
        "worker.email must declare unique=True (BR-04)"
    )


# BR-07
def test_driver_company_nif_is_foreign_key():
    """driver.company_nif must be a FK to company.nif (BR-07)."""
    src = _model_src("Driver")
    assert "company_nif" in src, "driver must have a company_nif column (BR-07)"
    assert "ForeignKey('company.nif')" in src or 'ForeignKey("company.nif")' in src, (
        "driver.company_nif must reference company.nif via ForeignKey (BR-07)"
    )


# BR-08
@pytest.mark.parametrize("fk_ref", [
    "booking.reference",
    "driver.drivers_license",
    "truck.license_plate",
    "terminal.id",
    "gate.id",
])
def test_appointment_has_required_foreign_keys(fk_ref):
    """appointment must declare a FK to each of its referenced entities (BR-08)."""
    src = _model_src("Appointment")
    assert f"ForeignKey('{fk_ref}')" in src or f'ForeignKey("{fk_ref}")' in src, (
        f"appointment must have a FK referencing {fk_ref} (BR-08)"
    )


# BR-09
def test_appointment_has_gate_in_and_gate_out_columns():
    """
    appointment must have both gate_in_id (entry, required) and
    gate_out_id (exit, optional) columns (BR-09).
    """
    src = _model_src("Appointment")
    assert "gate_in_id" in src, "appointment must have gate_in_id column (BR-09)"
    assert "gate_out_id" in src, "appointment must have gate_out_id column (BR-09)"


def test_appointment_gate_out_is_nullable():
    """
    gate_out_id must be nullable (0..1) — a truck may not have exited yet (BR-09).
    """
    src = _model_src("Appointment")
    # gate_out_id must NOT have nullable=False
    gate_out_pos = src.find("gate_out_id")
    line_end = src.find("\n", gate_out_pos)
    gate_out_line = src[gate_out_pos:line_end]
    assert "nullable=False" not in gate_out_line, (
        "gate_out_id must be nullable (exit gate is optional until truck leaves)"
    )


# BR-10
@pytest.mark.xfail(
    reason=(
        "BR-10 gap: no Detection table with a UNIQUE FK to appointment exists in "
        "PostgreSQL. Detections are stored in MongoDB agent_detections collection "
        "with no relational 1:1 enforcement. "
        "Fix: add a pg_detections table (or detection_id column on appointment) "
        "with UNIQUE(appointment_id) to enforce the 1:1 cardinality in PG."
    ),
    strict=True,
)
def test_detection_table_has_unique_appointment_fk():
    """
    BR-10: detection must have a UNIQUE FK to appointment (1:1 cardinality).
    Currently absent — detections are in MongoDB only.
    """
    src = _MODELS_PATH.read_text()
    # Look for a Detection ORM model with a UNIQUE FK to appointment
    assert "class Detection(Base):" in src or "class Deteccao(Base):" in src, (
        "No Detection ORM model found in sql_models.py — 1:1 constraint missing (BR-10)"
    )


# ---------------------------------------------------------------------------
# 2. Integration tests (require PostgreSQL)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_duplicate_company_nif_raises_integrity_error(pg_session):
    """Inserting two companies with the same nif raises IntegrityError (BR-01)."""
    from sqlalchemy.exc import IntegrityError
    from infrastructure.persistence.sql_models import Company

    nif = "NIF-TEST-BR01"
    pg_session.execute(
        __import__("sqlalchemy").delete(Company).where(Company.nif == nif)
    )
    pg_session.flush()

    pg_session.add(Company(nif=nif, name="Test Corp A"))
    pg_session.flush()

    with pytest.raises(IntegrityError):
        pg_session.add(Company(nif=nif, name="Test Corp B"))
        pg_session.flush()

    pg_session.rollback()


@pytest.mark.integration
def test_duplicate_worker_email_raises_integrity_error(pg_session):
    """Inserting two workers with the same email raises IntegrityError (BR-04)."""
    from sqlalchemy.exc import IntegrityError
    from infrastructure.persistence.sql_models import Worker

    email = "test-br04@example.com"
    pg_session.execute(
        __import__("sqlalchemy").delete(Worker).where(Worker.email == email)
    )
    pg_session.flush()

    pg_session.add(Worker(num_worker="W-TEST-BR04-1", name="Alice", email=email))
    pg_session.flush()

    with pytest.raises(IntegrityError):
        pg_session.add(Worker(num_worker="W-TEST-BR04-2", name="Bob", email=email))
        pg_session.flush()

    pg_session.rollback()


@pytest.mark.integration
def test_driver_invalid_company_nif_raises_integrity_error(pg_session):
    """Inserting a driver with a non-existent company_nif raises IntegrityError (BR-07)."""
    from sqlalchemy.exc import IntegrityError
    from infrastructure.persistence.sql_models import Driver

    with pytest.raises(IntegrityError):
        pg_session.add(Driver(
            drivers_license="LIC-TEST-BR07",
            company_nif="NIF-DOES-NOT-EXIST",
            name="Ghost Driver",
        ))
        pg_session.flush()

    pg_session.rollback()
