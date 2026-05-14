"""
Unit tests for Phase 4 — durable pending_review (PD-01).

Covers:
  - cmd_store_pending_review writes PG row + PendingReviewCreated outbox event
  - cmd_resolve_pending_review acquires lock, flips status, appends PendingReviewResolved
  - cmd_resolve_pending_review returns None for unknown event_id
  - cmd_resolve_pending_review is idempotent on already-resolved reviews
  - cmd_resolve_pending_review raises ValueError for invalid resolution
  - DecisionCorrelator.process_agent_decision calls cmd_store_pending_review
    instead of direct redis.setex for MANUAL_REVIEW decisions
  - Concurrent reviews identified by event_id, not truck_id (no collision)
  - Outbox worker project_to_redis handles PendingReviewCreated and
    PendingReviewResolved event types
"""

import uuid
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakePendingReviewRepo:
    def __init__(self):
        self._store: dict = {}

    def create(self, *, event_id, truck_id, gate_id, license_plate, payload):
        if event_id in self._store:
            raise Exception(f"Duplicate event_id {event_id}")
        row = {
            "event_id": event_id,
            "truck_id": truck_id,
            "gate_id": gate_id,
            "license_plate": license_plate,
            "payload": payload,
            "status": "PENDING",
            "created_at": None,
            "resolved_at": None,
            "resolved_by": None,
        }
        self._store[event_id] = row
        return row

    def get_for_update(self, event_id):
        return dict(self._store[event_id]) if event_id in self._store else None

    def update_status(self, event_id, status, resolved_by=None):
        if event_id not in self._store:
            return False
        self._store[event_id]["status"] = status
        self._store[event_id]["resolved_by"] = resolved_by
        return True


class _FakeOutbox:
    def __init__(self):
        self.events = []

    def append(self, event, *, topic, key):
        self.events.append({"event": event, "topic": topic, "key": key})


class _FakeUoW:
    def __init__(self):
        self.pending_reviews = _FakePendingReviewRepo()
        self.outbox = _FakeOutbox()
        self._committed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def commit(self):
        self._committed = True

    def rollback(self):
        pass


def _make_uow_factory():
    uow = _FakeUoW()
    return uow, lambda: uow


# ---------------------------------------------------------------------------
# cmd_store_pending_review
# ---------------------------------------------------------------------------

class TestCmdStorePendingReview:
    def test_creates_row_and_outbox_event(self):
        from application.use_cases.pending_review_handlers import cmd_store_pending_review

        uow, factory = _make_uow_factory()
        event_id = str(uuid.uuid4())
        row = cmd_store_pending_review(
            factory,
            event_id=event_id,
            truck_id="TRUCK-1",
            gate_id=2,
            license_plate="AB-12-CD",
            payload={"decision": "MANUAL_REVIEW"},
        )

        assert row["event_id"] == event_id
        assert row["status"] == "PENDING"
        assert uow._committed

        outbox_entries = uow.outbox.events
        assert len(outbox_entries) == 1
        assert outbox_entries[0]["topic"] == "pending-review.created"
        assert outbox_entries[0]["event"].event_type == "PendingReviewCreated"
        assert outbox_entries[0]["event"].payload["event_id"] == event_id
        assert outbox_entries[0]["event"].payload["gate_id"] == 2

    def test_two_reviews_different_event_ids_no_collision(self):
        from application.use_cases.pending_review_handlers import cmd_store_pending_review

        uow, factory = _make_uow_factory()
        id1, id2 = str(uuid.uuid4()), str(uuid.uuid4())

        cmd_store_pending_review(factory, event_id=id1, truck_id="TRUCK-1",
                                  gate_id=1, license_plate="XX-11-YY",
                                  payload={"decision": "MANUAL_REVIEW"})
        cmd_store_pending_review(factory, event_id=id2, truck_id="TRUCK-1",
                                  gate_id=1, license_plate="XX-11-YY",
                                  payload={"decision": "MANUAL_REVIEW"})

        assert id1 in uow.pending_reviews._store
        assert id2 in uow.pending_reviews._store


# ---------------------------------------------------------------------------
# cmd_resolve_pending_review
# ---------------------------------------------------------------------------

