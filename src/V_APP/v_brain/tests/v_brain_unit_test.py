"""
Unit tests for VBrain.
"""

import json
import threading
import time
from unittest.mock import MagicMock, patch, PropertyMock
import pytest

from V_APP.v_brain.config import VBrainConfig
from V_APP.v_brain.src.scale_correlator import ScaleCorrelator
from V_APP.v_brain.src.v_brain import VBrain
from shared.src.kafka_protocol import (
    KafkaTopicFactory,
    TruckDetectedMessage,
    LicensePlateResultsMessage,
    HazardPlateResultsMessage,
    DecisionResultsMessage,
    InfractionDecisionMessage,
    KafkaMessageProto,
)


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def config():
    return VBrainConfig(
        kafka_bootstrap="localhost:9092",
        gate_ids='["1"]',
        correlator_timeout_seconds=10,
    )


@pytest.fixture
def brain(config):
    b = VBrain(
        config=config,
        kafka_producer=MagicMock(),
        kafka_consumer=MagicMock(),
    )
    return b


# ═══════════════════════════════════════════════════════════════════
# VBrainConfig
# ═══════════════════════════════════════════════════════════════════

class TestVBrainConfig:
    def test_defaults(self):
        cfg = VBrainConfig()
        assert cfg.correlator_timeout_seconds == 30
        assert cfg.gate_id_list == ["1"]

    def test_custom_gates(self):
        cfg = VBrainConfig(gate_ids='["1","2","3"]')
        assert cfg.gate_id_list == ["1", "2", "3"]

    def test_invalid_json(self):
        with pytest.raises(Exception):
            VBrainConfig(gate_ids="not_valid")

    def test_empty_array(self):
        with pytest.raises(Exception):
            VBrainConfig(gate_ids="[]")


# ═══════════════════════════════════════════════════════════════════
# Init
# ═══════════════════════════════════════════════════════════════════

class TestVBrainInit:
    def test_running_false(self, brain):
        assert brain.running is False

    def test_topic_map_built(self, brain):
        expected_topics = [
            KafkaTopicFactory.truck_detected("1"),
            KafkaTopicFactory.license_plate_results("1"),
            KafkaTopicFactory.hazard_plate_results("1"),
            KafkaTopicFactory.agent_decision("1"),
            KafkaTopicFactory.infraction_decision("1"),
        ]
        for t in expected_topics:
            assert t in brain._topic_map

    def test_consume_topics(self, brain):
        assert len(brain.consume_topics) == 5

    def test_scale_status_initial(self, brain):
        assert brain.scale_status is False

    def test_correlator_created(self, brain):
        assert isinstance(brain.correlator, ScaleCorrelator)

    def test_stop(self, brain):
        brain.running = True
        brain.stop()
        assert brain.running is False


# ═══════════════════════════════════════════════════════════════════
# _handle_message routing
# ═══════════════════════════════════════════════════════════════════

class TestHandleMessage:
    def test_unknown_topic_ignored(self, brain):
        brain._handle_message("unknown-topic", MagicMock(), "t1")
        # Should not raise

    def test_routes_truck_detected(self, brain):
        topic = KafkaTopicFactory.truck_detected("1")
        with patch.object(brain, "_on_truck_detected") as mock:
            brain._handle_message(topic, MagicMock(), "t1")
            mock.assert_called_once_with("t1", "1")

    def test_routes_lp_results(self, brain):
        topic = KafkaTopicFactory.license_plate_results("1")
        with patch.object(brain, "_on_lp_results") as mock:
            brain._handle_message(topic, MagicMock(), "t1")
            mock.assert_called_once_with("t1", "1")

    def test_routes_hz_results(self, brain):
        topic = KafkaTopicFactory.hazard_plate_results("1")
        with patch.object(brain, "_on_hz_results") as mock:
            brain._handle_message(topic, MagicMock(), "t1")
            mock.assert_called_once_with("t1", "1")

    def test_routes_agent_decision(self, brain):
        topic = KafkaTopicFactory.agent_decision("1")
        with patch.object(brain, "_on_agent_decision") as mock:
            brain._handle_message(topic, MagicMock(), "t1")
            mock.assert_called_once_with("t1", "1")

    def test_routes_infraction_decision(self, brain):
        topic = KafkaTopicFactory.infraction_decision("1")
        with patch.object(brain, "_on_infraction_decision") as mock:
            brain._handle_message(topic, MagicMock(), "t1")
            mock.assert_called_once_with("t1", "1")


