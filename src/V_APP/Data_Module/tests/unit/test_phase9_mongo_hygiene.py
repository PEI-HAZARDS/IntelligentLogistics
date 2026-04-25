"""
Phase 9 unit tests — Mongo infra hygiene.

- cache_metadata_collection removed
- TTL constants defined for every retention-bounded collection
- TTL index calls present for each collection (structural)
- appointments_read unique index declared
- New analytics collections declared
"""
import pathlib

import pytest

_MONGO_SRC = pathlib.Path(__file__).parents[2] / "infrastructure" / "persistence" / "mongo.py"


def _src() -> str:
    return _MONGO_SRC.read_text()


# ---------------------------------------------------------------------------
# cache_metadata removed
# ---------------------------------------------------------------------------

class TestCacheMetadataRemoved:

    def test_collection_object_gone(self):
        assert "cache_metadata_collection" not in _src(), (
            "cache_metadata_collection must be removed from mongo.py (Phase 9)"
        )

    def test_index_call_gone(self):
        assert "idx_cache_pattern_timestamp" not in _src()


# ---------------------------------------------------------------------------
# TTL constants
# ---------------------------------------------------------------------------

class TestTTLConstants:

    def test_ttl_notifications_defined(self):
        assert "TTL_NOTIFICATIONS" in _src()

    def test_ttl_agent_detections_defined(self):
        assert "TTL_AGENT_DETECTIONS" in _src()

    def test_ttl_decision_events_defined(self):
        assert "TTL_DECISION_EVENTS" in _src()

    def test_ttl_legacy_defined(self):
        assert "TTL_LEGACY" in _src()

    def test_ttl_system_logs_defined(self):
        assert "TTL_SYSTEM_LOGS" in _src()

    def test_ttl_ocr_failures_defined(self):
        assert "TTL_OCR_FAILURES" in _src()

    def test_ttl_stats_long_defined(self):
        assert "TTL_STATS_LONG" in _src()


# ---------------------------------------------------------------------------
# TTL index creation calls
# ---------------------------------------------------------------------------

class TestTTLIndexCalls:

    @pytest.mark.parametrize("index_name", [
        "idx_notif_ttl",
        "idx_detections_ttl",
        "idx_events_ttl",
        "idx_system_logs_ttl",
        "idx_ocr_failures_ttl",
        "idx_agent_detections_ttl",
        "idx_decision_events_ttl",
        "idx_stats_hourly_ttl",
        "idx_stats_daily_ttl",
        "idx_op_perf_ttl",
        "idx_company_metrics_ttl",
    ])
    def test_ttl_index_declared(self, index_name):
        assert index_name in _src(), (
            f"TTL index {index_name!r} must be declared in create_indexes()"
        )

    def test_expire_after_seconds_used(self):
        assert "expireAfterSeconds" in _src()


# ---------------------------------------------------------------------------
# appointments_read unique index
# ---------------------------------------------------------------------------

class TestAppointmentsReadIndex:

    def test_collection_declared(self):
        assert "appointments_read_collection" in _src()

    def test_unique_index_on_appointment_id(self):
        src = _src()
        assert "idx_appts_read_appointment_id" in src
        # Unique constraint must be present
        fn_start = src.index("def create_indexes(")
        fn_body = src[fn_start:]
        # Find appointments_read unique index block
        assert "appointments_read_collection" in fn_body
        assert '"unique": True' in fn_body or "unique=True" in fn_body


# ---------------------------------------------------------------------------
# New analytics collections declared
# ---------------------------------------------------------------------------

class TestNewAnalyticsCollections:

    @pytest.mark.parametrize("col_name", [
        "statistics_daily_collection",
        "operator_performance_collection",
        "company_metrics_collection",
    ])
    def test_collection_declared(self, col_name):
        assert col_name in _src(), (
            f"{col_name} must be declared in mongo.py (Phase 9)"
        )
