"""
Phase 11 unit tests — Dead code + demo noise cleanup.

- utils/rate_limit.py deleted
- cache_detection / get_cached_detection removed from cache_queries.py
- get_all_active_counters import removed from worker_queries.py
- routes/events.py + event_queries.py carry deprecation warnings
- data_init_demo.py: plates env-overridable, MAX_ARRIVALS env-configurable
"""
import pathlib
import pytest

_BASE = pathlib.Path(__file__).parents[2]


def _src(rel: str) -> str:
    return (_BASE / rel).read_text()


# ---------------------------------------------------------------------------
# utils/rate_limit.py deleted
# ---------------------------------------------------------------------------

class TestRateLimitFileDeleted:

    def test_rate_limit_file_gone(self):
        path = _BASE / "utils" / "rate_limit.py"
        assert not path.exists(), (
            "utils/rate_limit.py must be deleted — redis.py::check_rate_limit "
            "is the canonical implementation (Phase 11)"
        )


# ---------------------------------------------------------------------------
# cache_queries.py: unused detection cache helpers removed
# ---------------------------------------------------------------------------

class TestCacheDetectionRemoved:

    def test_cache_detection_gone(self):
        src = _src("application/queries/cache_queries.py")
        assert "def cache_detection(" not in src, (
            "cache_detection was unused — removed in Phase 11"
        )

    def test_get_cached_detection_gone(self):
        src = _src("application/queries/cache_queries.py")
        assert "def get_cached_detection(" not in src, (
            "get_cached_detection was unused — removed in Phase 11"
        )

    def test_get_or_cache_still_present(self):
        src = _src("application/queries/cache_queries.py")
        assert "def get_or_cache(" in src, "get_or_cache must be preserved"


# ---------------------------------------------------------------------------
# worker_queries.py: unused import removed
# ---------------------------------------------------------------------------

class TestWorkerQueriesImportClean:

    def test_get_all_active_counters_not_imported(self):
        src = _src("application/queries/worker_queries.py")
        assert "get_all_active_counters" not in src, (
            "Unused get_all_active_counters import must be removed (Phase 11)"
        )


# ---------------------------------------------------------------------------
# routes/events.py + event_queries.py: deprecation warnings
# ---------------------------------------------------------------------------

class TestEventsDeprecated:

    def test_events_route_has_deprecated_marker(self):
        src = _src("routes/events.py")
        assert "DEPRECATED" in src

    def test_events_route_logs_warning(self):
        src = _src("routes/events.py")
        assert "logger.warning" in src or "logging.warning" in src

    def test_event_queries_has_deprecated_docstring(self):
        src = _src("application/queries/event_queries.py")
        assert "DEPRECATED" in src


# ---------------------------------------------------------------------------
# data_init_demo.py: env-overridable plates + MAX_ARRIVALS
# ---------------------------------------------------------------------------

class TestDataInitDemoEnvConfig:

    def test_demo_video1_plates_env_var(self):
        src = _src("scripts/data_init_demo.py")
        assert "DEMO_VIDEO1_PLATES" in src

    def test_demo_video2_plates_env_var(self):
        src = _src("scripts/data_init_demo.py")
        assert "DEMO_VIDEO2_PLATES" in src

    def test_base_daily_controls_volume(self):
        # MAX_ARRIVALS was replaced by BASE_DAILY + monthly load factors
        src = _src("scripts/data_init_demo.py")
        assert "BASE_DAILY" in src

    def test_monthly_load_factors_present(self):
        src = _src("scripts/data_init_demo.py")
        assert "_MONTHLY_LOAD" in src

    def test_company_delay_profiles_present(self):
        src = _src("scripts/data_init_demo.py")
        assert "_COMPANY_DELAY_PROFILES" in src
