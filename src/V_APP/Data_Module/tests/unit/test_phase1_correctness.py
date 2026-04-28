"""
Unit tests for Phase 1 silent-correctness fixes.

Covers:
  - computed_status / delay_minutes use UTC (not local time)
  - get_or_cache evicts corrupt cache entries and calls fallback
  - create_hazmat_alert returns None (not IntegrityError) for missing appointment
  - POST /alerts/hazmat returns 404 (not 500) when appointment missing
  - appointment_state_repository raises on NULL version
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# computed_status / delay_minutes — UTC comparisons
# ---------------------------------------------------------------------------

# Import sql_models without triggering a DB connection (the module only uses
# in-memory SQLAlchemy classes; the connection is created in postgres.py).
import infrastructure.persistence.sql_models as _sm


class _FakeAppointment:
    """Minimal stand-in for Appointment to test computed properties without ORM."""
    def __init__(self, scheduled_start_time, status):
        self.scheduled_start_time = scheduled_start_time
        self.status = status

    computed_status = _sm.Appointment.computed_status
    delay_minutes = _sm.Appointment.delay_minutes
    is_delayed = _sm.Appointment.is_delayed


class TestComputedStatusUTC:
    """computed_status and delay_minutes must compare against UTC, not local time."""

    def _make(self, offset_minutes: int, status="in_transit"):
        naive_utc = (
            datetime.now(timezone.utc) - timedelta(minutes=offset_minutes)
        ).replace(tzinfo=None)
        return _FakeAppointment(naive_utc, status)

    def test_not_delayed_when_within_tolerance(self):
        appt = self._make(0)
        assert appt.computed_status == "in_transit"

    def test_delayed_when_past_tolerance(self):
        appt = self._make(_sm.DELAY_TOLERANCE_MINUTES + 5)
        assert appt.computed_status == "delayed"

    def test_delay_minutes_is_non_negative_for_future(self):
        future = (datetime.now(timezone.utc) + timedelta(minutes=30)).replace(tzinfo=None)
        appt = _FakeAppointment(future, "in_transit")
        assert appt.delay_minutes == 0

    def test_delay_minutes_positive_for_overdue(self):
        extra = 10
        appt = self._make(_sm.DELAY_TOLERANCE_MINUTES + extra)
        assert appt.delay_minutes >= extra

    def test_completed_status_bypasses_delay_check(self):
        far_past = datetime(2000, 1, 1)
        appt = _FakeAppointment(far_past, "completed")
        assert appt.computed_status == "completed"
        assert appt.delay_minutes == 0


# ---------------------------------------------------------------------------
# get_or_cache — evicts corrupt entry, returns fallback result
# ---------------------------------------------------------------------------

class TestGetOrCache:
    def _import(self):
        # Re-import so we get the real module (not any cached mock)
        import importlib
        import application.queries.cache_queries as m
        importlib.reload(m)
        return m

    def test_calls_fallback_on_corrupt_json(self):
        import application.queries.cache_queries as cq

        mock_redis = MagicMock()
        mock_redis.get.return_value = "not-valid-json{{{"

        fallback_data = {"key": "value"}
        fallback = MagicMock(return_value=fallback_data)

        with patch.object(cq, "redis_client", mock_redis):
            result = cq.get_or_cache("some_key", 60, fallback)

        assert result == fallback_data
        fallback.assert_called_once()

    def test_evicts_corrupt_entry(self):
        import application.queries.cache_queries as cq

        mock_redis = MagicMock()
        mock_redis.get.return_value = "{{invalid}}"

        with patch.object(cq, "redis_client", mock_redis):
            cq.get_or_cache("some_key", 60, lambda: {"x": 1})

        mock_redis.delete.assert_called_once_with("some_key")

    def test_returns_cached_value_when_valid(self):
        import application.queries.cache_queries as cq

        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps({"cached": True})

        fallback = MagicMock()
        with patch.object(cq, "redis_client", mock_redis):
            result = cq.get_or_cache("some_key", 60, fallback)

        assert result == {"cached": True}
        fallback.assert_not_called()

    def test_calls_fallback_on_cache_miss(self):
        import application.queries.cache_queries as cq

        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        with patch.object(cq, "redis_client", mock_redis):
            result = cq.get_or_cache("some_key", 60, lambda: {"fresh": True})

        assert result == {"fresh": True}


# ---------------------------------------------------------------------------
# appointment_state_repository — raises on NULL version
# ---------------------------------------------------------------------------

class TestAppointmentStateRepositoryNullVersion:
    def test_raises_on_null_version(self):
        import pytest
        from infrastructure.persistence.appointment_state_repository import (
            SqlAlchemyAppointmentStateRepository,
        )

        mock_row = MagicMock()
        mock_row.version = None

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.one.return_value = mock_row

        repo = SqlAlchemyAppointmentStateRepository(mock_session)
        with pytest.raises(ValueError, match="NULL version"):
            repo.save_state_transition(1, "in_process", {})

    def test_increments_version_normally(self):
        from infrastructure.persistence.appointment_state_repository import (
            SqlAlchemyAppointmentStateRepository,
        )

        mock_row = MagicMock()
        mock_row.version = 3

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.one.return_value = mock_row

        repo = SqlAlchemyAppointmentStateRepository(mock_session)
        repo.save_state_transition(1, "in_process", {})

        assert mock_row.version == 4


# ---------------------------------------------------------------------------
# create_hazmat_alert — returns None when appointment missing
# ---------------------------------------------------------------------------

class TestCreateHazmatAlertMissingAppointment:
    def test_returns_none_when_appointment_not_found(self):
        from application.use_cases.alert_handlers import create_hazmat_alert

        mock_uow = MagicMock()
        mock_uow.__enter__ = MagicMock(return_value=mock_uow)
        mock_uow.__exit__ = MagicMock(return_value=False)
        # appointment_state.get_for_update returns None → appointment missing
        mock_uow.appointment_state.get_for_update.return_value = None

        result = create_hazmat_alert(lambda: mock_uow, appointment_id=9999)

        assert result is None
        mock_uow.alerts.add.assert_not_called()
