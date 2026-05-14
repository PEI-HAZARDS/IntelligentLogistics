"""
Unit tests for Redis atomicity and TTL-correctness fixes.

Three bugs corrected in redis.py:

  FIX-1 (counter TTL reset) — increment_counter must only call expire when the
         key is created (incrby return == amount), not on every increment.
         A busy gate was resetting its 2-hour window on every detection, so the
         counter key could never expire.

  FIX-2 (rate-limit TOCTOU) — check_rate_limit must use an atomic INCR+EXPIRE
         pipeline instead of GET→SETEX.  The old pattern allowed two simultaneous
         first requests to both see None and both pass under the limit.

  FIX-3 (LP-lookup atomicity) — cache_license_plate_appointments must write via
         SETEX (one atomic command) instead of DELETE+SADD+EXPIRE (three commands).
         A crash between SADD and EXPIRE left the key without a TTL, leaking forever.
"""

import json
import sys
import pytest
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Import the REAL redis module regardless of what prior tests put in sys.modules.
# test_decision_state_machine.py injects a MagicMock via sys.modules.setdefault()
# to suppress the Redis connection at import time and never restores it.
# We need the real module to test its internal behaviour.
# ---------------------------------------------------------------------------
_KEY = "infrastructure.persistence.redis"
_saved_module = sys.modules.get(_KEY)

# Remove any mock so the real module is imported fresh.
sys.modules.pop(_KEY, None)
# Also remove transitive entries that may have been mocked.
for _sub in [k for k in sys.modules if k.startswith("infrastructure.persistence.")]:
    sys.modules.pop(_sub, None)

import infrastructure.persistence.redis as _rmod  # noqa: E402 — must come after sys.modules manipulation

# Restore the mock so test_decision_state_machine.py still works if imported later.
if _saved_module is not None:
    sys.modules[_KEY] = _saved_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_redis_mock():
    m = MagicMock()
    m.pipeline.return_value.__enter__ = MagicMock(return_value=m.pipeline.return_value)
    m.pipeline.return_value.__exit__ = MagicMock(return_value=False)
    return m


def _swap(mock_redis):
    """Context manager: swap redis_client on the real module for the duration."""
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        original = _rmod.redis_client
        _rmod.redis_client = mock_redis
        try:
            yield
        finally:
            _rmod.redis_client = original

    return _ctx()


# ---------------------------------------------------------------------------
# FIX-1  counter TTL only set on creation
# ---------------------------------------------------------------------------

class TestIncrementCounterTTL:
    """expire must be called exactly once — when the key is first created."""

    def test_expire_called_on_first_increment(self):
        mock_redis = _make_redis_mock()
        mock_redis.incrby.return_value = 1  # key created
        with _swap(mock_redis):
            _rmod.increment_counter(1, "test")
        mock_redis.expire.assert_called_once()

    def test_expire_not_called_on_subsequent_increments(self):
        mock_redis = _make_redis_mock()
        mock_redis.incrby.side_effect = [1, 2, 3, 4, 5]
        with _swap(mock_redis):
            for _ in range(5):
                _rmod.increment_counter(1, "test")
        assert mock_redis.expire.call_count == 1

    def test_expire_uses_correct_ttl(self):
        mock_redis = _make_redis_mock()
        mock_redis.incrby.return_value = 1
        with _swap(mock_redis):
            _rmod.increment_counter(1, "metric")
        _, ttl_arg = mock_redis.expire.call_args[0]
        assert ttl_arg == _rmod.TTL_COUNTER_REALTIME

    def test_expire_not_called_when_key_already_existed(self):
        """If key existed before our increment, incrby returns > amount → no expire."""
        mock_redis = _make_redis_mock()
        mock_redis.incrby.return_value = 42
        with _swap(mock_redis):
            _rmod.increment_counter(1, "metric")
        mock_redis.expire.assert_not_called()


# ---------------------------------------------------------------------------
# FIX-2  rate-limit atomic pipeline (no GET→SETEX TOCTOU)
# ---------------------------------------------------------------------------

