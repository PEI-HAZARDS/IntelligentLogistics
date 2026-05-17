from AI_APP.shared.src.base_agent import BaseAgent, BaseAgentConfig
from shared.src.kafka_protocol import KafkaMessageProto, Message, KafkaTopicFactory
from AI_APP.shared.src.plate_classifier import PlateClassifier
from AI_APP.shared.src.image_storage import ImageStorage
from AI_APP.shared.src.paddle_ocr import OCR
import os
import logging

from typing import Optional
from prometheus_client import Counter, Histogram # type: ignore
from pydantic import Field

class AgentBConfig(BaseAgentConfig):
    min_detection_confidence: float = Field(
        default=0.6, 
        alias="AGENT_B_MIN_DETECTION_CONFIDENCE"
    )

class AgentB(BaseAgent):
    """
    Agent B: License Plate Detection
    
    Extends BaseAgent to:
    - Detect license plates using YOLO
    - Extract text using OCR with consensus algorithm
    - Classify plates to reject hazard plates
    - Publish license plate results to Kafka
    """

    def __init__(self, config: Optional[AgentBConfig] = None, **kwargs):
        """Initialize Agent B with license plate detection capabilities."""
        config = config or AgentBConfig()
        # Call parent constructor first so self.config is available
        super().__init__(config=config, **kwargs)
        
        # Restore logging level right after BaseAgent initialization (PaddleOCR suppresses it)
        logging.getLogger().setLevel(logging.INFO)
        self.logger.info(f"Agent B initialized with min_detection_confidence={self.config.min_detection_confidence}")
        # Separate storage bucket for rejected crops (requires self.config)
        self.crop_fails = ImageStorage(self.config.minio_config, "failed-crops")

    # ========================================================================
    # Required abstract method implementations
    # ========================================================================

    def get_agent_name(self) -> str:
        """Return agent identifier."""
        return "AgentB"
    
    def initialize_ocr(self) -> OCR:
        """Initialize and return OCR instance."""
        return OCR()
    
    def get_bbox_color(self) -> str:
        """Return bbox color (e.g., 'Red', 'Green')."""
        return "blue"
    
    def get_bbox_label(self) -> str:
        """Return bbox label (e.g., 'truck', 'car')."""
        return "License Plate"

    def get_yolo_model_path(self) -> str:
        """Return path to license plate YOLO model."""
        return os.getenv("MODELS_PATH", "/agentB/data") + "/license_plate_model.pt"

    def get_bucket(self) -> str:
        """Return bucket name for annotated frames and crops."""
        return f"agentb-{self.config.gate_id}"

    def get_consume_topic(self) -> str:
        """Return Kafka topic to consume truck detection events."""
        return KafkaTopicFactory.truck_detected(self.config.gate_id)

    def get_produce_topic(self) -> str:
        """Return Kafka topic to produce license plate results."""
        return KafkaTopicFactory.license_plate_results(self.config.gate_id)

    def get_object_type(self) -> str:
        """Return detected object type name."""
        return "license plate"

    def is_valid_detection(self, crop, confidence: float, box_index: int) -> bool:
        """
        Validate detection by checking plate classification.
        Reject hazard plates.
        """
        classification = self.classifier.classify(crop)

        if classification == PlateClassifier.HAZARD_PLATE:
            self.logger.info(
                f"Crop {box_index} rejected as {classification}, "
                "uploading to MinIO for analysis.")
            return False

        self.logger.info(f"Crop {box_index} accepted as LICENSE_PLATE")
        self.plates_detected.inc()
        return True

    def _build_message_for_detection(self, license_plate: str, confidence: float, crop_url: Optional[str]) -> Message:
        """Build license plate results message."""
        return KafkaMessageProto.license_plate_result(
            license_plate=license_plate,
            crop_url=crop_url if crop_url else "",
            confidence=confidence
        )

    def init_metrics(self) -> None:
        """Initialize Prometheus metrics for Agent B."""
        self.inference_latency = Histogram(
            'agent_b_inference_latency_seconds', 
            'Time spent running YOLO (LP) inference',
            buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0]
        )
        self.frames_processed_metric = Counter(
            'agent_b_frames_processed_total', 
            'Total number of frames processed by Agent B'
        )
        self.plates_detected = Counter(
            'agent_b_plates_detected_total', 
            'Total number of license plates detected'
        )
        self.ocr_confidence = Histogram(
            'agent_b_ocr_confidence', 
            'Confidence score of OCR readings',
            buckets=[0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99]
        )

    def get_detection_metric(self) -> Optional[object]:
        """plates_detected is incremented directly in is_valid_detection; no separate counter needed here."""
        return None