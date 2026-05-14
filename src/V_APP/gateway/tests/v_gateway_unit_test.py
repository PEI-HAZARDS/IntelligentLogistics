"""
Unit tests for VGateway.
"""

from unittest.mock import MagicMock
import pytest

from shared.src.base_gateway import BaseGatewayConfig
from shared.src.kafka_protocol import KafkaTopicFactory
from V_APP.gateway.src.v_gateway import VGateway


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def config():
    return BaseGatewayConfig(
        kafka_bootstrap="localhost:9092",
        gate_ids=["1"],
        receivers=["http://ai-gateway:8000"],
    )


@pytest.fixture
def gateway(config):
    return VGateway(
        config=config,
        kafka_producer=MagicMock(),
        kafka_consumer=MagicMock(),
    )


# ═══════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════

class TestVGatewayInit:
    def test_gateway_name(self, gateway):
        assert gateway.get_gateway_name() == "V_Gateway"

    def test_receivers(self, gateway):
        assert gateway.get_receivers() == ["http://ai-gateway:8000"]


class TestGetTopicsConsume:
    def test_single_gate(self, gateway):
        topics = gateway.get_topics_consume()
        assert KafkaTopicFactory.reset_agent_a("1") in topics
        assert len(topics) == 1

    def test_multiple_gates(self):
        config = BaseGatewayConfig(
            kafka_bootstrap="localhost:9092",
            gate_ids=["1", "2", "3"],
            receivers=["http://ai-gateway:8000"],
        )
        gw = VGateway(config=config, kafka_producer=MagicMock(), kafka_consumer=MagicMock())
        topics = gw.get_topics_consume()
        assert len(topics) == 3
        for gid in ["1", "2", "3"]:
            assert KafkaTopicFactory.reset_agent_a(gid) in topics


class TestGetTopicsProduce:
    def test_single_gate(self, gateway):
        topics = gateway.get_topics_produce()
        assert KafkaTopicFactory.truck_detected("1") in topics
        assert KafkaTopicFactory.license_plate_results("1") in topics
        assert KafkaTopicFactory.hazard_plate_results("1") in topics
        assert len(topics) == 3

    def test_multi_gate(self):
        config = BaseGatewayConfig(
            kafka_bootstrap="localhost:9092",
            gate_ids=["1", "2"],
            receivers=["http://ai-gateway:8000"],
        )
        gw = VGateway(config=config, kafka_producer=MagicMock(), kafka_consumer=MagicMock())
        topics = gw.get_topics_produce()
        assert len(topics) == 6  # 3 per gate


class TestProcessMessage:
    def test_returns_message_unchanged(self, gateway):
        msg = MagicMock()
        msg.MESSAGE_TYPE = "test"
        result = gateway.process_message(msg)
        assert result is msg
