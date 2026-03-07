import json
import time
from abc import ABC, abstractmethod
from typing import Optional, List
import logging

logger = logging.getLogger("protocol")

class KafkaTopicFactory:
    """Factory for generating consistent Kafka topic names based on gate_id."""

    @classmethod
    def truck_detected(cls, gate_id: str | int) -> str:
        return f"truck-detected-{gate_id}"

    @classmethod
    def license_plate_results(cls, gate_id: str | int) -> str:
        return f"lp-results-{gate_id}"

    @classmethod
    def hazard_plate_results(cls, gate_id: str | int) -> str:
        return f"hz-results-{gate_id}"

    @classmethod
    def agent_decision(cls, gate_id: str | int) -> str:
        return f"agent-decision-{gate_id}"
    
    @classmethod
    def operator_decision(cls, gate_id: str | int) -> str:
        return f"operator-decision-{gate_id}"

    @classmethod
    def reset_agent_a(cls, gate_id: str | int) -> str:
        return f"reset-agentA-{gate_id}"

    @classmethod
    def infraction_decision(cls, gate_id: str | int) -> str:
        return f"infraction-decision-{gate_id}"

    """Dont need gate_id because it is global to all network so 
       doesnt matter which gate is associated with the message"""
    @classmethod
    def scale_up(cls) -> str:
        return "scale-up"

    @classmethod
    def scale_down(cls) -> str:
        return "scale-down"

    @classmethod
    def global_topics(cls) -> list[str]:
        """Topics that don't require truck_id headers (system-level events)."""
        return [cls.scale_up(), cls.scale_down()]

    @classmethod
    def requires_truck_id(cls, topic: str) -> bool:
        """Whether a Kafka topic requires a truck_id header.

        Returns False for:
          - Global topics (scale-up, scale-down)
          - Command topics (reset-agentA-{gate_id})
        """
        if topic in cls.global_topics():
            return False
        if topic.startswith("reset-agentA-"):
            return False
        return True


class Message(ABC):
    """Base Message Type. Subclasses must implement to_dict() and from_dict()."""

    MESSAGE_TYPE: Optional[str] = None  # Must be overridden in subclasses

    def __init__(self, timestamp: Optional[int] = None) -> None:
        self.timestamp = timestamp if timestamp is not None else int(time.time() * 1000)

    @abstractmethod
    def to_dict(self) -> dict: ...

    def to_json(self) -> str:
        """Convenience method for JSON serialization."""
        return json.dumps(self.to_dict())

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict) -> "Message": ...


