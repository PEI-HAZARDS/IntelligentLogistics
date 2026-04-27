"""
Unit tests for VBrain.
"""

import json
import threading
import time
from unittest.mock import MagicMock, patch, PropertyMock
import pytest
import requests

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
        brain._scale_up_try("1", reason="test")
        brain.kafka_producer.produce.assert_called_once()
        call_kwargs = brain.kafka_producer.produce.call_args.kwargs
        assert call_kwargs["topic"] == KafkaTopicFactory.scale_up()

    def test_sets_scale_status_true(self, brain):
        brain.scale_status = False
        brain._scale_up_try("1")
        assert brain.scale_status is True

    def test_no_op_when_already_scaled_up(self, brain):
        brain.scale_status = True
        brain._scale_up_try("1")
        # Still produces the message (for frontend), but scale_status stays True
        assert brain.scale_status is True


class TestScaleDownTry:
    def test_publishes_scale_down_message(self, brain):
        brain._scale_down_try("1", reason="test")
        brain.kafka_producer.produce.assert_called_once()
        call_kwargs = brain.kafka_producer.produce.call_args.kwargs
        assert call_kwargs["topic"] == KafkaTopicFactory.scale_down()

    def test_sets_scale_status_false_when_no_pending(self, brain):
        brain.scale_status = True
        brain._scale_down_try("1")
        assert brain.scale_status is False

    def test_skips_scale_down_if_truck_still_pending(self, brain):
        brain.scale_status = True
        brain.correlator.truck_detected("t2", "1")  # undecided truck
        brain._scale_down_try("1")
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
        assert brain._get_scale_status() is False
        brain.scale_status = True
        assert brain._get_scale_status() is True


# ═══════════════════════════════════════════════════════════════════
# _call_scaling_api
# ═══════════════════════════════════════════════════════════════════

class TestCallScalingApi:
    def test_posts_payload_to_configured_endpoint(self, brain, _stub_scaling_http):
        brain._call_scaling_api("SCALE_UP", "1")
        _stub_scaling_http.assert_called_once()
        url = _stub_scaling_http.call_args.args[0]
        payload = _stub_scaling_http.call_args.kwargs["json"]
        assert url == f"{brain.config.scaling_api_url}/napp/v1/scaling-operation/slice"
        assert payload["action"] == "SCALE_UP"
        assert payload["sliceId"] == brain.config.scaling_slice_id
        assert payload["requestId"] == brain.config.scaling_request_id
        assert payload["notificationDestination"] == brain.config.scaling_notification_destination

    def test_accepts_202_as_success(self, brain, _stub_scaling_http):
        _stub_scaling_http.return_value.status_code = 202
        brain._call_scaling_api("SCALE_DOWN", "1")  # Should not raise

    def test_logs_error_on_non_2xx_status(self, brain, _stub_scaling_http, caplog):
        _stub_scaling_http.return_value.status_code = 500
        _stub_scaling_http.return_value.text = "boom"
        with caplog.at_level("ERROR", logger="VBrain"):
            brain._call_scaling_api("SCALE_UP", "1")  # Should not raise
        assert any("Scaling API SCALE_UP failed" in record.message for record in caplog.records)

    def test_swallows_request_exception(self, brain, _stub_scaling_http, caplog):
        _stub_scaling_http.side_effect = requests.ConnectionError("connection refused")
        with caplog.at_level("ERROR", logger="VBrain"):
            brain._call_scaling_api("SCALE_UP", "1")  # Should not raise
        assert any("request failed" in record.message for record in caplog.records)


# ═══════════════════════════════════════════════════════════════════
# start() — main consumer loop
# ═══════════════════════════════════════════════════════════════════

