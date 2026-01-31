import json
import time
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger("protocol")


class Message:
    """Base Message Type"""

    MESSAGE_TYPE = "base"  # Override in subclasses

    def __init__(self) -> None:
        self.timestamp = int(time.time())

    def to_dict(self) -> dict:
        raise NotImplementedError("Subclasses must implement to_dict()")

    def to_json(self) -> str:
        """Convenience method for JSON serialization"""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict):
        """Deserialize from dictionary - override in subclasses"""
        raise NotImplementedError("Subclasses must implement from_dict()")


class TruckDetectedMessage(Message):
    """Message to signal truck detection"""

    MESSAGE_TYPE = "truck_detected"

    def __init__(self, confidence: float, num_detections: int) -> None:
        super().__init__()
        self.confidence = confidence
        self.num_detections = num_detections

    def to_dict(self) -> dict:
        return {
            "message_type": self.MESSAGE_TYPE,  # Added for deserialization
            "timestamp": self.timestamp,
            "confidence": self.confidence,
            "num_detections": self.num_detections,
        }

    @classmethod
    def from_dict(cls, data: dict):
        """Reconstruct message from dict (excluding timestamp)"""
        msg = cls(confidence=data["confidence"], num_detections=data["num_detections"])
        msg.timestamp = data.get("timestamp", msg.timestamp)
        return msg


class LicensePlateResultsMessage(Message):
    """Message to send license plate results"""

    MESSAGE_TYPE = "license_plate_results"

    def __init__(self, license_plate: str, crop_url: str, confidence: float) -> None:
        super().__init__()
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
    def from_dict(cls, data: dict):
        msg = cls(
            license_plate=data["license_plate"],
            crop_url=data["crop_url"],
            confidence=data["confidence"],
        )
        msg.timestamp = data.get("timestamp", msg.timestamp)
        return msg


class HazardPlateResultsMessage(Message):
    """Message to send hazard plate results"""

    MESSAGE_TYPE = "hazard_plate_results"

    def __init__(self, un: str, kemler: str, crop_url: str, confidence: float) -> None:
        super().__init__()
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
    def from_dict(cls, data: dict):
        msg = cls(
            un=data["un"],
            kemler=data["kemler"],
            crop_url=data["crop_url"],
            confidence=data["confidence"],
        )
        msg.timestamp = data.get("timestamp", msg.timestamp)
        return msg


class DecisionResultsMessage(Message):
    """Message to send decision results"""

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
    ) -> None:
        super().__init__()
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
    def from_dict(cls, data: dict):
        msg = cls(
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
        )
        msg.timestamp = data.get("timestamp", msg.timestamp)
        return msg


# Message factory for deserialization
MESSAGE_TYPES = {
    TruckDetectedMessage.MESSAGE_TYPE: TruckDetectedMessage,
    LicensePlateResultsMessage.MESSAGE_TYPE: LicensePlateResultsMessage,
    HazardPlateResultsMessage.MESSAGE_TYPE: HazardPlateResultsMessage,
    DecisionResultsMessage.MESSAGE_TYPE: DecisionResultsMessage,
}


def deserialize_message(data: dict) -> Optional[Message]:
    """Deserialize a message from a dictionary"""
    message_type = data.get("message_type")
    if message_type not in MESSAGE_TYPES:
        logger.warning(f"Unknown message type: {message_type}")
        return None

    message_class = MESSAGE_TYPES[message_type]
    return message_class.from_dict(data)


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
