"""
Unit tests for the decision → appointment state machine (BR-45, BR-46, BR-47).

BR-45 — Auto-Accepted decision transitions appointment to IN_PROCESS.
BR-46 — MANUAL_REVIEW agent-alone does not change appointment status;
         status only transitions after the operator decision is processed.
BR-47 — REJECTED decision does NOT change status; an alert is created instead.

All tests use a FakeUoW — no running services required.

Run:
    PYTHONPATH=. pytest tests/unit/test_decision_state_machine.py -v
"""

import sys
from unittest.mock import MagicMock
import pytest

# appointment_commands imports redis_client at module level; patch before import
# so the test runs without a Redis connection (same pattern as
# kafka_decision_consumer_unit_test.py).
_mock_redis = MagicMock()
_mock_redis_module = MagicMock()
_mock_redis_module.redis_client = _mock_redis
sys.modules.setdefault("infrastructure.persistence.redis", _mock_redis_module)

from application.use_cases.appointment_commands import cmd_process_decision


# ---------------------------------------------------------------------------
# Fake infrastructure
# ---------------------------------------------------------------------------

class _FakeAlerts:
    def __init__(self):
        self.added: list = []

    def get_appointment_visit_id(self, appointment_id):
        return None

    def add(self, *, visit_id, alert_type, description, image_url=None, appointment_id=None):
        self.added.append({"type": alert_type, "description": description})


class _FakeOutbox:
    def __init__(self):
        self.appended: list = []

    def append(self, event, *, topic: str, key: str):
        self.appended.append(event)


class _FakeAppointmentState:
    def __init__(self, status: str = "in_transit"):
        self._status = status
        self.transitions: list = []

    def get_for_update(self, appointment_id):
        return {"status": self._status, "gate_in_id": 1}

    def save_state_transition(self, appointment_id, new_state, metadata):
        self.transitions.append((appointment_id, new_state, metadata))


class _FakeUoW:
    def __init__(self, current_status: str = "in_transit"):
        self.appointment_state = _FakeAppointmentState(current_status)
        self.alerts = _FakeAlerts()
        self.outbox = _FakeOutbox()
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass

    def commit(self):
        self.committed = True

    def rollback(self):
        pass


def _uow_factory(uow: _FakeUoW):
    """Return a callable that yields the pre-built fake."""
    return lambda: uow


# ---------------------------------------------------------------------------
# BR-45 — Auto-Accepted → IN_PROCESS
# ---------------------------------------------------------------------------

def test_accepted_decision_transitions_to_in_process():
    """
    An ACCEPTED decision with status=in_process must transition the
    appointment to IN_PROCESS and commit via UoW.
    """
    uow = _FakeUoW(current_status="in_transit")
    result = cmd_process_decision(
        _uow_factory(uow),
        appointment_id=42,
        decision_payload={"decision": "ACCEPTED", "status": "in_process"},
    )

    assert result is not None
    assert result["status"] == "in_process"
    assert result["previous_status"] == "in_transit"
    assert uow.committed is True


def test_accepted_decision_appends_decision_processed_event():
    """
    The outbox must receive exactly one DecisionProcessed event for an
    ACCEPTED decision — this is what the outbox worker projects to
    MongoDB and Redis.
    """
    uow = _FakeUoW(current_status="in_transit")
    cmd_process_decision(
        _uow_factory(uow),
        appointment_id=42,
        decision_payload={"decision": "ACCEPTED", "status": "in_process"},
    )

    assert len(uow.outbox.appended) == 1
    event = uow.outbox.appended[0]
    assert event.event_type == "DecisionProcessed"
    assert event.payload["new_status"] == "in_process"
    assert event.payload["decision"] == "ACCEPTED"


# ---------------------------------------------------------------------------
# BR-47 — REJECTED → status unchanged, alert created
# ---------------------------------------------------------------------------

def test_rejected_decision_does_not_change_status():
    """
    A REJECTED decision must NOT change the appointment status.
    The payload has no 'status' key so cmd_process_decision defaults
    to old_status.
    """
    uow = _FakeUoW(current_status="in_transit")
    result = cmd_process_decision(
        _uow_factory(uow),
        appointment_id=42,
        decision_payload={"decision": "REJECTED"},
    )

    assert result is not None
    assert result["status"] == "in_transit"
    assert result["previous_status"] == "in_transit"
    assert uow.committed is True


def test_rejected_decision_creates_alert():
    """
    A REJECTED decision with an alerts list must create one alert row
    per entry via uow.alerts.add().
    """
    uow = _FakeUoW(current_status="in_transit")
    result = cmd_process_decision(
        _uow_factory(uow),
        appointment_id=42,
        decision_payload={
            "decision": "REJECTED",
            "alerts": [
                {"type": "safety", "description": "Hazmat label non-compliant"},
            ],
        },
    )

    assert result["alerts_created"] == 1
    assert len(uow.alerts.added) == 1
    assert uow.alerts.added[0]["type"] == "safety"


def test_rejected_decision_no_alerts_when_payload_empty():
    """No alerts payload → zero alerts created, status unchanged."""
    uow = _FakeUoW(current_status="in_transit")
    result = cmd_process_decision(
        _uow_factory(uow),
        appointment_id=42,
        decision_payload={"decision": "REJECTED", "alerts": []},
    )

    assert result["alerts_created"] == 0
    assert len(uow.alerts.added) == 0
    assert result["status"] == "in_transit"


# ---------------------------------------------------------------------------
# BR-46 — MANUAL_REVIEW alone does not change appointment status
# ---------------------------------------------------------------------------

def test_manual_review_payload_alone_does_not_change_status():
    """
    If cmd_process_decision were ever called with a MANUAL_REVIEW payload
    (which in practice only happens after the operator resolves it), the
    status must not change from the current value.

    In the real flow, cmd_process_decision is NOT called at all during the
    agent-side MANUAL_REVIEW phase — DecisionCorrelator.process_agent_decision
    returns None and _dispatch_container_moved is skipped.  This test guards
    the command itself against an accidental call with an unresolved review.
    """
    uow = _FakeUoW(current_status="in_transit")
    result = cmd_process_decision(
        _uow_factory(uow),
        appointment_id=42,
        decision_payload={"decision": "MANUAL_REVIEW"},
    )

    # No 'status' key → defaults to old_status → no state change
    assert result["status"] == "in_transit"
    assert result["previous_status"] == "in_transit"


def test_appointment_not_found_returns_none():
    """
    If the appointment does not exist (get_for_update returns None),
    cmd_process_decision returns None without committing.
    """
    class _NotFoundAppointmentState(_FakeAppointmentState):
        def get_for_update(self, appointment_id):
            return None

    uow = _FakeUoW()
    uow.appointment_state = _NotFoundAppointmentState()
    result = cmd_process_decision(
        _uow_factory(uow),
        appointment_id=999,
        decision_payload={"decision": "ACCEPTED", "status": "in_process"},
    )

    assert result is None
    assert uow.committed is False
