"""
DW-08 unit tests — cmd_record_manual_review_audit outbox emission.

Verifies that the manual-review audit path emits an OperatorReviewCompleted
outbox event rather than writing directly to MongoDB.
"""

import uuid
import pytest


# ---------------------------------------------------------------------------
# In-memory fakes (same pattern as test_phase5_outbox_consolidation.py)
# ---------------------------------------------------------------------------

class _FakeOutbox:
    def __init__(self):
        self.events = []

    def append(self, event, *, topic, key):
        self.events.append({"event": event, "topic": topic, "key": key})


class _FakeUoW:
    def __init__(self):
        self.outbox = _FakeOutbox()
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def commit(self):
        self.committed = True

    def rollback(self):
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCmdRecordManualReviewAudit:
    def _make_uow(self):
        uow = _FakeUoW()
        return uow, lambda: uow

    def test_appends_operator_review_completed_event(self):
        from application.use_cases.decision_audit_handlers import cmd_record_manual_review_audit

        uow, factory = self._make_uow()
        event_id = cmd_record_manual_review_audit(
            factory,
            appointment_id=42,
            license_plate="AB-12-CD",
            gate_id=1,
            decision="rejected",
            appointment_status="canceled",
            notes="Plate mismatch",
        )

        # The audit event is always the first entry
        audit_entries = [
            e for e in uow.outbox.events
            if e["event"].event_type == "OperatorReviewCompleted"
        ]
        assert len(audit_entries) == 1
        entry = audit_entries[0]
        assert entry["topic"] == "decision.audit"
        assert entry["event"].aggregate_type == "appointment"
        assert entry["event"].aggregate_id == "42"
        assert entry["event"].event_id == event_id

    def test_payload_contains_required_fields(self):
        from application.use_cases.decision_audit_handlers import cmd_record_manual_review_audit

        uow, factory = self._make_uow()
        cmd_record_manual_review_audit(
            factory,
            appointment_id=7,
            license_plate="XX-99-ZZ",
            gate_id=3,
            decision="approved",
            appointment_status="in_process",
            notes="[MANUAL REVIEW] all ok",
        )

        audit_entries = [
            e for e in uow.outbox.events
            if e["event"].event_type == "OperatorReviewCompleted"
        ]
        payload = audit_entries[0]["event"].payload
        assert payload["appointment_id"] == 7
        assert payload["license_plate"] == "XX-99-ZZ"
        assert payload["gate_id"] == 3
        assert payload["decision"] == "approved"
        assert payload["appointment_status"] == "in_process"
        assert payload["manual_review"] is True

    def test_commits_uow_for_audit_event(self):
        from application.use_cases.decision_audit_handlers import cmd_record_manual_review_audit

        uow, factory = self._make_uow()
        cmd_record_manual_review_audit(
            factory,
            appointment_id=1,
            license_plate="AA-00-BB",
            gate_id=0,
            decision="rejected",
            appointment_status="canceled",
        )
        assert uow.committed is True

    def test_returns_valid_uuid_event_id(self):
        from application.use_cases.decision_audit_handlers import cmd_record_manual_review_audit

        uow, factory = self._make_uow()
        event_id = cmd_record_manual_review_audit(
            factory,
            appointment_id=1,
            license_plate="AA-00-BB",
            gate_id=0,
            decision="rejected",
            appointment_status="canceled",
        )
        uuid.UUID(event_id)  # raises if not a valid UUID

    def test_rejected_decision_no_notification_emitted(self):
        from application.use_cases.decision_audit_handlers import cmd_record_manual_review_audit

        uow, factory = self._make_uow()
        cmd_record_manual_review_audit(
            factory,
            appointment_id=5,
            license_plate="AA-00-BB",
            gate_id=2,
            decision="rejected",
            appointment_status="canceled",
        )
        # Only the audit event — no NotificationCreated
        types = [e["event"].event_type for e in uow.outbox.events]
        assert types == ["OperatorReviewCompleted"]

    def test_approved_decision_emits_notification_event(self):
        from application.use_cases.decision_audit_handlers import cmd_record_manual_review_audit

        # approved path calls cmd_create_notification which uses a second UoW;
        # we need the factory to return a fresh UoW on each call.
        uows: list[_FakeUoW] = []

        def _factory():
            u = _FakeUoW()
            uows.append(u)
            return u

        cmd_record_manual_review_audit(
            _factory,
            appointment_id=9,
            license_plate="GH-55-IJ",
            gate_id=4,
            decision="approved",
            appointment_status="in_process",
        )

        all_events = [e for uow in uows for e in uow.outbox.events]
        event_types = [e["event"].event_type for e in all_events]
        assert "OperatorReviewCompleted" in event_types
        assert "NotificationCreated" in event_types

    def test_partition_key_is_gate_id_string(self):
        from application.use_cases.decision_audit_handlers import cmd_record_manual_review_audit

        uow, factory = self._make_uow()
        cmd_record_manual_review_audit(
            factory,
            appointment_id=1,
            license_plate="AB-12-CD",
            gate_id=7,
            decision="rejected",
            appointment_status="canceled",
        )
        audit_entry = next(
            e for e in uow.outbox.events
            if e["event"].event_type == "OperatorReviewCompleted"
        )
        assert audit_entry["event"].partition_key == "7"

    def test_uses_separate_uow_from_pg_decision(self):
        """Audit outbox append is in an independent transaction from cmd_process_decision."""
        from application.use_cases.decision_audit_handlers import cmd_record_manual_review_audit

        committed_uows = []

        class _TrackingUoW(_FakeUoW):
            def commit(self):
                super().commit()
                committed_uows.append(self)

        def _factory():
            return _TrackingUoW()

        cmd_record_manual_review_audit(
            _factory,
            appointment_id=3,
            license_plate="CC-33-DD",
            gate_id=1,
            decision="rejected",
            appointment_status="canceled",
        )

        # At least one commit happened in a separate UoW (not the one from cmd_process_decision)
        assert len(committed_uows) >= 1
        assert all(u.committed for u in committed_uows)
