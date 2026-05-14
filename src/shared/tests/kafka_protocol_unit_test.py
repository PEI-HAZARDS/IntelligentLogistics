"""
Unit tests for kafka_protocol.py — KafkaTopicFactory, Message subclasses,
deserialize_message, and KafkaMessageProto.
"""

import json
import time
import pytest

from shared.src.kafka_protocol import (
    KafkaTopicFactory,
    TruckDetectedMessage,
    LicensePlateResultsMessage,
    HazardPlateResultsMessage,
    DecisionResultsMessage,
    ResetAgentAMessage,
    InfractionDecisionMessage,
    ScaleNetworkMessage,
    KafkaMessageProto,
    deserialize_message,
    MESSAGE_TYPES,
)


# ═══════════════════════════════════════════════════════════════════
# KafkaTopicFactory
# ═══════════════════════════════════════════════════════════════════

class TestKafkaTopicFactory:
    def test_truck_detected(self):
        assert KafkaTopicFactory.truck_detected("1") == "truck-detected-1"
        assert KafkaTopicFactory.truck_detected(2) == "truck-detected-2"

    def test_license_plate_results(self):
        assert KafkaTopicFactory.license_plate_results("3") == "lp-results-3"

    def test_hazard_plate_results(self):
        assert KafkaTopicFactory.hazard_plate_results("4") == "hz-results-4"

    def test_agent_decision(self):
        assert KafkaTopicFactory.agent_decision("5") == "agent-decision-5"

    def test_operator_decision(self):
        assert KafkaTopicFactory.operator_decision("1") == "operator-decision-1"

    def test_reset_agent_a(self):
        assert KafkaTopicFactory.reset_agent_a("6") == "reset-agentA-6"

    def test_infraction_decision(self):
        assert KafkaTopicFactory.infraction_decision("7") == "infraction-decision-7"

    def test_dlq_topic(self):
        assert KafkaTopicFactory.dlq("agent-decision-1") == "agent-decision-1.DLQ"

    def test_scale_up(self):
        assert KafkaTopicFactory.scale_up() == "scale-up"

    def test_scale_down(self):
        assert KafkaTopicFactory.scale_down() == "scale-down"

    def test_global_topics(self):
        topics = KafkaTopicFactory.global_topics()
        assert "scale-up" in topics
        assert "scale-down" in topics

    def test_requires_truck_id_normal_topic(self):
        assert KafkaTopicFactory.requires_truck_id("truck-detected-1") is True
        assert KafkaTopicFactory.requires_truck_id("lp-results-1") is True

    def test_requires_truck_id_global_topic(self):
        assert KafkaTopicFactory.requires_truck_id("scale-up") is False
        assert KafkaTopicFactory.requires_truck_id("scale-down") is False

    def test_requires_truck_id_reset_topic(self):
        assert KafkaTopicFactory.requires_truck_id("reset-agentA-1") is False
        assert KafkaTopicFactory.requires_truck_id("reset-agentA-99") is False


# ═══════════════════════════════════════════════════════════════════
# TruckDetectedMessage
# ═══════════════════════════════════════════════════════════════════

class TestTruckDetectedMessage:
    def test_creation_and_to_dict(self):
        msg = TruckDetectedMessage(confidence=0.95, num_detections=3)
        d = msg.to_dict()
        assert d["message_type"] == "truck_detected"
        assert d["confidence"] == 0.95
        assert d["num_detections"] == 3
        assert "timestamp" in d

    def test_custom_timestamp(self):
        msg = TruckDetectedMessage(confidence=0.5, num_detections=1, timestamp=12345)
        assert msg.timestamp == 12345

    def test_auto_timestamp(self):
        before = int(time.time() * 1000)
        msg = TruckDetectedMessage(confidence=0.5, num_detections=1)
        after = int(time.time() * 1000)
        assert before <= msg.timestamp <= after

    def test_from_dict(self):
        data = {"confidence": 0.8, "num_detections": 2, "timestamp": 99999}
        msg = TruckDetectedMessage.from_dict(data)
        assert msg.confidence == 0.8
        assert msg.num_detections == 2
        assert msg.timestamp == 99999

    def test_from_dict_no_timestamp(self):
        data = {"confidence": 0.8, "num_detections": 2}
        msg = TruckDetectedMessage.from_dict(data)
        assert msg.confidence == 0.8
        assert msg.timestamp is not None

    def test_from_dict_missing_field(self):
        with pytest.raises(ValueError, match="Missing required field"):
            TruckDetectedMessage.from_dict({"confidence": 0.5})

    def test_to_json(self):
        msg = TruckDetectedMessage(confidence=0.9, num_detections=1, timestamp=100)
        parsed = json.loads(msg.to_json())
        assert parsed["confidence"] == 0.9

    def test_roundtrip(self):
        original = TruckDetectedMessage(confidence=0.7, num_detections=5, timestamp=42)
        restored = TruckDetectedMessage.from_dict(original.to_dict())
        assert restored.confidence == original.confidence
        assert restored.num_detections == original.num_detections
        assert restored.timestamp == original.timestamp

    def test_message_type(self):
        assert TruckDetectedMessage.MESSAGE_TYPE == "truck_detected"


