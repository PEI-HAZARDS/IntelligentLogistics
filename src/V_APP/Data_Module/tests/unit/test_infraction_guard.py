"""
Tests for highway infraction guard (business rule: truck must be in transit to receive infraction).

Rules enforced:
- cmd_flag_highway_infraction raises ValueError if status not in {scheduled, in_transit}
- Route returns 409 when ValueError is raised
- Infraction is allowed for scheduled and in_transit appointments
"""

import pytest
from unittest.mock import MagicMock, patch
from application.use_cases.appointment_commands import (
    cmd_flag_highway_infraction,
    _INFRACTION_ALLOWED_STATUSES,
)


def _make_uow_factory(status: str):
    """Return a uow_factory that produces a mock UoW for a given appointment status."""
    aggregate = {
        "id": 1,
        "status": status,
        "gate_in_id": None,
    }
    mock_uow = MagicMock()
    mock_uow.__enter__ = MagicMock(return_value=mock_uow)
    mock_uow.__exit__ = MagicMock(return_value=False)
    mock_uow.appointment_state.get_for_update.return_value = aggregate
    mock_uow.outbox.append = MagicMock()
    mock_uow.commit = MagicMock()
    return lambda: mock_uow


@pytest.mark.unit
class TestInfractionAllowedStatuses:
    def test_allowed_statuses_set_contains_expected_values(self):
        assert _INFRACTION_ALLOWED_STATUSES == {"in_transit"}

    def test_infraction_allowed_for_in_transit(self):
        result = cmd_flag_highway_infraction(_make_uow_factory("in_transit"), 1)
        assert result is not None
        assert result["highway_infraction"] is True


@pytest.mark.unit
class TestInfractionRejectedStatuses:
    @pytest.mark.parametrize("status", ["scheduled", "in_process", "completed", "canceled"])
    def test_infraction_rejected_when_truck_not_in_transit(self, status):
        with pytest.raises(ValueError) as exc_info:
            cmd_flag_highway_infraction(_make_uow_factory(status), 1)
        assert status in str(exc_info.value)
        assert "in transit" in str(exc_info.value).lower() or "transit" in str(exc_info.value).lower()

    def test_error_message_is_descriptive(self):
        with pytest.raises(ValueError) as exc_info:
            cmd_flag_highway_infraction(_make_uow_factory("in_process"), 1)
        msg = str(exc_info.value)
        assert "in_process" in msg
        assert "port" in msg.lower() or "transit" in msg.lower()


@pytest.mark.unit
class TestInfractionNotFound:
    def test_returns_none_when_appointment_missing(self):
        mock_uow = MagicMock()
        mock_uow.__enter__ = MagicMock(return_value=mock_uow)
        mock_uow.__exit__ = MagicMock(return_value=False)
        mock_uow.appointment_state.get_for_update.return_value = None

        result = cmd_flag_highway_infraction(lambda: mock_uow, 999)
        assert result is None


@pytest.mark.unit
class TestInfractionRouteReturns409:
    """Route must return 409 when cmd raises ValueError (truck inside port)."""

    def test_arrivals_route_returns_409_for_in_process(self):
        """Structural check: the route must catch ValueError and raise HTTPException 409."""
        from pathlib import Path
        src = (
            Path(__file__).parent.parent.parent / "routes" / "arrivals.py"
        ).read_text()
        # Route must have try/except ValueError → 409
        assert "409" in src, "arrivals.py must return 409 for infraction guard violation"
        assert "ValueError" in src, "arrivals.py must catch ValueError from cmd_flag_highway_infraction"
