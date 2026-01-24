from shared.base_agent import BaseAgent
from shared.plate_classifier import PlateClassifier
from shared.image_storage import ImageStorage

import os
from typing import Dict, Any
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

    def __init__(self):
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
        
        # Call parent constructor
        super().__init__()

    # ========================================================================
    # Required abstract method implementations
    # ========================================================================

    def get_agent_name(self) -> str:
        """Return agent identifier."""
        return "AgentB"

    def get_yolo_model_path(self) -> str:
        """Return path to license plate YOLO model."""
        return "/agentB/data/license_plate_model.pt"

    def get_storage_bucket(self) -> str:
        """Return MinIO bucket for license plate crops."""
        return os.getenv("BUCKET_NAME", "lp-crops")

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

    def build_publish_payload(self, truck_id: str, detection_result: Dict[str, Any], 
                              confidence: float, crop_url: str | None) -> Dict[str, Any]:
        """Build Kafka message payload for license plate results."""
        return {
            "licensePlate": detection_result["text"],
            "confidence": float(confidence if confidence is not None else 0.0),
            "cropUrl": crop_url
        }

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

    # ========================================================================
    # Agent B specific overrides
    # ========================================================================

    def _run_yolo_detection(self, frame):
        """Override to include inference latency metric."""
        self.logger.info("[AgentB] YOLO (LP) running…")
        with self.inference_latency.time():
            results = self.yolo.detect(frame)
        
        self.frames_processed_metric.inc()

        if not results:
            self.logger.debug("[AgentB] YOLO did not return a result for this frame.")
            return None

        if not self.yolo.object_found(results):
            self.logger.info("[AgentB] No license plate detected for this frame.")
            return None

        boxes = self.yolo.get_boxes(results)
        self.logger.info(f"[AgentB] {len(boxes)} license plates detected.")
        return boxes

    def _process_ocr_result(self, crop, crop_index: int):
        """Override to include OCR confidence metric."""
        self.logger.info("[AgentB] OCR extracting text…")
        text, ocr_conf = self.ocr._extract_text(crop)

        if not text or ocr_conf <= 0.0:
            self.logger.debug(f"[AgentB] OCR returned no valid text for crop {crop_index}")
            return None

        self.logger.info(f"[AgentB] OCR: '{text}' (conf={ocr_conf:.2f})")
        self.ocr_confidence.observe(ocr_conf)

        # Store candidate crop
        text_normalized = text.upper().replace("-", "")
        self.candidate_crops.append({
            "crop": crop.copy(),
            "text": text_normalized,
            "confidence": ocr_conf
        })
        self.logger.debug(f"[AgentB] Added candidate crop: '{text_normalized}' (conf={ocr_conf:.2f})")

        self._add_to_consensus(text, ocr_conf)

        if self._check_full_consensus():
            final_text = self._build_final_text()
            self.logger.info(f"[AgentB] Full consensus achieved: '{final_text}'")
            best_crop = self._select_best_crop(final_text)
            return final_text, 1.0, best_crop

        return None

    def _parse_detection_result(self, text: str) -> Dict[str, Any]:
        """Parse license plate text (simple pass-through)."""
        return {"text": text}

    def _publish_empty_result(self, truck_id: str):
        """Publish empty result when no license plate detected."""
        self._publish_detection(truck_id, {"text": "N/A"}, -1, None)