# ═══════════════════════════════════════════════════════════════════
# _on_truck_detected
# ═══════════════════════════════════════════════════════════════════

class TestOnTruckDetected:
    def test_registers_truck(self, brain):
        brain._on_truck_detected("t1", "1")
        assert brain.correlator.is_tracked("t1")

    def test_publishes_scale_up(self, brain):
        brain._on_truck_detected("t1", "1")
        brain.kafka_producer.produce.assert_called()
        call_kwargs = brain.kafka_producer.produce.call_args.kwargs
        assert call_kwargs["topic"] == KafkaTopicFactory.scale_up()

    def test_ignores_none_truck_id(self, brain):
        brain._on_truck_detected(None, "1")
        assert brain.correlator.active_trucks == 0

    def test_sets_scale_status_up(self, brain):
        brain._on_truck_detected("t1", "1")
        assert brain.scale_status is True


# ═══════════════════════════════════════════════════════════════════
# _on_lp_results / _on_hz_results
# ═══════════════════════════════════════════════════════════════════

class TestOnLpResults:
    def test_marks_lp_done(self, brain):
        brain.correlator.truck_detected("t1", "1")
        brain._on_lp_results("t1", "1")
        assert brain.correlator.get_state("t1")["lp"] is True

    def test_ignores_none_truck_id(self, brain):
        brain._on_lp_results(None, "1")  # Should not raise

    def test_scales_down_when_both_complete(self, brain):
        brain.correlator.truck_detected("t1", "1")
        brain.correlator.hz_received("t1")
        with patch.object(brain, "_scale_down_try") as mock:
            brain._on_lp_results("t1", "1")
            mock.assert_called_once()


class TestOnHzResults:
    def test_marks_hz_done(self, brain):
        brain.correlator.truck_detected("t1", "1")
        brain._on_hz_results("t1", "1")
        assert brain.correlator.get_state("t1")["hz"] is True

    def test_ignores_none_truck_id(self, brain):
        brain._on_hz_results(None, "1")

    def test_scales_down_when_both_complete(self, brain):
        brain.correlator.truck_detected("t1", "1")
        brain.correlator.lp_received("t1")
        with patch.object(brain, "_scale_down_try") as mock:
            brain._on_hz_results("t1", "1")
            mock.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# _on_agent_decision / _on_infraction_decision
# ═══════════════════════════════════════════════════════════════════

class TestOnAgentDecision:
    def test_tracked_truck_resets_and_removes(self, brain):
        brain.correlator.truck_detected("t1", "1")
        with patch.object(brain, "_reset_agent_a") as mock_reset:
            brain._on_agent_decision("t1", "1")
            mock_reset.assert_called_once_with("1", reason="agent_decision")
        assert not brain.correlator.is_tracked("t1")

    def test_untracked_truck_logs_warning(self, brain):
        brain._on_agent_decision("unknown", "1")  # Should not raise

    def test_ignores_none_truck_id(self, brain):
        brain._on_agent_decision(None, "1")


class TestOnInfractionDecision:
    def test_tracked_truck_resets_and_removes(self, brain):
        brain.correlator.truck_detected("t1", "1")
        with patch.object(brain, "_reset_agent_a") as mock_reset:
            brain._on_infraction_decision("t1", "1")
            mock_reset.assert_called_once_with("1", reason="infraction_decision")
        assert not brain.correlator.is_tracked("t1")

    def test_untracked_truck_logs_warning(self, brain):
        brain._on_infraction_decision("unknown", "1")

    def test_ignores_none_truck_id(self, brain):
        brain._on_infraction_decision(None, "1")


# ═══════════════════════════════════════════════════════════════════
# Scale actions
# ═══════════════════════════════════════════════════════════════════

