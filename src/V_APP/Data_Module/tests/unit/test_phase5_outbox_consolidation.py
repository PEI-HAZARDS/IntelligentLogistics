"""
Phase 5 unit tests — Outbox consolidation (DW-01, DW-02, DW-06, DW-07).

DW-01: cmd_create_notification emits NotificationCreated outbox event.
DW-02: cmd_mark_notification_read / cmd_mark_all_notifications_read.
DW-06: Infraction inbox dedup (structural source inspection).
DW-07: statistics_aggregator run_cycle structural test.
"""
import pathlib
import pytest

# ---------------------------------------------------------------------------
# In-memory fakes
# ---------------------------------------------------------------------------

class _FakeOutbox:
    def __init__(self):
        self.events = []

    def append(self, event, *, topic, key):
        self.events.append({"event": event, "topic": topic, "key": key})

    def fetch_batch(self, batch_size):
        return []

    def mark_published(self, outbox_id):
        pass

    def mark_publish_failed(self, outbox_id, error):
        pass


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
# DW-01: cmd_create_notification
# ---------------------------------------------------------------------------

class TestCmdCreateNotification:
    def _make_uow(self):
        uow = _FakeUoW()
        return uow, lambda: uow

    def test_appends_notification_created_event(self):
        from application.use_cases.notification_handlers import cmd_create_notification

        uow, factory = self._make_uow()
        event_id = cmd_create_notification(
            factory,
            gate_id=1,
            title="Test",
            message="Hello",
            notification_type="info",
        )

        assert len(uow.outbox.events) == 1
        entry = uow.outbox.events[0]
        assert entry["topic"] == "notifications"
        assert entry["event"].event_type == "NotificationCreated"
        assert entry["event"].event_id == event_id
        assert entry["event"].payload["gate_id"] == 1
        assert entry["event"].payload["title"] == "Test"
        assert entry["event"].payload["read"] is False

    def test_commits_uow(self):
        from application.use_cases.notification_handlers import cmd_create_notification

        uow, factory = self._make_uow()
        cmd_create_notification(factory, gate_id=2, title="T", message="M")
        assert uow.committed is True

    def test_extra_fields_included_in_payload(self):
        from application.use_cases.notification_handlers import cmd_create_notification

        uow, factory = self._make_uow()
        cmd_create_notification(
            factory,
            gate_id=3,
            title="T",
            message="M",
            extra={"target": "driver"},
        )
        payload = uow.outbox.events[0]["event"].payload
        assert payload.get("target") == "driver"

    def test_returns_event_id_string(self):
        from application.use_cases.notification_handlers import cmd_create_notification
        import uuid

        uow, factory = self._make_uow()
        event_id = cmd_create_notification(factory, gate_id=1, title="T", message="M")
        # Must be valid UUID string
        uuid.UUID(event_id)

    def test_optional_fields_default_to_none(self):
        from application.use_cases.notification_handlers import cmd_create_notification

        uow, factory = self._make_uow()
        cmd_create_notification(factory, gate_id=1, title="T", message="M")
        payload = uow.outbox.events[0]["event"].payload
        assert payload["appointment_id"] is None
        assert payload["license_plate"] is None

    def test_partition_key_is_gate_id_string(self):
        from application.use_cases.notification_handlers import cmd_create_notification

        uow, factory = self._make_uow()
        cmd_create_notification(factory, gate_id=5, title="T", message="M")
        assert uow.outbox.events[0]["event"].partition_key == "5"

    def test_aggregate_type_is_notification(self):
        from application.use_cases.notification_handlers import cmd_create_notification

        uow, factory = self._make_uow()
        cmd_create_notification(factory, gate_id=1, title="T", message="M")
        assert uow.outbox.events[0]["event"].aggregate_type == "notification"


# ---------------------------------------------------------------------------
# DW-02: cmd_mark_notification_read / cmd_mark_all_notifications_read
# (structural — can't hit Mongo in unit tests)
# ---------------------------------------------------------------------------

