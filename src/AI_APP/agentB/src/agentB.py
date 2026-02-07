from shared.src.base_agent import BaseAgent
from shared.src.kafka_protocol import LicensePlateResultsMessage, KafkaMessageProto, Message
from shared.src.plate_classifier import PlateClassifier
from shared.src.image_storage import ImageStorage
from shared.src.paddle_ocr import OCR

import os
from typing import Optional
from prometheus_client import Counter, Histogram # type: ignore


class AgentB(BaseAgent):
    """
    Agent B: License Plate Detection
    
    Extends BaseAgent to:
    - Detect license plates using YOLO
    - Extract text using OCR with consensus algorithm
    - Classify plates to reject hazard plates
    - Publish license plate results to Kafka
    """

    def __init__(self, **kwargs):
        """Initialize Agent B with license plate detection capabilities."""
        # Create separate storage for failed crops
        minio_host = os.getenv("MINIO_HOST", "10.255.32.82")
        minio_port = os.getenv("MINIO_PORT", "9000")
        minio_conf = {
            "endpoint": f"{minio_host}:{minio_port}",
            "access_key": os.getenv("ACCESS_KEY"),
            "secret_key": os.getenv("SECRET_KEY"),
            "secure": False
        }
        self.crop_fails = ImageStorage(minio_conf, "failed-crops")
        
        # Call parent constructor (forwards any injected dependencies)
        super().__init__(**kwargs)

    # ========================================================================
    # Required abstract method implementations
    # ========================================================================

    def get_agent_name(self) -> str:
        """Return agent identifier."""
        return "AgentB"
    
    def initiallize_ocr(self) -> OCR:
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
        return "/agentB/data/license_plate_model.pt"

    def get_bucket(self) -> str:
        """Return bucket name for annotated frames and crops."""
        return f"agentb-{self.gate_id}"

    def get_consume_topic(self) -> str:
        """Return Kafka topic to consume truck detection events."""
        return f"truck-detected-{self.gate_id}"

    def get_produce_topic(self) -> str:
        """Return Kafka topic to produce license plate results."""
        return f"lp-results-{self.gate_id}"

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
                f"[AgentB] Crop {box_index} rejected as {classification}, "
                "uploading to MinIO for analysis.")
            return False

        self.logger.info(f"[AgentB] Crop {box_index} accepted as LICENSE_PLATE")
        self.plates_detected.inc()
        return True

    def _build_message_for_detection(self, license_plate: str, confidence: float, crop_url: Optional[str]) -> Message:
        """Build license plate results message."""
        return KafkaMessageProto.license_plate_result(
            license_plate=license_plate,
            crop_url=crop_url if crop_url else "",
            confidence=confidence
        )

    def init_metrics(self):
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