class TestScaleUpTry:
    def test_publishes_scale_up_message(self, brain):
        brain._scale_up_try("t1", "1", reason="test")
        brain.kafka_producer.produce.assert_called_once()
        call_kwargs = brain.kafka_producer.produce.call_args.kwargs
        assert call_kwargs["topic"] == KafkaTopicFactory.scale_up()

    def test_sets_scale_status_true(self, brain):
        brain.scale_status = False
        brain._scale_up_try("t1", "1")
        assert brain.scale_status is True

    def test_no_op_when_already_scaled_up(self, brain):
        brain.scale_status = True
        brain._scale_up_try("t1", "1")
        # Still produces the message (for frontend), but scale_status stays True
        assert brain.scale_status is True


class TestScaleDownTry:
    def test_publishes_scale_down_message(self, brain):
        brain._scale_down_try("t1", "1", reason="test")
        brain.kafka_producer.produce.assert_called_once()
        call_kwargs = brain.kafka_producer.produce.call_args.kwargs
        assert call_kwargs["topic"] == KafkaTopicFactory.scale_down()

    def test_sets_scale_status_false_when_no_pending(self, brain):
        brain.scale_status = True
        brain._scale_down_try("t1", "1")
        assert brain.scale_status is False

    def test_skips_scale_down_if_truck_still_pending(self, brain):
        brain.scale_status = True
        brain.correlator.truck_detected("t2", "1")  # undecided truck
        brain._scale_down_try("t1", "1")
        assert brain.scale_status is True  # not changed


# ═══════════════════════════════════════════════════════════════════
# _reset_agent_a
# ═══════════════════════════════════════════════════════════════════

class TestResetAgentA:
    def test_publishes_reset_message(self, brain):
        with patch("V_APP.v_brain.src.v_brain.time.sleep"):
            brain._reset_agent_a("1", reason="agent_decision")
            # Wait for the background thread to finish
            for t in threading.enumerate():
                if t.daemon and t != threading.current_thread():
                    t.join(timeout=5)
        brain.kafka_producer.produce.assert_called_once()
        call_kwargs = brain.kafka_producer.produce.call_args.kwargs
        assert call_kwargs["topic"] == KafkaTopicFactory.reset_agent_a("1")


# ═══════════════════════════════════════════════════════════════════
# _timeout_loop
# ═══════════════════════════════════════════════════════════════════

class TestTimeoutLoop:
    def test_handles_timed_out_trucks(self, brain):
        brain.correlator.truck_detected("t1", "1")
        brain.correlator._state["t1"]["ts"] = time.time() - 20

        # Make the loop run once then stop
        original_sleep = time.sleep
        call_count = 0

        def fake_sleep(duration):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                brain.running = False

        brain.running = True
        with patch("time.sleep", side_effect=fake_sleep):
            with patch.object(brain, "_reset_agent_a") as mock_reset:
                with patch.object(brain, "_scale_down_try") as mock_scale_down:
                    brain._timeout_loop()
                    mock_reset.assert_called_once_with("1", reason="timeout")

        assert not brain.correlator.is_tracked("t1")

    def test_handles_no_gate_id(self, brain):
        brain.correlator.truck_detected("t1", "1")
        brain.correlator._state["t1"]["ts"] = time.time() - 20
        # Remove gate_id to trigger the else branch
        brain.correlator._state["t1"]["gate_id"] = None

        call_count = 0
        def fake_sleep(duration):
            nonlocal call_count
            call_count += 1
            brain.running = False

        brain.running = True
        with patch("time.sleep", side_effect=fake_sleep):
            # Patch get_gate_id to return None
            with patch.object(brain.correlator, "get_gate_id", return_value=None):
                brain._timeout_loop()

        assert not brain.correlator.is_tracked("t1")


# ═══════════════════════════════════════════════════════════════════
# _get_scale_status
# ═══════════════════════════════════════════════════════════════════

class TestGetScaleStatus:
    def test_returns_scale_status(self, brain):
        brain.scale_status = False
        assert brain._get_scale_status("1") is False
        brain.scale_status = True
        assert brain._get_scale_status("1") is True
