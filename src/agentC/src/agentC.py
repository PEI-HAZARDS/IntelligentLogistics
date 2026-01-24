from shared.base_agent import BaseAgent
from shared.plate_classifier import PlateClassifier

import os
from typing import Dict, Any
from prometheus_client import Counter, Histogram # type: ignore


class AgentC(BaseAgent):
    """
    Agent C: Hazard Plate Detection
    
    Extends BaseAgent to:
    - Detect hazard plates using YOLO
    - Extract UN and Kemler codes using OCR with consensus algorithm
    - Publish hazard plate results to Kafka
    """

    def __init__(self):
        """Initialize Agent C with hazard plate detection capabilities."""
        # Call parent constructor
        super().__init__()

    # ========================================================================
    # Required abstract method implementations
    # ========================================================================

    def get_agent_name(self) -> str:
        """Return agent identifier."""
        return "AgentC"

    def get_yolo_model_path(self) -> str:
        """Return path to hazard plate YOLO model."""
        return "/agentC/data/hazard_plate_model.pt"

    def get_storage_bucket(self) -> str:
        """Return MinIO bucket for hazard plate crops."""
        return os.getenv("BUCKET_NAME", "hz-crops")

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
        self.logger.info(f"[AgentC] Crop {box_index} accepted as HAZARD_PLATE")
        self.hazards_detected.inc()
        self.hazard_confidence.observe(confidence)
        return True

    def build_publish_payload(self, truck_id: str, detection_result: Dict[str, Any], 
                              confidence: float, crop_url: str | None) -> Dict[str, Any]:
        """Build Kafka message payload for hazard plate results with UN and Kemler codes."""
        return {
            "un": detection_result.get("un", "N/A"),
            "kemler": detection_result.get("kemler", "N/A"),
            "confidence": float(confidence if confidence is not None else 0.0),
            "cropUrl": crop_url
        }

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
        self.hazard_confidence = Histogram(
            'agent_c_hazard_confidence', 
            'Confidence score of hazard detection',
            buckets=[0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99]
        )

    # ========================================================================
    # Agent C specific overrides
    # ========================================================================

    def _run_yolo_detection(self, frame):
        """Override to include inference latency metric."""
        self.logger.info("[AgentC] YOLO (HZ) running…")
        with self.inference_latency.time():
            results = self.yolo.detect(frame)
        
        self.frames_processed_metric.inc()

        if not results:
            self.logger.debug("[AgentC] YOLO did not return a result for this frame.")
            return None

        if not self.yolo.object_found(results):
            self.logger.info("[AgentC] No hazard plate detected for this frame.")
            return None

        boxes = self.yolo.get_boxes(results)
        self.logger.info(f"[AgentC] {len(boxes)} hazard plates detected.")
        return boxes

    def _parse_detection_result(self, text: str) -> Dict[str, Any]:
        """
        Parse hazard plate text into UN and Kemler codes.
        Expected format: "KEMLER UN" (e.g., "33 1203")
        """
        parts = text.split(" ")
        self.logger.info(f"[AgentC] Parts: {parts}")
        
        if len(parts) == 2:
            kemler = parts[0]
            un = parts[1]
        else:
            un = "N/A"
            kemler = "N/A"
        
        return {"un": un, "kemler": kemler, "text": text}

    def _publish_empty_result(self, truck_id: str):
        """Publish empty result when no hazard plate detected."""
        self._publish_detection(truck_id, {"un": "N/A", "kemler": "N/A"}, -1, None)
