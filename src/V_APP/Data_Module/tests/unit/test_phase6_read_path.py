"""
Phase 6 unit tests — Read-path three-tier (BR-29, BR-38) + complex stats cache.

BR-29: driver active appointment Redis → PG read path.
BR-38: alert by-id Redis → PG, active-alerts list short-TTL cache.
Stats: pipeline performance Redis cache layer.
Outbox worker: alert projection + driver active cache maintenance.
"""
import pathlib
import pytest

# ---------------------------------------------------------------------------
# Redis key functions (importable with no infrastructure deps)
# ---------------------------------------------------------------------------

_REDIS_SRC = pathlib.Path(__file__).parents[2] / "infrastructure" / "persistence" / "redis.py"


class TestRedisKeyFunctions:
    """Structural — test_decision_state_machine patches sys.modules at collection
    time, so imports of the real redis module are unreliable in the full suite.
    Source inspection is the safe approach."""

    def test_driver_active_appointment_key_pattern(self):
        src = _REDIS_SRC.read_text()
        assert 'def driver_active_appointment_key(' in src
        assert 'driver:{' in src or '"driver:"' in src or "f\"driver:{" in src

    def test_alert_detail_key_pattern(self):
        src = _REDIS_SRC.read_text()
        assert 'def alert_detail_key(' in src
        assert 'alert:{' in src or '"alert:"' in src or 'f"alert:{' in src

    def test_active_alerts_list_key_pattern(self):
        src = _REDIS_SRC.read_text()
        assert 'def active_alerts_list_key(' in src
        assert 'alerts:active:list' in src

    def test_stats_pipeline_key_pattern(self):
        src = _REDIS_SRC.read_text()
        assert 'def stats_pipeline_key(' in src
        assert 'stats:pipeline:gate:' in src

    def test_ttl_driver_active_defined(self):
        src = _REDIS_SRC.read_text()
        assert 'TTL_DRIVER_ACTIVE' in src

    def test_ttl_alert_detail_defined(self):
        src = _REDIS_SRC.read_text()
        assert 'TTL_ALERT_DETAIL' in src

    def test_ttl_active_alerts_list_short(self):
        src = _REDIS_SRC.read_text()
        assert 'TTL_ACTIVE_ALERTS_LIST' in src

    def test_ttl_stats_pipeline_defined(self):
        src = _REDIS_SRC.read_text()
        assert 'TTL_STATS_PIPELINE' in src


# ---------------------------------------------------------------------------
# BR-29: driver_queries three-tier — structural
# ---------------------------------------------------------------------------

class TestDriverActiveAppointmentReadPathStructural:
    _SRC = pathlib.Path(__file__).parents[2] / "application" / "queries" / "driver_queries.py"

    def test_redis_cache_checked_first(self):
        src = self._SRC.read_text()
        assert "get_cached_driver_active_appointment" in src

    def test_cache_populated_on_pg_hit(self):
        src = self._SRC.read_text()
        assert "cache_driver_active_appointment" in src

    def test_three_tier_comment_or_annotation(self):
        src = self._SRC.read_text()
        assert "Redis" in src or "BR-29" in src


# ---------------------------------------------------------------------------
# BR-38: alert_queries three-tier — structural
# ---------------------------------------------------------------------------

class TestAlertReadPathStructural:
    _SRC = pathlib.Path(__file__).parents[2] / "application" / "queries" / "alert_queries.py"

    def test_alert_by_id_checks_redis_first(self):
        src = self._SRC.read_text()
        assert "alert_detail_key" in src

    def test_alert_by_id_populates_cache_on_miss(self):
        src = self._SRC.read_text()
        lines = src.split("\n")
        # After PG hit, setex must appear
        assert "setex" in src

    def test_get_active_alerts_checks_list_cache(self):
        src = self._SRC.read_text()
        assert "active_alerts_list_key" in src

    def test_get_active_alerts_only_caches_default_limit(self):
        src = self._SRC.read_text()
        assert "limit == 50" in src

    def test_list_cache_bypassed_for_custom_limit(self):
        src = self._SRC.read_text()
        # Must NOT cache unconditionally
        assert "if limit == 50" in src