# ═══════════════════════════════════════════════════════════════════
# LicensePlateResultsMessage
# ═══════════════════════════════════════════════════════════════════

class TestLicensePlateResultsMessage:
    def test_creation_and_to_dict(self):
        msg = LicensePlateResultsMessage(
            license_plate="AB12CD", crop_url="http://img/lp.jpg", confidence=0.95
        )
        d = msg.to_dict()
        assert d["message_type"] == "license_plate_results"
        assert d["license_plate"] == "AB12CD"
        assert d["crop_url"] == "http://img/lp.jpg"
        assert d["confidence"] == 0.95

    def test_from_dict(self):
        data = {
            "license_plate": "XY99ZZ",
            "crop_url": "http://img/lp2.jpg",
            "confidence": 0.88,
            "timestamp": 55555,
        }
        msg = LicensePlateResultsMessage.from_dict(data)
        assert msg.license_plate == "XY99ZZ"
        assert msg.crop_url == "http://img/lp2.jpg"
        assert msg.timestamp == 55555

    def test_from_dict_missing_field(self):
        with pytest.raises(ValueError, match="Missing required field"):
            LicensePlateResultsMessage.from_dict({"license_plate": "AB12CD"})

    def test_roundtrip(self):
        original = LicensePlateResultsMessage("PL", "url", 0.5, timestamp=1)
        restored = LicensePlateResultsMessage.from_dict(original.to_dict())
        assert restored.license_plate == original.license_plate
        assert restored.crop_url == original.crop_url
        assert restored.confidence == original.confidence


# ═══════════════════════════════════════════════════════════════════
# HazardPlateResultsMessage
# ═══════════════════════════════════════════════════════════════════

class TestHazardPlateResultsMessage:
    def test_creation_and_to_dict(self):
        msg = HazardPlateResultsMessage(
            un="1234", kemler="33", crop_url="http://img/hz.jpg", confidence=0.9
        )
        d = msg.to_dict()
        assert d["message_type"] == "hazard_plate_results"
        assert d["un"] == "1234"
        assert d["kemler"] == "33"
        assert d["crop_url"] == "http://img/hz.jpg"

    def test_from_dict(self):
        data = {
            "un": "5678",
            "kemler": "X88",
            "crop_url": "url",
            "confidence": 0.7,
            "timestamp": 10,
        }
        msg = HazardPlateResultsMessage.from_dict(data)
        assert msg.un == "5678"
        assert msg.kemler == "X88"

    def test_from_dict_missing_field(self):
        with pytest.raises(ValueError, match="Missing required field"):
            HazardPlateResultsMessage.from_dict({"un": "1"})

    def test_roundtrip(self):
        original = HazardPlateResultsMessage("U", "K", "url", 0.1, timestamp=2)
        restored = HazardPlateResultsMessage.from_dict(original.to_dict())
        assert restored.un == original.un
        assert restored.kemler == original.kemler


# ═══════════════════════════════════════════════════════════════════
# DecisionResultsMessage
# ═══════════════════════════════════════════════════════════════════

