from shared.src.base_agent import BaseAgent
from shared.src.plate_classifier import PlateClassifier
from shared.src.paddle_ocr import OCR
from shared.src.kafka_protocol import HazardPlateResultsMessage, KafkaMessageProto, Message

import os
from typing import Optional
from prometheus_client import Counter, Histogram # type: ignore


class AgentC(BaseAgent):
    """
    Agent C: Hazard Plate Detection
    
    Extends BaseAgent to:
    - Detect hazard plates using YOLO
    - Extract UN and Kemler codes using OCR with consensus algorithm
    - Publish hazard plate results to Kafka
    """

    def __init__(self, **kwargs):
        """Initialize Agent C with hazard plate detection capabilities."""
        # Call parent constructor (forwards any injected dependencies)
        super().__init__(**kwargs)

    # ========================================================================
    # Required abstract method implementations
    # ========================================================================

    def get_agent_name(self) -> str:
        """Return agent identifier."""
        return "AgentC"
    
    def initiallize_ocr(self) -> OCR:
        """Initialize and return OCR instance."""
        allowed_chars = '0123456789xX '  # Digits, space, and hyphen for hazard plates
        return OCR(allowed_chars=allowed_chars)
    
    def get_bbox_color(self) -> str:
        """Return bbox color (e.g., 'Red', 'Green')."""
        return "orange"
    
    def get_bbox_label(self) -> str:
        """Return bbox label text (e.g., 'truck', 'car')."""
        return "Hazard Plate"

    def get_yolo_model_path(self) -> str:
        """Return path to hazard plate YOLO model."""
        return "/agentC/data/hazard_plate_model.pt"

    def get_annotated_frames_bucket(self) -> str:
        """Return bucket name for annotated frames."""
        return f"hz-annotated-frames-gate-{self.gate_id}"

    def get_crops_bucket(self) -> str:
        """Return bucket name for crops."""
        return f"hz-crops-gate-{self.gate_id}"

    def get_consume_topic(self) -> str:
        """Return Kafka topic to consume truck detection events."""
        return f"truck-detected-{self.gate_id}"

    def get_produce_topic(self) -> str:
        """Return Kafka topic to produce hazard plate results."""
        return f"hz-results-{self.gate_id}"

    def get_object_type(self) -> str:
        """Return detected object type name."""
        return "hazard plate"

    def is_valid_detection(self, crop, confidence: float, box_index: int) -> bool:
        """
        Validate hazard plate detection.
        All detections are accepted (no classification filtering for hazard plates).
        """
        self.logger.debug(f"Crop {box_index} accepted as HAZARD_PLATE")
        self.hazards_detected.inc()
        self.ocr_confidence.observe(confidence)
        return True

    def _build_message_for_detection(self, text: str, confidence: float, crop_url: Optional[str]) -> Message:
        """Build hazard plate results message with UN and Kemler codes."""
        un, kemler = self._parse_detection_result(text)
        return KafkaMessageProto.hazard_plate_result(
            un=un,
            kemler=kemler,
            crop_url=crop_url if crop_url else "",
            confidence=confidence
        )

    def init_metrics(self):
        """Initialize Prometheus metrics for Agent C."""
        self.inference_latency = Histogram(
            'agent_c_inference_latency_seconds', 
            'Time spent running YOLO (Hazmat) inference',
            buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0]
        )
        self.frames_processed_metric = Counter(
            'agent_c_frames_processed_total', 
            'Total number of frames processed by Agent C'
        )
        self.hazards_detected = Counter(
            'agent_c_hazards_detected_total', 
            'Total number of hazardous plates detected'
        )
        self.ocr_confidence = Histogram(
            'agent_c_hazard_confidence', 
            'Confidence score of hazard detection',
            buckets=[0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99]
        )

    # ========================================================================
    # Agent C specific overrides
    # ========================================================================

    def _parse_detection_result(self, text: str) -> tuple[str, str]:
        """
        Parse hazard plate text into UN and Kemler codes.
        Expected format: "KEMLER UN" (e.g., "33 1203")
        
        Returns:
            Tuple of (un, kemler)
        """
        parts = text.split(" ")
        self.logger.debug(f"Parts: {parts}")
        
        if len(parts) == 2:
            kemler = parts[0]
            un = parts[1]
        else:
            un = "N/A"
            kemler = "N/A"
        
        return un, kemler