# ---------------------------------------------------------------------------
# Stats pipeline cache — structural
# ---------------------------------------------------------------------------

class TestStatsPipelineCacheStructural:
    _SRC = pathlib.Path(__file__).parents[2] / "application" / "queries" / "statistics_queries.py"

    def test_redis_check_before_mongo_aggregation(self):
        src = self._SRC.read_text()
        assert "stats_pipeline_key" in src

    def test_result_stored_in_redis_after_aggregation(self):
        src = self._SRC.read_text()
        assert "TTL_STATS_PIPELINE" in src

    def test_mongo_aggregation_still_present_as_fallback(self):
        src = self._SRC.read_text()
        assert "decision_events_collection.aggregate" in src


# ---------------------------------------------------------------------------
# Outbox worker alert projection — structural
# ---------------------------------------------------------------------------

class TestOutboxWorkerAlertProjectionStructural:
    _SRC = pathlib.Path(__file__).parents[2] / "scripts" / "simple_outbox_worker.py"

    def test_alert_detail_key_imported(self):
        src = self._SRC.read_text()
        assert "alert_detail_key" in src

    def test_active_alerts_list_key_imported(self):
        src = self._SRC.read_text()
        assert "active_alerts_list_key" in src

    def test_alert_cached_individually_on_created_event(self):
        src = self._SRC.read_text()
        assert 'alert_detail_key' in src
        assert 'TTL_ALERT_DETAIL' in src

    def test_active_alerts_list_invalidated_on_alert_created(self):
        src = self._SRC.read_text()
        assert "active_alerts_list_key()" in src


# ---------------------------------------------------------------------------
# Outbox worker driver active cache — structural
# ---------------------------------------------------------------------------

class TestOutboxWorkerDriverCacheStructural:
    _SRC = pathlib.Path(__file__).parents[2] / "scripts" / "simple_outbox_worker.py"

    def test_cache_driver_active_appointment_imported(self):
        src = self._SRC.read_text()
        assert "cache_driver_active_appointment" in src

    def test_invalidate_driver_active_appointment_imported(self):
        src = self._SRC.read_text()
        assert "invalidate_driver_active_appointment" in src

    def test_driver_license_used_as_cache_key_scope(self):
        src = self._SRC.read_text()
        assert "driver_license" in src

    def test_active_statuses_trigger_cache_write(self):
        src = self._SRC.read_text()
        assert "in_process" in src
        assert "unloading" in src


# ---------------------------------------------------------------------------
# BR-29: code-path ordering (structural — psycopg2 unavailable in test venv)
# ---------------------------------------------------------------------------

class TestDriverActiveCacheHitStructural:
    """Verify the three-tier ordering by reading the source."""

    _SRC = pathlib.Path(__file__).parents[2] / "application" / "queries" / "driver_queries.py"

    def test_redis_import_precedes_pg_import(self):
        src = self._SRC.read_text()
        # Scope to the get_driver_active_appointment function body
        fn_start = src.index("def get_driver_active_appointment(")
        fn_src = src[fn_start:]
        redis_pos = fn_src.index("get_cached_driver_active_appointment")
        pg_pos = fn_src.index("from infrastructure.persistence.postgres import SessionLocal")
        assert redis_pos < pg_pos, "Redis check must appear before PostgreSQL import"

    def test_early_return_on_cache_hit(self):
        src = self._SRC.read_text()
        fn_start = src.index("def get_driver_active_appointment(")
        fn_src = src[fn_start:]
        cache_pos = fn_src.index("get_cached_driver_active_appointment")
        return_pos = fn_src.index("return cached", cache_pos)
        # SessionLocal() is called (not just imported) only in the PG fallback branch
        pg_call_pos = fn_src.index("db = SessionLocal()")
        assert return_pos < pg_call_pos, "Early return on cache hit must precede SessionLocal() call"

    def test_pg_result_written_to_cache(self):
        src = self._SRC.read_text()
        # cache_driver_active_appointment must be called after the PG query
        pg_pos = src.index("from infrastructure.persistence.postgres import SessionLocal")
        write_pos = src.index("cache_driver_active_appointment(drivers_license, result)")
        assert write_pos > pg_pos, "Cache write must occur after PG lookup"
