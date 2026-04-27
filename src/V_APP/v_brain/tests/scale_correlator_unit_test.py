"""
Unit tests for ScaleCorrelator.
"""

import time
import pytest
from V_APP.v_brain.src.scale_correlator import ScaleCorrelator


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def correlator():
    return ScaleCorrelator(timeout_seconds=10)


# ═══════════════════════════════════════════════════════════════════
# Registration
# ═══════════════════════════════════════════════════════════════════

class TestTruckDetected:
    def test_registers_new_truck(self, correlator):
        correlator.truck_detected("t1", "gate-1")
        assert correlator.is_tracked("t1")
        assert correlator.active_trucks == 1

    def test_initial_state(self, correlator):
        correlator.truck_detected("t1", "gate-1")
        state = correlator.get_state("t1")
        assert state["gate_id"] == "gate-1"
        assert state["lp"] is False
        assert state["hz"] is False
        assert state["decided"] is False

    def test_overwrites_existing(self, correlator):
        correlator.truck_detected("t1", "gate-1")
        correlator.truck_detected("t1", "gate-2")
        assert correlator.get_gate_id("t1") == "gate-2"

    def test_multiple_trucks(self, correlator):
        correlator.truck_detected("t1", "1")
        correlator.truck_detected("t2", "2")
        assert correlator.active_trucks == 2


# ═══════════════════════════════════════════════════════════════════
# Tracking
# ═══════════════════════════════════════════════════════════════════

class TestTracking:
    def test_is_tracked_false_for_unknown(self, correlator):
        assert correlator.is_tracked("unknown") is False

    def test_get_gate_id_returns_none_for_unknown(self, correlator):
        assert correlator.get_gate_id("unknown") is None

    def test_get_gate_id(self, correlator):
        correlator.truck_detected("t1", "gate-5")
        assert correlator.get_gate_id("t1") == "gate-5"

    def test_get_state_none_for_unknown(self, correlator):
        assert correlator.get_state("unknown") is None


# ═══════════════════════════════════════════════════════════════════
# LP / HZ received
# ═══════════════════════════════════════════════════════════════════

class TestLpReceived:
    def test_marks_lp(self, correlator):
        correlator.truck_detected("t1", "1")
        result = correlator.lp_received("t1")
        assert result is False  # HZ not yet
        assert correlator.get_state("t1")["lp"] is True

    def test_returns_true_when_both_complete(self, correlator):
        correlator.truck_detected("t1", "1")
        correlator.hz_received("t1")
        result = correlator.lp_received("t1")
        assert result is True

    def test_ignores_unknown_truck(self, correlator):
        assert correlator.lp_received("unknown") is False


class TestHzReceived:
    def test_marks_hz(self, correlator):
        correlator.truck_detected("t1", "1")
        result = correlator.hz_received("t1")
        assert result is False
        assert correlator.get_state("t1")["hz"] is True

    def test_returns_true_when_both_complete(self, correlator):
        correlator.truck_detected("t1", "1")
        correlator.lp_received("t1")
        result = correlator.hz_received("t1")
        assert result is True

    def test_ignores_unknown_truck(self, correlator):
        assert correlator.hz_received("unknown") is False


# ═══════════════════════════════════════════════════════════════════
# Decision received
# ═══════════════════════════════════════════════════════════════════

class TestDecisionReceived:
    def test_marks_decided(self, correlator):
        correlator.truck_detected("t1", "1")
        result = correlator.decision_received("t1")
        assert result is True
        assert correlator.get_state("t1")["decided"] is True

    def test_ignores_unknown_truck(self, correlator):
        assert correlator.decision_received("unknown") is False


# ═══════════════════════════════════════════════════════════════════
# Timeouts
# ═══════════════════════════════════════════════════════════════════

class TestCheckTimeouts:
    def test_no_timeouts_when_fresh(self, correlator):
        correlator.truck_detected("t1", "1")
        assert correlator.check_timeouts() == []

    def test_detects_timed_out(self, correlator):
        correlator.truck_detected("t1", "1")
        correlator._state["t1"]["ts"] = time.time() - 20  # expired
        timed_out = correlator.check_timeouts()
        assert "t1" in timed_out

    def test_mixed_fresh_and_stale(self, correlator):
        correlator.truck_detected("t1", "1")
        correlator.truck_detected("t2", "2")
        correlator._state["t1"]["ts"] = time.time() - 20
        timed_out = correlator.check_timeouts()
        assert "t1" in timed_out
        assert "t2" not in timed_out


# ═══════════════════════════════════════════════════════════════════
# Remove
# ═══════════════════════════════════════════════════════════════════

class TestRemove:
    def test_removes_tracked_truck(self, correlator):
        correlator.truck_detected("t1", "1")
        correlator.remove("t1")
        assert correlator.is_tracked("t1") is False
        assert correlator.active_trucks == 0

    def test_remove_unknown_does_not_raise(self, correlator):
        correlator.remove("nonexistent")  # Should not raise


# ═══════════════════════════════════════════════════════════════════
# Active trucks
# ═══════════════════════════════════════════════════════════════════

class TestActiveTrucks:
    def test_empty(self, correlator):
        assert correlator.active_trucks == 0

    def test_count(self, correlator):
        correlator.truck_detected("t1", "1")
        correlator.truck_detected("t2", "2")
        correlator.truck_detected("t3", "3")
        assert correlator.active_trucks == 3
        correlator.remove("t2")
        assert correlator.active_trucks == 2


# ═══════════════════════════════════════════════════════════════════
# _is_results_complete
# ═══════════════════════════════════════════════════════════════════

class TestIsResultsComplete:
    def test_returns_false_for_unknown_truck(self, correlator):
        assert correlator._is_results_complete("unknown") is False

    def test_returns_false_when_only_lp_received(self, correlator):
        correlator.truck_detected("t1", "1")
        correlator.lp_received("t1")
        assert correlator._is_results_complete("t1") is False

    def test_returns_true_when_lp_and_hz_received(self, correlator):
        correlator.truck_detected("t1", "1")
        correlator.lp_received("t1")
        correlator.hz_received("t1")
        assert correlator._is_results_complete("t1") is True
