"""
Unit tests for DecisionCorrelator and KafkaDecisionConsumer.
"""

import sys
import os
import json
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone

import pytest

# ─── Mock external dependencies before importing ────────────────

# Ensure the Data_Module directory is on the path
_data_module_dir = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _data_module_dir)

# Mock Redis
mock_redis_client = MagicMock()
redis_module = MagicMock()
redis_module.redis_client = mock_redis_client
sys.modules["db.redis"] = redis_module
sys.modules["db"] = MagicMock()

# Mock config
mock_settings = MagicMock()
mock_settings.gate_id = "1"
mock_settings.kafka_bootstrap = "localhost:9092"
config_module = MagicMock()
config_module.settings = mock_settings
sys.modules["config"] = config_module

# Mock services that kafka_decision_consumer imports
sys.modules["services.decision_service"] = MagicMock()
sys.modules["services.notification_service"] = MagicMock()

from services.kafka_decision_consumer import DecisionCorrelator, KafkaDecisionConsumer


# ═══════════════════════════════════════════════════════════════════
# DecisionCorrelator
# ═══════════════════════════════════════════════════════════════════

class TestDecisionCorrelator:
    @pytest.fixture
    def correlator(self):
        c = DecisionCorrelator()
        c.redis = MagicMock()
        return c

    # ── process_agent_decision ────────────────────────────────────

    def test_accepted_returns_final_decision(self, correlator):
        data = {"decision": "ACCEPTED", "license_plate": "AB12CD"}
        result = correlator.process_agent_decision("t1", data)
        assert result is not None
        assert result["decision_source"] == "agent"
        assert "processed_at" in result

    def test_manual_review_stores_in_redis(self, correlator):
        data = {"decision": "MANUAL_REVIEW", "license_plate": "AB12CD"}
        result = correlator.process_agent_decision("t1", data)
        assert result is None
        correlator.redis.setex.assert_called_once()
        key = correlator.redis.setex.call_args[0][0]
        assert key == "pending_review:t1"

    def test_manual_review_redis_failure(self, correlator):
        correlator.redis.setex.side_effect = Exception("Redis down")
        data = {"decision": "MANUAL_REVIEW", "license_plate": "AB12CD"}
        result = correlator.process_agent_decision("t1", data)
        assert result is None  # doesn't crash

    def test_unknown_status_returns_none(self, correlator):
        data = {"decision": "UNKNOWN_STATUS"}
        result = correlator.process_agent_decision("t1", data)
        assert result is None

    # ── process_operator_decision ─────────────────────────────────

    def test_operator_with_pending_agent(self, correlator):
        agent_data = {"decision": "MANUAL_REVIEW", "decision_reason": "flagged", "license_plate": "AB12CD"}
        correlator.redis.get.return_value = json.dumps(agent_data)
        operator_data = {"decision": "APPROVED", "decision_reason": "operator override", "license_plate": "AB12CD"}

        result = correlator.process_operator_decision("t1", operator_data)

        assert result is not None
        assert result["decision"] == "APPROVED"
        assert result["decision_source"] == "operator"
        assert result["agent_decision"] == "MANUAL_REVIEW"
        correlator.redis.delete.assert_called_once()

    def test_operator_without_pending_agent(self, correlator):
        correlator.redis.get.return_value = None
        operator_data = {"decision": "APPROVED", "license_plate": "AB12CD"}

        result = correlator.process_operator_decision("t1", operator_data)

        assert result is not None
        assert result["decision_source"] == "operator"

    def test_operator_redis_failure(self, correlator):
        correlator.redis.get.side_effect = Exception("Redis down")
        operator_data = {"decision": "APPROVED", "license_plate": "AB12CD"}
        result = correlator.process_operator_decision("t1", operator_data)
        assert result is not None
        assert result["decision_source"] == "operator"

    # ── _build_final_decision ─────────────────────────────────────

    def test_build_final_decision(self, correlator):
        data = {"a": 1, "b": 2}
        result = correlator._build_final_decision(data, source="test")
        assert result["decision_source"] == "test"
        assert result["a"] == 1
        assert "processed_at" in result

    # ── _merge_decisions ──────────────────────────────────────────

    def test_merge_decisions(self, correlator):
        agent = {"decision": "MANUAL_REVIEW", "decision_reason": "suspicious"}
        operator = {"decision": "APPROVED", "decision_reason": "ok", "license_plate": "LP"}

        result = correlator._merge_decisions(agent, operator)
        assert result["decision"] == "APPROVED"
        assert result["agent_decision"] == "MANUAL_REVIEW"
        assert result["operator_decision"] == "APPROVED"
        assert result["decision_source"] == "operator"
        assert result["license_plate"] == "LP"


