"""
Unit tests for APIGateway and APIGatewayConfig.
"""

import sys
import json
from unittest.mock import MagicMock, patch, AsyncMock
import pytest

# ─── Mock heavy external dependencies before importing ──────────

# Prometheus
prometheus_mock = MagicMock()
sys.modules.setdefault("prometheus_client", prometheus_mock)
sys.modules.setdefault("prometheus_fastapi_instrumentator", MagicMock())

# OpenTelemetry
for otel_mod in [
    "opentelemetry",
    "opentelemetry.trace",
    "opentelemetry.sdk",
    "opentelemetry.sdk.trace",
    "opentelemetry.sdk.trace.export",
    "opentelemetry.exporter",
    "opentelemetry.exporter.otlp",
    "opentelemetry.exporter.otlp.proto",
    "opentelemetry.exporter.otlp.proto.grpc",
    "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
    "opentelemetry.instrumentation",
    "opentelemetry.instrumentation.fastapi",
    "opentelemetry.sdk.resources",
]:
    sys.modules.setdefault(otel_mod, MagicMock())

# Mock router modules (they import DB/service dependencies)
for router_mod in [
    "routers",
    "routers.arrivals",
    "routers.manual_review",
    "routers.alerts",
    "routers.drivers",
    "routers.stream",
    "routers.realtime",
    "routers.workers",
    "routers.statistics",
]:
    m = MagicMock()
    m.router = MagicMock()
    sys.modules.setdefault(router_mod, m)

# Mock web_socket_manager
ws_mock_mod = MagicMock()
sys.modules.setdefault("web_socket_manager", ws_mock_mod)

from V_APP.api_gateway.src.api_gateway import APIGateway, APIGatewayConfig
from shared.src.kafka_protocol import KafkaTopicFactory


# ═══════════════════════════════════════════════════════════════════
# APIGatewayConfig
# ═══════════════════════════════════════════════════════════════════

class TestAPIGatewayConfig:
    def test_defaults(self):
        cfg = APIGatewayConfig()
        assert cfg.gateway_port == 8000
        assert cfg.gate_id_list == ["1"]

    def test_custom_gates(self):
        cfg = APIGatewayConfig(gate_ids='["2","3"]')
        assert cfg.gate_id_list == ["2", "3"]

    def test_decision_gate_ids(self):
        cfg = APIGatewayConfig(decision_gate_ids='["4"]')
        assert cfg.decision_gate_id_list == ["4"]

    def test_infraction_gate_ids(self):
        cfg = APIGatewayConfig(infraction_gate_ids='["5","6"]')
        assert cfg.infraction_gate_id_list == ["5", "6"]

    def test_invalid_json(self):
        with pytest.raises(Exception):
            APIGatewayConfig(gate_ids="invalid")

    def test_empty_array(self):
        with pytest.raises(Exception):
            APIGatewayConfig(gate_ids="[]")


# ═══════════════════════════════════════════════════════════════════
# APIGateway Init
# ═══════════════════════════════════════════════════════════════════

class TestAPIGatewayInit:
    @pytest.fixture
    def config(self):
        return APIGatewayConfig(
            kafka_bootstrap="localhost:9092",
            gate_ids='["1"]',
            decision_gate_ids='["1"]',
            infraction_gate_ids='["1"]',
        )

    @pytest.fixture
    def gateway(self, config):
        return APIGateway(
            config=config,
            kafka_producer=MagicMock(),
            kafka_consumer=MagicMock(),
            WSManager=MagicMock(),
        )

    def test_running_false(self, gateway):
        assert gateway.running is False

    def test_consume_topics_include_scale(self, gateway):
        assert KafkaTopicFactory.scale_up() in gateway.consume_topics
        assert KafkaTopicFactory.scale_down() in gateway.consume_topics

    def test_consume_topics_include_infraction_decision(self, gateway):
        assert KafkaTopicFactory.infraction_decision("1") in gateway.consume_topics

    def test_consume_topics_include_agent_decision(self, gateway):
        assert KafkaTopicFactory.agent_decision("1") in gateway.consume_topics

    def test_app_created(self, gateway):
        assert gateway.app is not None

    def test_stop(self, gateway):
        gateway.running = True
        gateway._consumer_thread = MagicMock()
        gateway._consumer_thread.is_alive.return_value = False
        gateway.stop()
        assert gateway.running is False
        gateway.kafka_consumer.close.assert_called_once()
        gateway.kafka_producer.flush.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# _consumer_loop
# ═══════════════════════════════════════════════════════════════════

class TestConsumerLoop:
    @pytest.fixture
    def config(self):
        return APIGatewayConfig(
            kafka_bootstrap="localhost:9092",
            gate_ids='["1"]',
            decision_gate_ids='["1"]',
            infraction_gate_ids='["1"]',
        )

    @pytest.fixture
    def gateway(self, config):
        gw = APIGateway(
            config=config,
            kafka_producer=MagicMock(),
            kafka_consumer=MagicMock(),
            WSManager=MagicMock(),
        )
        return gw

    def test_none_message_continues(self, gateway):
        call_count = 0
        def consume_then_stop(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                gateway.running = False
            return None

        gateway.kafka_consumer.consume_message.side_effect = consume_then_stop
        gateway.kafka_consumer.clear_stale_messages = MagicMock()
        gateway.running = True
        gateway._consumer_loop()
        assert call_count >= 1

    def test_skipped_decision_filtered(self, gateway):
        msg = MagicMock()
        msg.topic.return_value = "agent-decision-1"

        # Build data that will produce a SKIPPED decision
        decision_data = {
            "message_type": "decision_results",
            "decision": "SKIPPED",
            "license_plate": "AB12CD",
            "license_crop_url": "u",
            "un": "1",
            "kemler": "2",
            "hazard_crop_url": "u2",
            "alerts": [],
            "route": "A",
            "decision_reason": "skip",
            "decision_source": "agent",
        }

        call_count = 0
        def consume_then_stop(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return msg
            gateway.running = False
            return None

        gateway.kafka_consumer.consume_message.side_effect = consume_then_stop
        gateway.kafka_consumer.clear_stale_messages = MagicMock()
        gateway.kafka_consumer.parse_message.return_value = ("agent-decision-1", decision_data, "t1")
        gateway.running = True

        # Mock deserialize to return a message that to_dict gives SKIPPED
        mock_typed_msg = MagicMock()
        mock_typed_msg.to_dict.return_value = decision_data
        with patch("V_APP.api_gateway.src.api_gateway.deserialize_message", return_value=mock_typed_msg):
            gateway._consumer_loop()

        # broadcast should NOT have been called for SKIPPED
        gateway.ws_manager.broadcast_to_gate.assert_not_called()
