"""
Integration tests for the Inbox idempotency guarantee and state machine.

BR-21 — inbox_events.event_id UNIQUE prevents duplicate processing.
BR-22 — Inbox state machine: RECEIVED → PROCESSING → PROCESSED | FAILED | DEAD_LETTER.

Requires: running PostgreSQL (docker-compose up -d in src/V_APP/).
Run:
    PYTHONPATH=. pytest tests/integration/test_inbox_state_machine.py -m integration -v
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from domain.events import ConsumeContext, EventEnvelope
from infrastructure.persistence.inbox_repository import SqlAlchemyInboxRepository
from infrastructure.persistence.inbox_outbox_models import InboxEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(event_id: str) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id,
        correlation_id="corr-test",
        causation_id=None,
        aggregate_type="appointment",
        aggregate_id="42",
        event_type="ContainerMoved",
        event_version=1,
        occurred_at=datetime.now(timezone.utc),
        producer="test",
        partition_key="42",
        payload={"truck_id": "truck-test"},
    )


def _make_ctx() -> ConsumeContext:
    return ConsumeContext(
        topic="test.topic",
        partition=0,
        offset=0,
        key=None,
        headers={},
    )


def _delete_inbox_row(session, event_id: str) -> None:
    session.execute(
        text('DELETE FROM inbox_events WHERE event_id = :eid'),
        {"eid": event_id},
    )
    session.commit()


# ---------------------------------------------------------------------------
# BR-21 — UNIQUE constraint on event_id
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_duplicate_event_id_returns_false(pg_session):
    """
    try_insert_received returns False on a duplicate event_id without raising.
    The first insert succeeds (True); the second is silently rejected (False).
    """
    import uuid
    eid = f"test-inbox-dedup-{uuid.uuid4()}"
    repo = SqlAlchemyInboxRepository(pg_session)
    event = _make_event(eid)
    ctx = _make_ctx()

    try:
        result_first = repo.try_insert_received(event, ctx)
        pg_session.commit()

        result_second = repo.try_insert_received(event, ctx)

        assert result_first is True
        assert result_second is False
    finally:
        # begin_nested() + SAVEPOINT rollback on duplicate leaves the outer
        # session in DEACTIVE state in SQLAlchemy 2.x + psycopg2; reset before cleanup.
        pg_session.rollback()
        _delete_inbox_row(pg_session, eid)


@pytest.mark.integration
def test_duplicate_event_id_db_constraint(pg_session):
    """
    Inserting two rows with the same event_id via raw SQL raises IntegrityError,
    confirming the UNIQUE constraint exists at the database level (not only in
    application code).
    """
    eid = "test-inbox-dedup-sql-001"
    ins = text(
        """
        INSERT INTO inbox_events
            (event_id, topic, partition, "offset",
             aggregate_type, aggregate_id, event_type, event_version, status)
        VALUES
            (:eid, 'test', 0, 0, 'appointment', '1', 'ContainerMoved', 1, 'RECEIVED')
        """
    )

    pg_session.execute(ins, {"eid": eid})
    pg_session.flush()

    with pytest.raises(IntegrityError):
        pg_session.execute(ins, {"eid": eid})
        pg_session.flush()

    # Rollback leaves no committed rows — no cleanup needed.


# ---------------------------------------------------------------------------
# BR-22 — Inbox state machine
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_happy_path_reaches_processed(pg_session):
    """
    Full happy path: RECEIVED → PROCESSING → PROCESSED.
    processed_at must be set on completion.
    """
    eid = "test-inbox-sm-happy-001"
    repo = SqlAlchemyInboxRepository(pg_session)

    repo.try_insert_received(_make_event(eid), _make_ctx())
    repo.mark_processing(eid)
    repo.mark_processed(eid)

    row = pg_session.query(InboxEvent).filter_by(event_id=eid).one()
    assert row.status == "PROCESSED"
    assert row.processed_at is not None


@pytest.mark.integration
def test_retryable_failure_goes_to_failed(pg_session):
    """
    mark_failed(retryable=True) transitions to FAILED and increments retry_count.
    """
    eid = "test-inbox-sm-fail-001"
    repo = SqlAlchemyInboxRepository(pg_session)

    repo.try_insert_received(_make_event(eid), _make_ctx())
    repo.mark_processing(eid)
    repo.mark_failed(eid, error="transient network error", retryable=True)

    row = pg_session.query(InboxEvent).filter_by(event_id=eid).one()
    assert row.status == "FAILED"
    assert row.retry_count == 1
    assert "transient" in row.last_error


@pytest.mark.integration
def test_permanent_failure_goes_to_dead_letter(pg_session):
    """
    mark_failed(retryable=False) transitions directly to DEAD_LETTER,
    bypassing FAILED.
    """
    eid = "test-inbox-sm-dlq-001"
    repo = SqlAlchemyInboxRepository(pg_session)

    repo.try_insert_received(_make_event(eid), _make_ctx())
    repo.mark_processing(eid)
    repo.mark_failed(eid, error="ValueError: bad payload", retryable=False)

    row = pg_session.query(InboxEvent).filter_by(event_id=eid).one()
    assert row.status == "DEAD_LETTER"
    assert row.retry_count == 1