class TruckDetectedMessage(Message):
    """Message to signal truck detection."""

    MESSAGE_TYPE = "truck_detected"

    def __init__(self, confidence: float, num_detections: int, timestamp: Optional[int] = None) -> None:
        super().__init__(timestamp)
        self.confidence = confidence
        self.num_detections = num_detections

    def to_dict(self) -> dict:
        return {
            "message_type": self.MESSAGE_TYPE,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
            "num_detections": self.num_detections,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TruckDetectedMessage":
        """Reconstruct message from dict.

        Raises:
            ValueError: If a required field is missing.
        """
        try:
            return cls(
                confidence=data["confidence"],
                num_detections=data["num_detections"],
                timestamp=data.get("timestamp"),
            )
        except KeyError as e:
            raise ValueError(f"Missing required field {e} in {cls.MESSAGE_TYPE} message") from e


class LicensePlateResultsMessage(Message):
    """Message to send license plate results."""

    MESSAGE_TYPE = "license_plate_results"

    def __init__(self, license_plate: str, crop_url: str, confidence: float, timestamp: Optional[int] = None) -> None:
        super().__init__(timestamp)
        self.confidence = confidence
        self.license_plate = license_plate
        self.crop_url = crop_url

    def to_dict(self) -> dict:
        return {
            "message_type": self.MESSAGE_TYPE,
            "timestamp": self.timestamp,
            "license_plate": self.license_plate,
            "crop_url": self.crop_url,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LicensePlateResultsMessage":
        """Raises:
            ValueError: If a required field is missing.
        """
        try:
            return cls(
                license_plate=data["license_plate"],
                crop_url=data["crop_url"],
                confidence=data["confidence"],
                timestamp=data.get("timestamp"),
            )
        except KeyError as e:
            raise ValueError(f"Missing required field {e} in {cls.MESSAGE_TYPE} message") from e


class HazardPlateResultsMessage(Message):
    """Message to send hazard plate results."""

    MESSAGE_TYPE = "hazard_plate_results"

    def __init__(self, un: str, kemler: str, crop_url: str, confidence: float, timestamp: Optional[int] = None) -> None:
        super().__init__(timestamp)
        self.un = un
        self.kemler = kemler
        self.confidence = confidence
        self.crop_url = crop_url

    def to_dict(self) -> dict:
        return {
            "message_type": self.MESSAGE_TYPE,
            "timestamp": self.timestamp,
            "un": self.un,
            "kemler": self.kemler,
            "crop_url": self.crop_url,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HazardPlateResultsMessage":
        """Raises:
            ValueError: If a required field is missing.
        """
        try:
            return cls(
                un=data["un"],
                kemler=data["kemler"],
                crop_url=data["crop_url"],
                confidence=data["confidence"],
                timestamp=data.get("timestamp"),
            )
        except KeyError as e:
            raise ValueError(f"Missing required field {e} in {cls.MESSAGE_TYPE} message") from e


class DecisionResultsMessage(Message):
    """Message to send decision results."""

    MESSAGE_TYPE = "decision_results"

    def __init__(
        self,
        license_plate: str,
        license_crop_url: str,
        un: str,
        kemler: str,
        hazard_crop_url: str,
        alerts: List[str],
        route: str,
        decision: str,
        decision_reason: str,
        decision_source: str,
        timestamp: Optional[int] = None,
    ) -> None:
        super().__init__(timestamp)
        self.license_plate = license_plate
        self.license_crop_url = license_crop_url
        self.un = un
        self.kemler = kemler
        self.hazard_crop_url = hazard_crop_url
        self.alerts = alerts
        self.route = route
        self.decision = decision
        self.decision_reason = decision_reason
        self.decision_source = decision_source

    def to_dict(self) -> dict:
        return {
            "message_type": self.MESSAGE_TYPE,
            "timestamp": self.timestamp,
            "license_plate": self.license_plate,
            "license_crop_url": self.license_crop_url,
            "un": self.un,
            "kemler": self.kemler,
            "hazard_crop_url": self.hazard_crop_url,
            "alerts": self.alerts,
            "route": self.route,
            "decision": self.decision,
            "decision_reason": self.decision_reason,
            "decision_source": self.decision_source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DecisionResultsMessage":
        """Raises:
            ValueError: If a required field is missing.
        """
        try:
            return cls(
                license_plate=data["license_plate"],
                license_crop_url=data["license_crop_url"],
                un=data["un"],
                kemler=data["kemler"],
                hazard_crop_url=data["hazard_crop_url"],
                alerts=data["alerts"],
                route=data["route"],
                decision=data["decision"],
                decision_reason=data["decision_reason"],
                decision_source=data["decision_source"],
                timestamp=data.get("timestamp"),
            )
        except KeyError as e:
            raise ValueError(f"Missing required field {e} in {cls.MESSAGE_TYPE} message") from e

class ResetAgentAMessage(Message):
    """Message to reset agent A.
    This message is send by each the V-Brain after some time and logic passes by the decision agents.
    And has the functionality to reset the agent A to its detection state.
    """

    MESSAGE_TYPE = "reset_agent_a"

    def __init__(self, reason: str = "unknown", timestamp: Optional[int] = None) -> None:
        super().__init__(timestamp)
        self.reason = reason  # e.g. "agent_decision", "infraction_decision", "timeout"

    def to_dict(self) -> dict:
        return {
            "message_type": self.MESSAGE_TYPE,
            "timestamp": self.timestamp,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ResetAgentAMessage":
        """Reconstruct message from dict.

        Raises:
            ValueError: If a required field is missing.
        """
        try:
            return cls(
                reason=data.get("reason", "unknown"),
                timestamp=data.get("timestamp"),
            )
        except KeyError as e:
            raise ValueError(f"Missing required field {e} in {cls.MESSAGE_TYPE} message") from e


class InfractionDecisionMessage(Message):
    """Message published when a truck is detected making a possible highway infraction.
    Produced by Infraction_Decision and consumed by V_Brain.
    """

    MESSAGE_TYPE = "infraction_decision"

    def __init__(
        self,
        license_plate: str,
        license_crop_url: str,
        un: str,
        kemler: str,
        hazard_crop_url: str,
        infraction: bool,
        timestamp: Optional[int] = None,
    ) -> None:
        super().__init__(timestamp)
        self.license_plate = license_plate
        self.license_crop_url = license_crop_url
        self.un = un
        self.kemler = kemler
        self.hazard_crop_url = hazard_crop_url
        self.infraction = infraction

    def to_dict(self) -> dict:
        return {
            "message_type": self.MESSAGE_TYPE,
            "timestamp": self.timestamp,
            "license_plate": self.license_plate,
            "license_crop_url": self.license_crop_url,
            "un": self.un,
            "kemler": self.kemler,
            "hazard_crop_url": self.hazard_crop_url,
            "infraction": self.infraction,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InfractionDecisionMessage":
        """Raises:
            ValueError: If a required field is missing.
        """
        try:
            return cls(
                license_plate=data["license_plate"],
                license_crop_url=data["license_crop_url"],
                un=data["un"],
                kemler=data["kemler"],
                hazard_crop_url=data["hazard_crop_url"],
                infraction=data["infraction"],
                timestamp=data.get("timestamp"),
            )
        except KeyError as e:
            raise ValueError(f"Missing required field {e} in {cls.MESSAGE_TYPE} message") from e


class ScaleNetworkMessage(Message):
    """Message to signal the API_Gateway to connect to 4k stream or 720p stream.
    """

    MESSAGE_TYPE = "scale_network"

    def __init__(self, gate_id: str, mode: str, timestamp: Optional[int] = None) -> None:
        super().__init__(timestamp)
        self.gate_id = gate_id
        self.mode = mode                # "scale_up" or "scale_down"

    def to_dict(self) -> dict:
        return {
            "message_type": self.MESSAGE_TYPE,
            "timestamp": self.timestamp,
            "gate_id": self.gate_id,
            "mode": self.mode,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScaleNetworkMessage":
        """Raises:
            ValueError: If a required field is missing.
        """
        try:
            return cls(
                gate_id=data["gate_id"],
                mode=data["mode"],
                timestamp=data.get("timestamp"),
            )
        except KeyError as e:
            raise ValueError(f"Missing required field {e} in {cls.MESSAGE_TYPE} message") from e




# Message factory for deserialization
MESSAGE_TYPES = {
    TruckDetectedMessage.MESSAGE_TYPE: TruckDetectedMessage,
    LicensePlateResultsMessage.MESSAGE_TYPE: LicensePlateResultsMessage,
    HazardPlateResultsMessage.MESSAGE_TYPE: HazardPlateResultsMessage,
    DecisionResultsMessage.MESSAGE_TYPE: DecisionResultsMessage,
    ResetAgentAMessage.MESSAGE_TYPE: ResetAgentAMessage,
    InfractionDecisionMessage.MESSAGE_TYPE: InfractionDecisionMessage,
    ScaleNetworkMessage.MESSAGE_TYPE: ScaleNetworkMessage,
}


def deserialize_message(data: dict) -> Message:
    """Deserialize a message from a dictionary.

    Raises:
        ValueError: If the message_type is missing, unknown, or required fields are absent.
    """
    message_type = data.get("message_type")
    if message_type not in MESSAGE_TYPES:
        raise ValueError(f"Unknown or missing message_type: '{message_type}'")

    return MESSAGE_TYPES[message_type].from_dict(data)


class KafkaMessageProto:
    """Factory methods for creating kafka monitoring messages"""

    @classmethod
    def truck_detected(
        cls, confidence: float, num_detections: int
    ) -> TruckDetectedMessage:
        return TruckDetectedMessage(confidence, num_detections)

    @classmethod
    def license_plate_result(
        cls, license_plate: str, crop_url: str, confidence: float
    ) -> LicensePlateResultsMessage:
        return LicensePlateResultsMessage(license_plate, crop_url, confidence)

    @classmethod
    def hazard_plate_result(
        cls, un: str, kemler: str, crop_url: str, confidence: float
    ) -> HazardPlateResultsMessage:
        return HazardPlateResultsMessage(un, kemler, crop_url, confidence)

    @classmethod
    def decision_result(
        cls,
        license_plate: str,
        license_crop_url: str,
        un: str,
        kemler: str,
        hazard_crop_url: str,
        alerts: List[str],
        route: str,
        decision: str,
        decision_reason: str,
        decision_source: str,
    ) -> DecisionResultsMessage:
        return DecisionResultsMessage(
            license_plate,
            license_crop_url,
            un,
            kemler,
            hazard_crop_url,
            alerts,
            route,
            decision,
            decision_reason,
            decision_source,
        )

    @classmethod
    def reset_agent_a(cls, reason: str = "unknown") -> ResetAgentAMessage:
        return ResetAgentAMessage(reason=reason)

    @classmethod
    def infraction_decision(
        cls,
        license_plate: str,
        license_crop_url: str,
        un: str,
        kemler: str,
        hazard_crop_url: str,
        infraction: bool,
    ) -> InfractionDecisionMessage:
        return InfractionDecisionMessage(
            license_plate,
            license_crop_url,
            un,
            kemler,
            hazard_crop_url,
            infraction,
        )

    @classmethod
    def scale(cls, gate_id: str, mode: str) -> ScaleNetworkMessage:
        """Produce a scale message. Publish on KafkaTopicFactory.scale_up() or scale_down()
        depending on the desired mode ("scale_up" or "scale_down").
        """
        return ScaleNetworkMessage(gate_id, mode=mode)
