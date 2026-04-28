"""
Tests for the ContainerMoved atomicity guarantee (BR-27).

BR-27 — Kafka offset is committed ONLY after the PostgreSQL UoW commit
succeeds.  If uow.commit() raises, the exception propagates out of
handler.handle() and the caller's Kafka offset commit is never reached.

These tests use a FakeUoW so they run without a running PostgreSQL instance.
The structural guard (Kafka commit line is after handler.handle) is verified
via source inspection — same pattern as test_appointment_commands_uow.py.

Run:
    PYTHONPATH=. pytest tests/integration/test_container_moved_atomicity.py -v
"""

import pytest
from datetime import datetime, timezone

from domain.events import ConsumeContext, EventEnvelope
from application.use_cases.container_moved_handler import ContainerMovedHandler


# ---------------------------------------------------------------------------
# Fake infrastructure
# ---------------------------------------------------------------------------

class _FakeInbox:
    def __init__(self):
        self._store: dict = {}

    def try_insert_received(self, event, ctx) -> bool:
        if event.event_id in self._store:
            return False
        self._store[event.event_id] = "RECEIVED"
        return True

    def mark_processing(self, event_id: str):
        self._store[event_id] = "PROCESSING"

    def mark_processed(self, event_id: str):
        self._store[event_id] = "PROCESSED"

    def mark_failed(self, event_id: str, error: str, retryable: bool):
        self._store[event_id] = "FAILED" if retryable else "DEAD_LETTER"

    def status(self, event_id: str) -> str:
        return self._store.get(event_id, "ABSENT")


class _FakeOutbox:
    def __init__(self):
        self.appended: list = []

    def append(self, event, *, topic: str, key: str):
        self.appended.append(event)


class _FakeAppointmentState:
    def __init__(self, aggregate=None):
        self._aggregate = aggregate or {"status": "in_transit", "gate_in_id": 1}

    def get_for_update(self, appointment_id):
        return self._aggregate

    def save_state_transition(self, appointment_id, new_state, metadata):
        pass


class _FakeVisits:
    def create(self, **kwargs):
        return True


class _FakeUoW:
    def __init__(self, fail_on_commit: bool = False, aggregate=None):
        self.inbox = _FakeInbox()
        self.outbox = _FakeOutbox()
        self.appointment_state = _FakeAppointmentState(aggregate)
        self.visits = _FakeVisits()
        self.committed = False
        self.rolled_back = False
        self._fail = fail_on_commit

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.rolled_back = True

    def commit(self):
        if self._fail:
            raise RuntimeError("Simulated PG commit failure")
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def _make_event(event_id: str = "test-cm-evt-001", new_state: str = "in_transit") -> EventEnvelope:
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
        payload={"new_state": new_state, "gate_in_id": 1},
    )


def _make_ctx() -> ConsumeContext:
    return ConsumeContext(topic="test.topic", partition=0, offset=0, key=None, headers={})


def _make_handler(uow: _FakeUoW) -> ContainerMovedHandler:
    return ContainerMovedHandler(uow_factory=lambda **_: uow)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_commit_failure_propagates_exception():
    """
    When uow.commit() raises, ContainerMovedHandler.handle() must not
    swallow the exception — it must propagate to the caller.
    This ensures _dispatch_container_moved never reaches the Kafka commit.
    """
    uow = _FakeUoW(fail_on_commit=True)
    handler = _make_handler(uow)

    with pytest.raises(RuntimeError, match="Simulated PG commit failure"):
        handler.handle(_make_event(), _make_ctx())


def test_uow_rolled_back_when_commit_fails():
    """
    When commit fails, UoW.__exit__ must call rollback — confirmed via the
    fake's rolled_back flag, which mirrors what SqlAlchemyUnitOfWork does.
    """
    uow = _FakeUoW(fail_on_commit=True)
    handler = _make_handler(uow)

    with pytest.raises(RuntimeError):
        handler.handle(_make_event(), _make_ctx())

    assert uow.rolled_back is True
    assert uow.committed is False


def test_inbox_not_committed_when_commit_fails():
    """
    After a commit failure uow.committed must be False — the session was
    never committed and SqlAlchemy's rollback in UoW.__exit__ discards all
    flushed writes (inbox row, outbox row) from the PG WAL buffer.
    The fake cannot model the actual rollback of in-memory state, but the
    committed=False invariant is the safety property that matters.
    """
    uow = _FakeUoW(fail_on_commit=True)
    handler = _make_handler(uow)

    eid = "test-cm-no-commit-001"
    with pytest.raises(RuntimeError):
        handler.handle(_make_event(eid), _make_ctx())

    assert uow.committed is False
    assert uow.rolled_back is True


def test_successful_flow_commits_exactly_once():
    """
    Happy path: handler commits once, inbox reaches PROCESSED, one outbox
    event is appended.
    """
    uow = _FakeUoW(fail_on_commit=False)
    handler = _make_handler(uow)

    eid = "test-cm-happy-001"
    handler.handle(_make_event(eid), _make_ctx())

    assert uow.committed is True
    assert uow.inbox.status(eid) == "PROCESSED"
    assert len(uow.outbox.appended) == 1
    assert uow.outbox.appended[0].event_type == "AppointmentStateChanged"


def test_duplicate_event_returns_without_commit():
    """
    A duplicate event_id (inbox dedup gate returns False) causes the handler
    to return immediately without calling uow.commit().  The Kafka offset is
    still committed by the caller — duplicate events are ACK'd and skipped,
    not retried.
    """
    uow = _FakeUoW(fail_on_commit=False)
    # Pre-seed the inbox so the event looks like a duplicate
    eid = "test-cm-dup-001"
    uow.inbox._store[eid] = "PROCESSED"

    handler = _make_handler(uow)
    handler.handle(_make_event(eid), _make_ctx())

    # No commit triggered — handler returned early
    assert uow.committed is False
    assert len(uow.outbox.appended) == 0


def test_kafka_commit_is_after_handler_in_dispatch():
    """
    Structural guard: in _dispatch_container_moved the Kafka consumer.commit()
    call appears strictly AFTER the handler.handle() call.
    If this ordering is ever reversed, the test fails before any runtime issue.
    Reads the source file directly to avoid the shared.src import at module level.
    """
    import pathlib
    consumer_path = (
        pathlib.Path(__file__).parent.parent.parent
        / "infrastructure" / "messaging" / "kafka_decision_consumer.py"
    )
    src = consumer_path.read_text()

    # Narrow to _dispatch_container_moved only
    start = src.find("async def _dispatch_container_moved")
    end = src.find("\n    async def ", start + 1)
    method_src = src[start:end] if end != -1 else src[start:]

    handler_pos = method_src.find("handler.handle")
    kafka_commit_pos = method_src.find("consumer.commit")

    assert handler_pos != -1, "_dispatch_container_moved must call handler.handle"
    assert kafka_commit_pos != -1, "_dispatch_container_moved must call consumer.commit"
    assert handler_pos < kafka_commit_pos, (
        "Kafka consumer.commit must appear AFTER handler.handle in source — "
        "offset must only be committed after a successful PG commit"
    )