# ═══════════════════════════════════════════════════════════════════
# KafkaDecisionConsumer
# ═══════════════════════════════════════════════════════════════════

class TestKafkaDecisionConsumer:
    @pytest.fixture
    def consumer(self):
        mock_kafka = MagicMock()
        c = KafkaDecisionConsumer(consumer=mock_kafka)
        c.correlator = MagicMock()
        return c

    def test_init(self, consumer):
        assert consumer.running is False

    def test_init_uses_multigate_env_topics(self):
        mock_kafka = MagicMock()
        with patch.dict(os.environ, {
            "DECISION_GATE_IDS": '["1","3"]',
            "INFRACTION_GATE_IDS": '["2"]',
        }):
            c = KafkaDecisionConsumer(consumer=mock_kafka)

        assert c.agent_decision_topics == {"agent-decision-1", "agent-decision-3"}
        assert c.operator_decision_topics == {"operator-decision-1", "operator-decision-3"}
        assert c.infraction_decision_topics == {"infraction-decision-2"}

    def test_start(self, consumer):
        consumer.running = False
        # Mock _consume_loop to complete immediately
        async def _run():
            with patch.object(consumer, "_consume_loop", new_callable=AsyncMock):
                await consumer.start()
                assert consumer.running is True
                assert consumer.consumer_task is not None
                await consumer.stop()
        asyncio.run(_run())

    def test_start_already_running(self, consumer):
        consumer.running = True
        asyncio.run(consumer.start())
        assert consumer.consumer_task is None

    def test_stop(self, consumer):
        async def _run():
            consumer.running = True
            consumer.consumer_task = asyncio.create_task(asyncio.sleep(10))
            await consumer.stop()
            assert consumer.running is False
        asyncio.run(_run())

    def test_stop_no_task(self, consumer):
        async def _run():
            consumer.running = True
            consumer.consumer_task = None
            await consumer.stop()
            assert consumer.running is False
        asyncio.run(_run())

    def test_store_infraction_decision_updates_appointment(self, consumer):
        data = {
            "license_plate": "AB12CD",
            "infraction": True,
            "un": "1203",
            "kemler": "33",
        }

        async def _run():
            with patch("services.kafka_decision_consumer.persist_infraction_event_from_kafka", return_value="event-123") as persist_mock, \
                 patch("services.kafka_decision_consumer.update_appointment_after_infraction", return_value={
                     "appointment_id": 42,
                     "old_highway_infraction": False,
                     "new_highway_infraction": True,
                 }) as update_mock, \
                 patch("services.kafka_decision_consumer.create_notification") as notif_mock:
                await consumer._store_infraction_decision("truck-1", data)

                persist_mock.assert_called_once()
                update_mock.assert_called_once_with("AB12CD", True)
                notif_mock.assert_called_once()

        asyncio.run(_run())

    def test_store_infraction_decision_without_infraction_skips_update(self, consumer):
        data = {
            "license_plate": "AB12CD",
            "infraction": False,
        }

        async def _run():
            with patch("services.kafka_decision_consumer.persist_infraction_event_from_kafka", return_value="event-456") as persist_mock, \
                 patch("services.kafka_decision_consumer.update_appointment_after_infraction") as update_mock, \
                 patch("services.kafka_decision_consumer.create_notification") as notif_mock:
                await consumer._store_infraction_decision("truck-2", data)

                persist_mock.assert_called_once()
                update_mock.assert_not_called()
                notif_mock.assert_not_called()

        asyncio.run(_run())

    def test_store_infraction_decision_missing_plate_skips_update(self, consumer):
        data = {
            "license_plate": "N/A",
            "infraction": True,
        }

        async def _run():
            with patch("services.kafka_decision_consumer.persist_infraction_event_from_kafka", return_value="event-789") as persist_mock, \
                 patch("services.kafka_decision_consumer.update_appointment_after_infraction") as update_mock, \
                 patch("services.kafka_decision_consumer.create_notification") as notif_mock:
                await consumer._store_infraction_decision("truck-3", data)

                persist_mock.assert_called_once()
                update_mock.assert_not_called()
                notif_mock.assert_not_called()

        asyncio.run(_run())

    def test_extract_gate_id_from_topic(self, consumer):
        assert consumer._extract_gate_id_from_topic("infraction-decision-2") == "2"
        assert consumer._extract_gate_id_from_topic("agent-decision-gateA") == "gateA"
        assert consumer._extract_gate_id_from_topic("unknown-topic") is None
