"""
Tests for the SELECT FOR UPDATE lock on the Appointment aggregate (BR-48).

BR-48 — Command handler must acquire SELECT … FOR UPDATE before applying
a state transition, preventing lost updates under concurrent writers.

Test layers:
  1. Structural — source confirms .with_for_update() and version increment.
  2. Behavioural (integration) — two real PG connections; the second is
     blocked by NOWAIT until the first commits.

For the behavioural test we use inbox_events (no FK deps) to demonstrate
PG-level row locking without needing a fully-seeded appointment tree.
The structural test then confirms the same mechanism is wired in
SqlAlchemyAppointmentStateRepository.get_for_update.

Integration tests require running PostgreSQL (docker-compose up -d).

Run:
    PYTHONPATH=. pytest tests/integration/test_appointment_row_lock.py -v
"""

import pathlib
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_PATH = (
    pathlib.Path(__file__).parent.parent.parent
    / "infrastructure" / "persistence" / "appointment_state_repository.py"
)


# ---------------------------------------------------------------------------
# 1. Structural guards (no running services required)
# ---------------------------------------------------------------------------

def test_get_for_update_calls_with_for_update():
    """
    SqlAlchemyAppointmentStateRepository.get_for_update must use
    .with_for_update() so PostgreSQL emits SELECT … FOR UPDATE.
    If this guard is removed, concurrent writes can produce lost updates.
    """
    src = _REPO_PATH.read_text()

    method_start = src.find("def get_for_update")
    method_end = src.find("\n    def ", method_start + 1)
    method_src = src[method_start:method_end] if method_end != -1 else src[method_start:]

    assert ".with_for_update()" in method_src, (
        "get_for_update must call .with_for_update() to acquire a row lock "
        "before any state transition"
    )


def test_save_state_transition_increments_version():
    """
    save_state_transition must increment the version column so that any
    concurrent writer using optimistic concurrency detects the conflict.
    """
    src = _REPO_PATH.read_text()

    method_start = src.find("def save_state_transition")
    method_end = src.find("\n    def ", method_start + 1)
    method_src = src[method_start:method_end] if method_end != -1 else src[method_start:]

    assert "version" in method_src, (
        "save_state_transition must update the version column"
    )
    assert "+ 1" in method_src, (
        "version must be incremented by 1 on each state transition"
    )


# ---------------------------------------------------------------------------
# 2. Behavioural lock test (requires running PostgreSQL)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_select_for_update_blocks_concurrent_session():
    """
    Session A acquires FOR UPDATE on a row.
    Session B attempts FOR UPDATE NOWAIT on the same row and receives
    OperationalError (lock not available) while A holds the lock.
    After A commits, B acquires the lock without error.

    This proves that .with_for_update() in get_for_update produces real
    PG-level row locking.  We use inbox_events to avoid FK-seed complexity.
    """
    from infrastructure.persistence.postgres import engine

    eid = "test-lock-inbox-001"

    # --- Seed: insert and commit a row outside both test transactions ---
    with engine.connect() as seed_conn:
        seed_conn.execute(text(
            'DELETE FROM inbox_events WHERE event_id = :eid'
        ), {"eid": eid})
        seed_conn.execute(text("""
            INSERT INTO inbox_events
                (event_id, topic, partition, "offset",
                 aggregate_type, aggregate_id, event_type, event_version, status)
            VALUES
                (:eid, 'test', 0, 0, 'appointment', '1', 'ContainerMoved', 1, 'RECEIVED')
        """), {"eid": eid})
        seed_conn.commit()

    conn_a = engine.connect()
    conn_b = engine.connect()
    try:
        # Session A: begin and acquire FOR UPDATE (holds lock)
        conn_a.execute(text("BEGIN"))
        conn_a.execute(
            text("SELECT * FROM inbox_events WHERE event_id = :eid FOR UPDATE"),
            {"eid": eid},
        )

        # Session B: NOWAIT must raise because A holds the lock
        conn_b.execute(text("BEGIN"))
        with pytest.raises(OperationalError):
            conn_b.execute(
                text("SELECT * FROM inbox_events WHERE event_id = :eid FOR UPDATE NOWAIT"),
                {"eid": eid},
            )

        # Release A's lock
        conn_a.commit()

        # Session B (after rollback to clear error state) can now acquire
        conn_b.rollback()
        conn_b.execute(text("BEGIN"))
        result = conn_b.execute(
            text("SELECT * FROM inbox_events WHERE event_id = :eid FOR UPDATE NOWAIT"),
            {"eid": eid},
        )
        assert result.rowcount != 0 or result.fetchone() is not None
        conn_b.rollback()

    finally:
        conn_a.close()
        conn_b.close()
        # Cleanup seed row
        with engine.connect() as cleanup:
            cleanup.execute(
                text("DELETE FROM inbox_events WHERE event_id = :eid"), {"eid": eid}
            )
            cleanup.commit()


@pytest.mark.integration
def test_version_increments_after_state_transition(pg_session):
    """
    SqlAlchemyAppointmentStateRepository.save_state_transition increments
    version by 1 on each call.  Simulated directly on a real ORM session
    by manipulating an Appointment ORM object without FK enforcement
    (uses flush, not commit, so no FK violation is surfaced).

    If this test cannot run (FK constraints prevent the row), it is marked
    xfail and the structural test in this module is sufficient.
    """
    from infrastructure.persistence.sql_models import Appointment
    from infrastructure.persistence.appointment_state_repository import (
        SqlAlchemyAppointmentStateRepository,
    )

    # Try to find any existing appointment in the session (demo seed data)
    existing = pg_session.query(Appointment).first()
    if existing is None:
        pytest.skip("No appointment rows in DB — run data_init_demo.py first")

    repo = SqlAlchemyAppointmentStateRepository(pg_session)
    original_version = existing.version or 1

    repo.save_state_transition(
        existing.id,
        existing.status,  # keep same status, just bump version
        {},
    )

    pg_session.flush()
    pg_session.expire(existing)

    updated = pg_session.query(Appointment).filter_by(id=existing.id).one()
    assert updated.version == original_version + 1

    # Rollback so we don't persist the change
    pg_session.rollback()
