"""
Phase 7 unit tests — DW-03/04/08: single Mongo write path + Redis clean-up.

DW-03: process_incoming_decision no longer calls persist_decision_event.
DW-04: command-path Redis invalidation/cache writes removed from process_incoming_decision.
DW-08: deprecated legacy write functions deleted from arrival_queries.py.
kafka: _persist_decision is a no-op; persist_infraction_event_from_kafka removed from consumer.
"""
import pathlib
import pytest

_DECISION_QUERIES_SRC = pathlib.Path(__file__).parents[2] / "application" / "queries" / "decision_queries.py"
_ARRIVAL_QUERIES_SRC = pathlib.Path(__file__).parents[2] / "application" / "queries" / "arrival_queries.py"
_KAFKA_CONSUMER_SRC = pathlib.Path(__file__).parents[2] / "infrastructure" / "messaging" / "kafka_decision_consumer.py"


# ---------------------------------------------------------------------------
# DW-03: process_incoming_decision — no direct Mongo writes
# ---------------------------------------------------------------------------

class TestDW03NoDirectMongoWrites:

    def test_process_incoming_decision_no_persist_decision_event_call(self):
        src = _DECISION_QUERIES_SRC.read_text()
        fn_start = src.index("def process_incoming_decision(")
        fn_end = src.index("\ndef ", fn_start + 1)
        fn_body = src[fn_start:fn_end]
        assert "persist_decision_event(" not in fn_body, (
            "process_incoming_decision must not call persist_decision_event — "
            "Mongo projection is the outbox worker's responsibility (DW-03)"
        )

    def test_process_incoming_decision_no_persist_infraction_call(self):
        src = _DECISION_QUERIES_SRC.read_text()
        fn_start = src.index("def process_incoming_decision(")
        fn_end = src.index("\ndef ", fn_start + 1)
        fn_body = src[fn_start:fn_end]
        assert "persist_infraction_event_from_kafka(" not in fn_body

    def test_persist_decision_event_deleted(self):
        src = _DECISION_QUERIES_SRC.read_text()
        assert "def persist_decision_event(" not in src, (
            "persist_decision_event must be deleted — outbox worker is sole Mongo writer (DW-03)"
        )

    def test_persist_detection_event_deleted(self):
        src = _DECISION_QUERIES_SRC.read_text()
        assert "def persist_detection_event(" not in src, (
            "persist_detection_event must be deleted — outbox worker is sole Mongo writer (DW-03)"
        )

    def test_persist_infraction_event_from_kafka_deleted(self):
        src = _DECISION_QUERIES_SRC.read_text()
        assert "def persist_infraction_event_from_kafka(" not in src, (
            "persist_infraction_event_from_kafka must be deleted — no active callers (DW-03)"
        )


# ---------------------------------------------------------------------------
# DW-04: no command-path Redis cache/invalidation writes
# ---------------------------------------------------------------------------

class TestDW04NoCommandPathRedisWrites:

    def _process_fn_body(self) -> str:
        src = _DECISION_QUERIES_SRC.read_text()
        fn_start = src.index("def process_incoming_decision(")
        fn_end = src.index("\ndef ", fn_start + 1)
        return src[fn_start:fn_end]

    def test_no_cache_decision_result_call(self):
        assert "cache_decision_result(" not in self._process_fn_body(), (
            "process_incoming_decision must not call cache_decision_result (DW-04)"
        )

    def test_no_invalidate_appointment_cache_call(self):
        assert "invalidate_appointment_cache(" not in self._process_fn_body(), (
            "process_incoming_decision must not call invalidate_appointment_cache (DW-04) — "
            "outbox worker handles this"
        )

    def test_no_invalidate_license_plate_cache_call(self):
        assert "invalidate_license_plate_cache(" not in self._process_fn_body()

    def test_invalidate_imports_removed(self):
        src = _DECISION_QUERIES_SRC.read_text()
        assert "invalidate_appointment_cache" not in src.splitlines()[0:35].__str__() or \
               "invalidate_appointment_cache" not in src, True
        # Verify not imported at module level
        import_block_end = src.index("logger = logging")
        import_block = src[:import_block_end]
        assert "invalidate_appointment_cache" not in import_block
        assert "invalidate_license_plate_cache" not in import_block


# ---------------------------------------------------------------------------
# DW-08: deprecated legacy writers deleted from arrival_queries.py
# ---------------------------------------------------------------------------

class TestDW08LegacyWritersDeleted:

    @pytest.mark.parametrize("fn_name", [
        "update_appointment_status",
        "create_visit_for_appointment",
        "update_visit_status",
        "update_appointment_from_decision",
        "flag_appointment_highway_infraction",
    ])
    def test_legacy_function_removed(self, fn_name):
        src = _ARRIVAL_QUERIES_SRC.read_text()
        assert f"def {fn_name}(" not in src, (
            f"{fn_name} must be removed from arrival_queries.py (DW-08)"
        )


# ---------------------------------------------------------------------------
# kafka_decision_consumer: _persist_decision is a no-op
# ---------------------------------------------------------------------------

class TestKafkaConsumerDW03:

    def test_persist_decision_event_not_imported(self):
        src = _KAFKA_CONSUMER_SRC.read_text()
        import_block_end = src.index("logger = logging") if "logger = logging" in src else src.index("class ")
        import_block = src[:import_block_end]
        assert "persist_decision_event" not in import_block, (
            "kafka_decision_consumer must not import persist_decision_event (DW-03)"
        )

    def test_persist_infraction_event_not_imported(self):
        src = _KAFKA_CONSUMER_SRC.read_text()
        import_block_end = src.index("logger = logging") if "logger = logging" in src else src.index("class ")
        import_block = src[:import_block_end]
        assert "persist_infraction_event_from_kafka" not in import_block

    def test_persist_decision_method_is_noop(self):
        src = _KAFKA_CONSUMER_SRC.read_text()
        fn_start = src.index("async def _persist_decision(")
        try:
            fn_end = src.index("\n    async def ", fn_start + 1)
        except ValueError:
            try:
                fn_end = src.index("\n    def ", fn_start + 1)
            except ValueError:
                fn_end = len(src)
        fn_body = src[fn_start:fn_end]
        # Must NOT call the deprecated persist functions
        assert "persist_decision_event(" not in fn_body
        assert "run_in_executor" not in fn_body

    def test_store_infraction_no_mongo_write(self):
        src = _KAFKA_CONSUMER_SRC.read_text()
        fn_start = src.index("async def _store_infraction_decision(")
        try:
            fn_end = src.index("\n    async def ", fn_start + 1)
        except ValueError:
            try:
                fn_end = src.index("\n    def ", fn_start + 1)
            except ValueError:
                fn_end = len(src)
        fn_body = src[fn_start:fn_end]
        assert "persist_infraction_event_from_kafka(" not in fn_body
        assert "persist_decision_event(" not in fn_body
