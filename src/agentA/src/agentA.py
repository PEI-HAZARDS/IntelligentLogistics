from shared.src.stream_manager import StreamManager
from shared.src.object_detector import ObjectDetector
from shared.src.bounding_box_drawer import BoundingBoxDrawer
from shared.src.image_storage import ImageStorage
from shared.src.kafka_wrapper import KafkaProducerWrapper
import os
import time
import uuid
from confluent_kafka import Producer, KafkaError  # type: ignore
from typing import Optional
import json
import logging
from prometheus_client import start_http_server, Counter, Histogram, Gauge #type: ignore

# Test Jenkins deploy

# --- Configuration ---
# Load environment variables or fallback to default network settings
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "10.255.32.143:9092")
NGINX_RTMP_HOST = os.getenv("NGINX_RTMP_HOST", "10.255.32.80")
NGINX_RTMP_PORT = os.getenv("NGINX_RTMP_PORT", "1935")
GATE_ID = os.getenv("GATE_ID", "1")
STREAM_LOW = f"rtmp://{NGINX_RTMP_HOST}:{NGINX_RTMP_PORT}/streams_low/gate{GATE_ID}"

# --- Operational Constants ---
MESSAGE_INTERVAL = 35   # Throttle: Limit alerts to one every 35 seconds
KAFKA_TOPIC = f"truck-detected-{GATE_ID}"

# --- MinIO Config ---
MINIO_HOST = os.getenv("MINIO_HOST", "10.255.32.82")
MINIO_PORT = os.getenv("MINIO_PORT", "9000")
MINIO_CONFIG = {
        "endpoint": f"{MINIO_HOST}:{MINIO_PORT}",
        "access_key": os.getenv("ACCESS_KEY"),
        "secret_key": os.getenv("SECRET_KEY"),
        "secure": False
    }

BUCKET_NAME = f"trk-annotated-frames-gate-{GATE_ID}"

logger = logging.getLogger("AgentA")

class AgentA:
    """
    Agent A:
    - Continuously monitors a low-quality stream.
    - Detects trucks with YOLO.
    - Publishes 'truck-detected-GATE_ID' events to Kafka
    """

    def __init__(
        self,
        object_detector: Optional[ObjectDetector] = None,
        stream_manager: Optional[StreamManager] = None,
        kafka_producer: Optional[KafkaProducerWrapper] = None,
        image_storage: Optional[ImageStorage] = None,
        drawer: Optional[BoundingBoxDrawer] = None,
    ):
        # Initialize dependencies (use injected or default)
        self.yolo = object_detector or ObjectDetector("/agentA/data/truck_model.pt", 7)
        self.drawer = drawer or BoundingBoxDrawer(color="green", thickness=2, label="truck")
        self.image_storage = image_storage or ImageStorage(MINIO_CONFIG, BUCKET_NAME)
        self.stream_manager = stream_manager or StreamManager(STREAM_LOW)
        self.kafka_producer = kafka_producer or KafkaProducerWrapper(KAFKA_BOOTSTRAP)
        
        self.running = True
        self.last_message_time = 0
        
        # --- Prometheus Metrics ---
        self.inference_latency = Histogram(
            'agent_a_inference_latency_seconds', 
            'Time spent running YOLO inference',
            buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0]
        )
        self.frames_processed = Counter(
            'agent_a_frames_processed_total', 
            'Total number of frames processed by Agent A'
        )
        self.trucks_detected = Counter(
            'agent_a_trucks_detected_total', 
            'Total number of trucks detected'
        )
        self.detection_confidence = Histogram(
            'agent_a_detection_confidence', 
            'Confidence score of detected trucks',
            buckets=[0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99]
        )
        
        # Start Prometheus metrics server
        # logger.info("[AgentA] Starting Prometheus metrics server on port 8000")
        # start_http_server(8000) - Started in init.py

    def _publish_truck_detected(self, max_conf: float, num_boxes: int, truck_id: Optional[str] = None):
        """Publishes the 'truck-detected-GATE_ID' event to Kafka."""

        # Generate unique ID and timestamp for the event
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Construct JSON payload
        payload = {
            "timestamp": timestamp,
            "confidence": float(max_conf),
            "detections": int(num_boxes)
        }

        # Send asynchronously to Kafka
        self.kafka_producer.produce(KAFKA_TOPIC, payload, headers={"truckId": truck_id})
    
    def _process_detection(self, frame):
        """
        Process a frame for truck detection and publish to Kafka if detected.
        
        Args:
            frame: Video frame to process
        """
        # Run YOLO inference
        logger.debug("[AgentA] Frame captured, running truck detection…")
        with self.inference_latency.time():
            results = self.yolo.detect(frame)
        
        self.frames_processed.inc()

        if results is None:
            logger.warning("[AgentA] YOLO model returned no results (None).")
            return

        # Check for positive detection
        if not self.yolo.object_found(results):
            logger.debug("[AgentA] No truck detected in this frame.")
            return
        
        now = time.time()
        elapsed = now - self.last_message_time
        truck_id = "TRK" + str(uuid.uuid4())[:8]

        # Check throttling interval (Debounce)
        if elapsed < MESSAGE_INTERVAL:
            logger.info(f"[AgentA] Truck detected, but waiting {MESSAGE_INTERVAL - elapsed:.1f}s before next message.")
            return

        # Extract stats and publish to Kafka
        try:
            boxes = self.yolo.get_boxes(results)  # [x1,y1,x2,y2,conf]
            num_boxes = len(boxes)
            max_conf = max((b[4] for b in boxes), default=0.0)

            # Draw detected boxes on the frame (labelled)
            try:
                frame = self.drawer.draw_box(frame, boxes)
                self.image_storage.upload_memory_image(frame, f"{truck_id}_{int(time.time())}.jpg")
            except Exception as e:
                logger.exception(f"[AgentA] Error drawing boxes: {e}")

            # Record metrics
            self.trucks_detected.inc(num_boxes)
            self.detection_confidence.observe(max_conf)

            self.last_message_time = now
            self._publish_truck_detected(max_conf, num_boxes, truck_id)

        except Exception as e:
            logger.exception(f"[AgentA] Error preparing Kafka event: {e}")

    def _loop(self):
        """Main loop for Agent A."""

        logger.info(f"[AgentA] Starting Agent A main loop (stream={STREAM_LOW}, kafka bootstrap={KAFKA_BOOTSTRAP}) …")

        # Main processing cycle
        while self.running:
            try:
                frame = self.stream_manager.read()

                if frame is None:
                    time.sleep(0.1) 
                    continue
                
                # Process frame for truck detection
                self._process_detection(frame)

            except Exception as e:
                logger.exception(f"[AgentA] Exception during detection loop: {e}")
                time.sleep(1)

        # Cleanup: Release resources
        self.stream_manager.release()
        self.kafka_producer.flush()

    def stop(self):
        """Gracefully stop Agent A."""

        logger.info("[AgentA] Stopping Agent A…")
        self.running = False