class TestStart:
    """The `start()` loop is the only place that touches the Prometheus HTTP
    server, the timeout thread, and the Kafka deserialization pipeline. We
    drive a single iteration end-to-end with mocked Kafka wrappers."""

    def _build_kafka_msg(self, topic: str, value: bytes, headers=None):
        msg = MagicMock()
        msg.topic.return_value = topic
        msg.value.return_value = value
        msg.headers.return_value = headers or []
        return msg

    def test_routes_a_truck_detected_message(self, brain):
        topic = KafkaTopicFactory.truck_detected("1")
        kafka_msg = self._build_kafka_msg(
            topic,
            json.dumps({"message_type": "truck_detected", "confidence": 0.9, "num_detections": 1}).encode(),
        )

        # consume_message returns one valid message, then None to end the loop.
        calls = iter([kafka_msg, None])

        def consume(timeout):
            value = next(calls)
            if value is None:
                brain.running = False
            return value

        brain.kafka_consumer.consume_message.side_effect = consume
        brain.kafka_consumer.extract_truck_id_from_headers.return_value = "t1"

        with patch("V_APP.v_brain.src.v_brain.start_http_server"):
            with patch.object(brain, "_handle_message") as handle:
                with patch.object(brain, "_timeout_loop"):  # keep the worker thread cheap
                    brain.start()

        handle.assert_called_once()
        assert handle.call_args.args[0] == topic
        assert handle.call_args.args[2] == "t1"
        brain.kafka_consumer.clear_stale_messages.assert_called_once()
        brain.kafka_consumer.close.assert_called_once()
        brain.kafka_producer.close.assert_called_once()
        assert brain.running is False

    def test_skips_when_consumer_returns_none(self, brain):
        calls = iter([None, None])

        def consume(timeout):
            value = next(calls, None)
            brain.running = False
            return value

        brain.kafka_consumer.consume_message.side_effect = consume

        with patch("V_APP.v_brain.src.v_brain.start_http_server"):
            with patch.object(brain, "_handle_message") as handle:
                with patch.object(brain, "_timeout_loop"):
                    brain.start()

        handle.assert_not_called()

    def test_skips_invalid_json_payloads(self, brain):
        kafka_msg = self._build_kafka_msg(
            KafkaTopicFactory.truck_detected("1"), b"not-json"
        )
        calls = iter([kafka_msg, None])

        def consume(timeout):
            value = next(calls)
            if value is None:
                brain.running = False
            return value

        brain.kafka_consumer.consume_message.side_effect = consume
        brain.kafka_consumer.extract_truck_id_from_headers.return_value = "t1"

        with patch("V_APP.v_brain.src.v_brain.start_http_server"):
            with patch.object(brain, "_handle_message") as handle:
                with patch.object(brain, "_timeout_loop"):
                    brain.start()

        handle.assert_not_called()

    def test_skips_unknown_message_type(self, brain):
        kafka_msg = self._build_kafka_msg(
            KafkaTopicFactory.truck_detected("1"),
            json.dumps({"message_type": "bogus"}).encode(),
        )
        calls = iter([kafka_msg, None])

        def consume(timeout):
            value = next(calls)
            if value is None:
                brain.running = False
            return value

        brain.kafka_consumer.consume_message.side_effect = consume
        brain.kafka_consumer.extract_truck_id_from_headers.return_value = "t1"

        with patch("V_APP.v_brain.src.v_brain.start_http_server"):
            with patch.object(brain, "_handle_message") as handle:
                with patch.object(brain, "_timeout_loop"):
                    brain.start()

        handle.assert_not_called()

    def test_handles_keyboard_interrupt(self, brain):
        brain.kafka_consumer.consume_message.side_effect = KeyboardInterrupt()

        with patch("V_APP.v_brain.src.v_brain.start_http_server"):
            with patch.object(brain, "_timeout_loop"):
                brain.start()  # Should not propagate

        assert brain.running is False
        brain.kafka_consumer.close.assert_called_once()

    def test_unhandled_exception_is_caught_and_resources_closed(self, brain):
        brain.kafka_consumer.consume_message.side_effect = RuntimeError("kafka down")

        with patch("V_APP.v_brain.src.v_brain.start_http_server"):
            with patch.object(brain, "_timeout_loop"):
                brain.start()  # Should not propagate

        brain.kafka_consumer.close.assert_called_once()
        brain.kafka_producer.close.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# __main__ entrypoint
# ═══════════════════════════════════════════════════════════════════

class TestMainEntrypoint:
    def test_main_builds_brain_and_starts(self):
        from V_APP.v_brain import __main__ as main_module

        with patch.object(main_module, "VBrain") as VBrainCls:
            instance = VBrainCls.return_value
            main_module.main()

        VBrainCls.assert_called_once()
        instance.start.assert_called_once()