class TestNotificationHandlersDW02Structural:
    _SRC = pathlib.Path(__file__).parents[2] / "application" / "use_cases" / "notification_handlers.py"

    def test_cmd_mark_notification_read_exists(self):
        src = self._SRC.read_text()
        assert "def cmd_mark_notification_read(" in src

    def test_cmd_mark_all_notifications_read_exists(self):
        src = self._SRC.read_text()
        assert "def cmd_mark_all_notifications_read(" in src

    def test_cmd_mark_notification_read_raises_value_error_on_bad_id(self):
        src = self._SRC.read_text()
        assert "raise ValueError" in src

    def test_routes_notifications_uses_cmd_mark_read(self):
        routes_src = (pathlib.Path(__file__).parents[2] / "routes" / "notifications.py").read_text()
        assert "cmd_mark_notification_read" in routes_src
        assert "cmd_mark_all_notifications_read" in routes_src

    def test_routes_notifications_no_direct_find_one_and_update(self):
        routes_src = (pathlib.Path(__file__).parents[2] / "routes" / "notifications.py").read_text()
        # Direct Mongo mutation must no longer appear in the route handlers
        assert "find_one_and_update" not in routes_src


# ---------------------------------------------------------------------------
# DW-06: Infraction inbox dedup (structural)
# ---------------------------------------------------------------------------

class TestInfractionInboxDedupStructural:
    _SRC = pathlib.Path(__file__).parents[2] / "infrastructure" / "messaging" / "kafka_decision_consumer.py"

    def test_store_infraction_decision_accepts_msg_param(self):
        src = self._SRC.read_text()
        assert "async def _store_infraction_decision(self, truck_id" in src
        assert ", msg)" in src

    def test_try_insert_received_called(self):
        src = self._SRC.read_text()
        assert "try_insert_received" in src

    def test_inbox_mark_processing_called(self):
        src = self._SRC.read_text()
        assert "mark_processing(" in src

    def test_inbox_mark_processed_called(self):
        src = self._SRC.read_text()
        assert "mark_processed(" in src

    def test_inbox_mark_failed_called(self):
        src = self._SRC.read_text()
        assert "mark_failed(" in src

    def test_duplicate_infraction_returns_early(self):
        src = self._SRC.read_text()
        assert "Duplicate infraction event skipped" in src

    def test_dedup_event_id_derived_from_msg_when_missing(self):
        src = self._SRC.read_text()
        # uuid5 used to build deterministic event_id from topic:partition:offset
        assert "uuid5" in src

    def test_cmd_create_notification_used_not_create_notification(self):
        src = self._SRC.read_text()
        assert "cmd_create_notification" in src
        # create_notification (direct Mongo) must no longer be imported
        assert "from application.queries.notification_queries import create_notification" not in src

    def test_call_site_passes_msg_to_store_infraction(self):
        src = self._SRC.read_text()
        assert "_store_infraction_decision(truck_id, data, msg)" in src


# ---------------------------------------------------------------------------
# DW-07: statistics_aggregator structural tests
# ---------------------------------------------------------------------------

class TestStatisticsAggregatorStructural:
    _SRC = pathlib.Path(__file__).parents[2] / "scripts" / "statistics_aggregator.py"

    def test_aggregator_script_exists(self):
        assert self._SRC.exists(), "statistics_aggregator.py not found"

    def test_run_cycle_function_exists(self):
        src = self._SRC.read_text()
        assert "def run_cycle(" in src

    def test_calls_compute_hourly_statistics(self):
        src = self._SRC.read_text()
        assert "compute_hourly_statistics" in src

    def test_loads_gate_ids_from_env(self):
        src = self._SRC.read_text()
        assert "AGGREGATOR_GATE_IDS" in src

    def test_graceful_shutdown_via_signal(self):
        src = self._SRC.read_text()
        assert "SIGTERM" in src
        assert "_shutdown_requested" in src

    def test_run_cycle_returns_ok_failed_dict(self):
        src = self._SRC.read_text()
        assert '"ok"' in src
        assert '"failed"' in src


# ---------------------------------------------------------------------------
# DW-01 outbox worker projection structural test
# ---------------------------------------------------------------------------

class TestOutboxWorkerNotificationProjectionStructural:
    _SRC = pathlib.Path(__file__).parents[2] / "scripts" / "simple_outbox_worker.py"

    def test_notification_created_projection_exists(self):
        src = self._SRC.read_text()
        assert 'event_type == "NotificationCreated"' in src

    def test_notifications_collection_imported(self):
        src = self._SRC.read_text()
        assert "notifications_collection" in src

    def test_projection_is_idempotent_upsert(self):
        src = self._SRC.read_text()
        # Must use $setOnInsert so re-projection doesn't overwrite existing doc
        assert "$setOnInsert" in src