class TestCmdResolvePendingReview:
    def _setup(self, resolution="APPROVED"):
        from application.use_cases.pending_review_handlers import (
            cmd_store_pending_review,
            cmd_resolve_pending_review,
        )
        uow, factory = _make_uow_factory()
        event_id = str(uuid.uuid4())
        cmd_store_pending_review(
            factory,
            event_id=event_id,
            truck_id="TRUCK-1",
            gate_id=3,
            license_plate="AA-00-BB",
            payload={"decision": "MANUAL_REVIEW"},
        )
        uow.outbox.events.clear()
        uow._committed = False
        return uow, factory, event_id, cmd_resolve_pending_review

    def test_approved_flips_status_and_appends_outbox(self):
        uow, factory, event_id, cmd = self._setup()
        result = cmd(factory, event_id=event_id, resolution="APPROVED", resolved_by="W001")

        assert result["status"] == "APPROVED"
        assert result["resolved_by"] == "W001"
        assert uow._committed

        assert len(uow.outbox.events) == 1
        ev = uow.outbox.events[0]["event"]
        assert ev.event_type == "PendingReviewResolved"
        assert ev.payload["resolution"] == "APPROVED"
        assert ev.payload["event_id"] == event_id

    def test_rejected_flips_status(self):
        uow, factory, event_id, cmd = self._setup()
        result = cmd(factory, event_id=event_id, resolution="REJECTED", resolved_by="W002")
        assert result["status"] == "REJECTED"

    def test_returns_none_for_unknown_event_id(self):
        from application.use_cases.pending_review_handlers import cmd_resolve_pending_review

        _, factory = _make_uow_factory()
        result = cmd_resolve_pending_review(
            factory, event_id=str(uuid.uuid4()), resolution="APPROVED", resolved_by="W001"
        )
        assert result is None

    def test_idempotent_on_already_resolved(self):
        uow, factory, event_id, cmd = self._setup()
        cmd(factory, event_id=event_id, resolution="APPROVED", resolved_by="W001")
        uow.outbox.events.clear()

        # Second call on same event_id — already resolved
        result = cmd(factory, event_id=event_id, resolution="REJECTED", resolved_by="W002")
        # Must return existing state without re-resolving
        assert result["status"] == "APPROVED"
        assert len(uow.outbox.events) == 0  # no new outbox event

    def test_raises_value_error_for_invalid_resolution(self):
        from application.use_cases.pending_review_handlers import cmd_resolve_pending_review

        _, factory = _make_uow_factory()
        with pytest.raises(ValueError, match="Invalid resolution"):
            cmd_resolve_pending_review(
                factory, event_id=str(uuid.uuid4()), resolution="MAYBE", resolved_by="W001"
            )


# ---------------------------------------------------------------------------
# Structural: DecisionCorrelator no longer writes directly to Redis
# ---------------------------------------------------------------------------

import pathlib

_CONSUMER_SRC = (
    pathlib.Path(__file__).parent.parent.parent
    / "infrastructure" / "messaging" / "kafka_decision_consumer.py"
).read_text()

_WORKER_SRC = (
    pathlib.Path(__file__).parent.parent.parent
    / "scripts" / "simple_outbox_worker.py"
).read_text()


class TestDecisionCorrelatorManualReviewStructural:
    def test_imports_cmd_store_pending_review(self):
        """kafka_decision_consumer must import cmd_store_pending_review (PD-01)."""
        assert "cmd_store_pending_review" in _CONSUMER_SRC

    def test_calls_cmd_store_pending_review_in_manual_review_branch(self):
        """The MANUAL_REVIEW branch must call cmd_store_pending_review."""
        # Find the MANUAL_REVIEW branch
        branch_start = _CONSUMER_SRC.find('"MANUAL_REVIEW"')
        branch_end = _CONSUMER_SRC.find("return None", branch_start)
        branch = _CONSUMER_SRC[branch_start:branch_end]
        assert "cmd_store_pending_review" in branch, (
            "MANUAL_REVIEW branch must call cmd_store_pending_review (PD-01)"
        )

    def test_no_direct_setex_in_manual_review_branch(self):
        """The MANUAL_REVIEW branch must NOT contain a direct redis.setex (PD-01)."""
        branch_start = _CONSUMER_SRC.find('"MANUAL_REVIEW"')
        branch_end = _CONSUMER_SRC.find("return None", branch_start)
        branch = _CONSUMER_SRC[branch_start:branch_end]
        assert "self.redis.setex" not in branch, (
            "MANUAL_REVIEW branch must not write directly to Redis; use cmd_store_pending_review"
        )


# ---------------------------------------------------------------------------
# Structural: outbox worker handles PendingReview events
# ---------------------------------------------------------------------------

class TestOutboxWorkerPendingReviewProjectionsStructural:
    def test_pending_review_created_handled(self):
        """project_to_redis must handle PendingReviewCreated → setex."""
        assert "PendingReviewCreated" in _WORKER_SRC
        assert "pending_review_key" in _WORKER_SRC
        assert "setex" in _WORKER_SRC

    def test_pending_review_resolved_handled(self):
        """project_to_redis must handle PendingReviewResolved → delete."""
        assert "PendingReviewResolved" in _WORKER_SRC
        # Delete called after Resolved
        resolved_pos = _WORKER_SRC.find("PendingReviewResolved")
        resolved_block = _WORKER_SRC[resolved_pos:resolved_pos + 300]
        assert "delete" in resolved_block

    def test_pending_review_key_imported_in_worker(self):
        """simple_outbox_worker must import pending_review_key from redis module."""
        assert "pending_review_key" in _WORKER_SRC