class TestCheckRateLimitAtomic:
    """check_rate_limit must use pipeline(INCR + EXPIRE), never GET."""

    def _setup_pipeline_result(self, mock_redis, count):
        pipe = MagicMock()
        pipe.execute.return_value = (count, True)
        mock_redis.pipeline.return_value = pipe
        return pipe

    def test_uses_pipeline_not_get(self):
        mock_redis = _make_redis_mock()
        self._setup_pipeline_result(mock_redis, 1)
        with _swap(mock_redis):
            _rmod.check_rate_limit("ep", "c")
        mock_redis.get.assert_not_called()
        mock_redis.pipeline.assert_called_once()

    def test_pipeline_calls_incr_and_expire(self):
        mock_redis = _make_redis_mock()
        pipe = self._setup_pipeline_result(mock_redis, 1)
        with _swap(mock_redis):
            _rmod.check_rate_limit("ep", "c")
        pipe.incr.assert_called_once()
        pipe.expire.assert_called_once()

    def test_allows_request_within_limit(self):
        mock_redis = _make_redis_mock()
        self._setup_pipeline_result(mock_redis, 59)
        with _swap(mock_redis):
            assert _rmod.check_rate_limit("ep", "c", limit=60) is True

    def test_allows_request_at_limit(self):
        mock_redis = _make_redis_mock()
        self._setup_pipeline_result(mock_redis, 60)
        with _swap(mock_redis):
            assert _rmod.check_rate_limit("ep", "c", limit=60) is True

    def test_blocks_request_over_limit(self):
        mock_redis = _make_redis_mock()
        self._setup_pipeline_result(mock_redis, 61)
        with _swap(mock_redis):
            assert _rmod.check_rate_limit("ep", "c", limit=60) is False

    def test_allows_on_redis_error(self):
        mock_redis = _make_redis_mock()
        mock_redis.pipeline.side_effect = Exception("Redis unavailable")
        with _swap(mock_redis):
            assert _rmod.check_rate_limit("ep", "c") is True


# ---------------------------------------------------------------------------
# FIX-3  LP lookup atomic SETEX (single command, no TTL leak)
# ---------------------------------------------------------------------------

class TestLicensePlateLookupAtomic:
    """cache_license_plate_appointments must use SETEX, not DELETE+SADD+EXPIRE."""

    def test_uses_setex_not_sadd(self):
        mock_redis = _make_redis_mock()
        with _swap(mock_redis):
            _rmod.cache_license_plate_appointments("AB-12-CD", [1, 2, 3])
        mock_redis.setex.assert_called_once()
        mock_redis.sadd.assert_not_called()

    def test_setex_not_preceded_by_delete(self):
        mock_redis = _make_redis_mock()
        with _swap(mock_redis):
            _rmod.cache_license_plate_appointments("AB-12-CD", [1, 2, 3])
        mock_redis.delete.assert_not_called()

    def test_setex_uses_correct_ttl(self):
        mock_redis = _make_redis_mock()
        with _swap(mock_redis):
            _rmod.cache_license_plate_appointments("AB-12-CD", [1])
        args = mock_redis.setex.call_args[0]
        assert args[1] == _rmod.TTL_LICENSE_PLATE_LOOKUP

    def test_stored_value_is_valid_json_list(self):
        mock_redis = _make_redis_mock()
        with _swap(mock_redis):
            _rmod.cache_license_plate_appointments("AB-12-CD", [10, 20, 30])
        args = mock_redis.setex.call_args[0]
        assert sorted(int(x) for x in json.loads(args[2])) == [10, 20, 30]

    def test_get_reads_json_not_set(self):
        """get_cached_license_plate_appointments must use GET, not SMEMBERS."""
        mock_redis = _make_redis_mock()
        mock_redis.get.return_value = json.dumps(["7", "8"])
        with _swap(mock_redis):
            result = _rmod.get_cached_license_plate_appointments("AB-12-CD")
        assert sorted(result) == [7, 8]
        mock_redis.smembers.assert_not_called()

    def test_get_returns_none_on_miss(self):
        mock_redis = _make_redis_mock()
        mock_redis.get.return_value = None
        with _swap(mock_redis):
            result = _rmod.get_cached_license_plate_appointments("ZZ-00-ZZ")
        assert result is None

    def test_empty_list_stored_and_retrieved(self):
        mock_redis = _make_redis_mock()
        with _swap(mock_redis):
            _rmod.cache_license_plate_appointments("AB-12-CD", [])
        args = mock_redis.setex.call_args[0]
        assert json.loads(args[2]) == []
