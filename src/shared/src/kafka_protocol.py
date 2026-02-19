import json
import time
from abc import ABC, abstractmethod
from typing import Optional, List
import logging

logger = logging.getLogger("protocol")


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


# Message factory for deserialization
MESSAGE_TYPES = {
    TruckDetectedMessage.MESSAGE_TYPE: TruckDetectedMessage,
    LicensePlateResultsMessage.MESSAGE_TYPE: LicensePlateResultsMessage,
    HazardPlateResultsMessage.MESSAGE_TYPE: HazardPlateResultsMessage,
    DecisionResultsMessage.MESSAGE_TYPE: DecisionResultsMessage,
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
