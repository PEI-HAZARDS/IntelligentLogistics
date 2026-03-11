"""
Unit tests for AIGateway.
"""

from unittest.mock import MagicMock
import pytest

from shared.src.base_gateway import BaseGatewayConfig
from shared.src.kafka_protocol import KafkaTopicFactory
from AI_APP.gateway.src.ai_gateway import AIGateway


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def config():
    return BaseGatewayConfig(
        kafka_bootstrap="localhost:9092",
        gate_ids=["1"],
        receivers=["http://v-gateway:8000"],
    )


@pytest.fixture
def gateway(config):
    return AIGateway(
        config=config,
        kafka_producer=MagicMock(),
        kafka_consumer=MagicMock(),
    )


# ═══════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════

class TestAIGatewayInit:
    def test_gateway_name(self, gateway):
        assert gateway.get_gateway_name() == "AI_Gateway"

    def test_receivers(self, gateway):
        assert gateway.get_receivers() == ["http://v-gateway:8000"]


class TestGetTopicsConsume:
    def test_single_gate(self, gateway):
        topics = gateway.get_topics_consume()
        assert KafkaTopicFactory.truck_detected("1") in topics
        assert KafkaTopicFactory.license_plate_results("1") in topics
        assert KafkaTopicFactory.hazard_plate_results("1") in topics

    def test_multiple_gates(self):
        config = BaseGatewayConfig(
            kafka_bootstrap="localhost:9092",
            gate_ids=["1", "2"],
            receivers=["http://v-gateway:8000"],
        )
        gw = AIGateway(config=config, kafka_producer=MagicMock(), kafka_consumer=MagicMock())
        topics = gw.get_topics_consume()
        assert KafkaTopicFactory.truck_detected("1") in topics
        assert KafkaTopicFactory.truck_detected("2") in topics
        assert len(topics) == 6  # 3 per gate


class TestGetTopicsProduce:
    def test_single_gate(self, gateway):
        topics = gateway.get_topics_produce()
        reset_topic = KafkaTopicFactory.reset_agent_a("1")
        assert reset_topic in topics
        # Also has fallback by message_type
        assert "reset_agent_a" in topics

    def test_multi_gate_no_fallback(self):
        config = BaseGatewayConfig(
            kafka_bootstrap="localhost:9092",
            gate_ids=["1", "2"],
            receivers=["http://v-gateway:8000"],
        )
        gw = AIGateway(config=config, kafka_producer=MagicMock(), kafka_consumer=MagicMock())
        topics = gw.get_topics_produce()
        assert KafkaTopicFactory.reset_agent_a("1") in topics
        assert KafkaTopicFactory.reset_agent_a("2") in topics
        assert "reset_agent_a" not in topics  # no fallback for multi-gate


class TestProcessMessage:
    def test_returns_message_unchanged(self, gateway):
        msg = MagicMock()
        msg.MESSAGE_TYPE = "test"
        result = gateway.process_message(msg)
        assert result is msg