class TestDecisionResultsMessage:
    def _make_data(self, **overrides) -> dict:
        base = {
            "license_plate": "AB12CD",
            "license_crop_url": "http://lp.jpg",
            "un": "1234",
            "kemler": "33",
            "hazard_crop_url": "http://hz.jpg",
            "alerts": ["alert1"],
            "route": "A",
            "decision": "ACCEPTED",
            "decision_reason": "ok",
            "decision_source": "agent",
        }
        base.update(overrides)
        return base

    def test_creation_and_to_dict(self):
        msg = DecisionResultsMessage(**self._make_data())
        d = msg.to_dict()
        assert d["message_type"] == "decision_results"
        assert d["license_plate"] == "AB12CD"
        assert d["alerts"] == ["alert1"]
        assert d["decision"] == "ACCEPTED"

    def test_from_dict(self):
        data = self._make_data(timestamp=999)
        msg = DecisionResultsMessage.from_dict(data)
        assert msg.license_plate == "AB12CD"
        assert msg.decision_source == "agent"
        assert msg.timestamp == 999

    def test_from_dict_missing_field(self):
        with pytest.raises(ValueError, match="Missing required field"):
            DecisionResultsMessage.from_dict({"license_plate": "AB"})

    def test_roundtrip(self):
        original = DecisionResultsMessage(**self._make_data(timestamp=42))
        restored = DecisionResultsMessage.from_dict(original.to_dict())
        assert restored.decision == original.decision
        assert restored.decision_reason == original.decision_reason
        assert restored.alerts == original.alerts


# ═══════════════════════════════════════════════════════════════════
# ResetAgentAMessage
# ═══════════════════════════════════════════════════════════════════

class TestResetAgentAMessage:
    def test_default_reason(self):
        msg = ResetAgentAMessage()
        assert msg.reason == "unknown"

    def test_custom_reason(self):
        msg = ResetAgentAMessage(reason="timeout")
        d = msg.to_dict()
        assert d["reason"] == "timeout"
        assert d["message_type"] == "reset_agent_a"

    def test_from_dict(self):
        data = {"reason": "agent_decision", "timestamp": 100}
        msg = ResetAgentAMessage.from_dict(data)
        assert msg.reason == "agent_decision"

    def test_from_dict_defaults_reason(self):
        msg = ResetAgentAMessage.from_dict({})
        assert msg.reason == "unknown"

    def test_roundtrip(self):
        original = ResetAgentAMessage(reason="test", timestamp=7)
        restored = ResetAgentAMessage.from_dict(original.to_dict())
        assert restored.reason == original.reason


# ═══════════════════════════════════════════════════════════════════
# InfractionDecisionMessage
# ═══════════════════════════════════════════════════════════════════

class TestInfractionDecisionMessage:
    def test_creation_and_to_dict(self):
        msg = InfractionDecisionMessage(
            license_plate="LP1",
            license_crop_url="url_lp",
            un="9999",
            kemler="X",
            hazard_crop_url="url_hz",
            infraction=True,
        )
        d = msg.to_dict()
        assert d["message_type"] == "infraction_decision"
        assert d["infraction"] is True
        assert d["un"] == "9999"

    def test_from_dict(self):
        data = {
            "license_plate": "LP2",
            "license_crop_url": "u1",
            "un": "0000",
            "kemler": "Y",
            "hazard_crop_url": "u2",
            "infraction": False,
            "timestamp": 88,
        }
        msg = InfractionDecisionMessage.from_dict(data)
        assert msg.infraction is False
        assert msg.timestamp == 88

    def test_from_dict_missing_field(self):
        with pytest.raises(ValueError, match="Missing required field"):
            InfractionDecisionMessage.from_dict({"license_plate": "LP"})

    def test_roundtrip(self):
        original = InfractionDecisionMessage("p", "u1", "u", "k", "u2", True, timestamp=5)
        restored = InfractionDecisionMessage.from_dict(original.to_dict())
        assert restored.infraction == original.infraction


# ═══════════════════════════════════════════════════════════════════
# ScaleNetworkMessage
# ═══════════════════════════════════════════════════════════════════

class TestScaleNetworkMessage:
    def test_creation_and_to_dict(self):
        msg = ScaleNetworkMessage(gate_id="1", mode="scale_up")
        d = msg.to_dict()
        assert d["message_type"] == "scale_network"
        assert d["gate_id"] == "1"
        assert d["mode"] == "scale_up"

    def test_from_dict(self):
        data = {"gate_id": "2", "mode": "scale_down", "timestamp": 77}
        msg = ScaleNetworkMessage.from_dict(data)
        assert msg.gate_id == "2"
        assert msg.mode == "scale_down"

    def test_from_dict_missing_field(self):
        with pytest.raises(ValueError, match="Missing required field"):
            ScaleNetworkMessage.from_dict({"gate_id": "1"})

    def test_roundtrip(self):
        original = ScaleNetworkMessage("3", "scale_up", timestamp=9)
        restored = ScaleNetworkMessage.from_dict(original.to_dict())
        assert restored.gate_id == original.gate_id
        assert restored.mode == original.mode


# ═══════════════════════════════════════════════════════════════════
# deserialize_message
# ═══════════════════════════════════════════════════════════════════

class TestDeserializeMessage:
    def test_known_types(self):
        for msg_type, cls in MESSAGE_TYPES.items():
            assert msg_type == cls.MESSAGE_TYPE

    def test_truck_detected(self):
        data = {"message_type": "truck_detected", "confidence": 0.9, "num_detections": 1}
        msg = deserialize_message(data)
        assert isinstance(msg, TruckDetectedMessage)

    def test_license_plate_results(self):
        data = {
            "message_type": "license_plate_results",
            "license_plate": "AB",
            "crop_url": "u",
            "confidence": 0.5,
        }
        msg = deserialize_message(data)
        assert isinstance(msg, LicensePlateResultsMessage)

    def test_hazard_plate_results(self):
        data = {
            "message_type": "hazard_plate_results",
            "un": "1",
            "kemler": "2",
            "crop_url": "u",
            "confidence": 0.6,
        }
        msg = deserialize_message(data)
        assert isinstance(msg, HazardPlateResultsMessage)

    def test_decision_results(self):
        data = {
            "message_type": "decision_results",
            "license_plate": "p",
            "license_crop_url": "u",
            "un": "1",
            "kemler": "2",
            "hazard_crop_url": "u2",
            "alerts": [],
            "route": "A",
            "decision": "ACCEPTED",
            "decision_reason": "ok",
            "decision_source": "agent",
        }
        msg = deserialize_message(data)
        assert isinstance(msg, DecisionResultsMessage)

    def test_reset_agent_a(self):
        data = {"message_type": "reset_agent_a"}
        msg = deserialize_message(data)
        assert isinstance(msg, ResetAgentAMessage)

    def test_infraction_decision(self):
        data = {
            "message_type": "infraction_decision",
            "license_plate": "p",
            "license_crop_url": "u",
            "un": "1",
            "kemler": "2",
            "hazard_crop_url": "u2",
            "infraction": True,
        }
        msg = deserialize_message(data)
        assert isinstance(msg, InfractionDecisionMessage)

    def test_scale_network(self):
        data = {"message_type": "scale_network", "gate_id": "1", "mode": "scale_up"}
        msg = deserialize_message(data)
        assert isinstance(msg, ScaleNetworkMessage)

    def test_unknown_type(self):
        with pytest.raises(ValueError, match="Unknown or missing message_type"):
            deserialize_message({"message_type": "bogus"})

    def test_missing_type(self):
        with pytest.raises(ValueError, match="Unknown or missing message_type"):
            deserialize_message({"some": "data"})


# ═══════════════════════════════════════════════════════════════════
# KafkaMessageProto
# ═══════════════════════════════════════════════════════════════════

class TestKafkaMessageProto:
    def test_truck_detected(self):
        msg = KafkaMessageProto.truck_detected(0.9, 2)
        assert isinstance(msg, TruckDetectedMessage)
        assert msg.confidence == 0.9
        assert msg.num_detections == 2

    def test_license_plate_result(self):
        msg = KafkaMessageProto.license_plate_result("AB", "url", 0.8)
        assert isinstance(msg, LicensePlateResultsMessage)
        assert msg.license_plate == "AB"

    def test_hazard_plate_result(self):
        msg = KafkaMessageProto.hazard_plate_result("1", "2", "url", 0.7)
        assert isinstance(msg, HazardPlateResultsMessage)
        assert msg.un == "1"
        assert msg.kemler == "2"

    def test_decision_result(self):
        msg = KafkaMessageProto.decision_result(
            "LP", "u1", "U", "K", "u2", ["a"], "R", "ACCEPTED", "ok", "agent"
        )
        assert isinstance(msg, DecisionResultsMessage)
        assert msg.decision == "ACCEPTED"

    def test_reset_agent_a(self):
        msg = KafkaMessageProto.reset_agent_a(reason="timeout")
        assert isinstance(msg, ResetAgentAMessage)
        assert msg.reason == "timeout"

    def test_reset_agent_a_default(self):
        msg = KafkaMessageProto.reset_agent_a()
        assert msg.reason == "unknown"

    def test_infraction_decision(self):
        msg = KafkaMessageProto.infraction_decision("LP", "u1", "U", "K", "u2", True)
        assert isinstance(msg, InfractionDecisionMessage)
        assert msg.infraction is True

    def test_scale(self):
        msg = KafkaMessageProto.scale(gate_id="1", mode="scale_down")
        assert isinstance(msg, ScaleNetworkMessage)
        assert msg.gate_id == "1"
        assert msg.mode == "scale_down"
