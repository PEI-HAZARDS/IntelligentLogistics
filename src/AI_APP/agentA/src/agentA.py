from AI_APP.shared.src.stream_manager import StreamManager
from AI_APP.shared.src.object_detector import ObjectDetector
from AI_APP.shared.src.bounding_box_drawer import BoundingBoxDrawer, Box
from AI_APP.shared.src.image_storage import ImageStorage
from shared.src.kafka_wrapper import KafkaProducerWrapper, KafkaConsumerWrapper
from shared.src.kafka_protocol import KafkaMessageProto, KafkaTopicFactory
import time
import uuid
from typing import Optional, cast, List
import logging
from prometheus_client import Counter, Histogram #type: ignore
from pydantic_settings import BaseSettings # type: ignore
from pydantic import Field # type: ignore


logger = logging.getLogger("AgentA")

# Module level — registered once per process
_INFERENCE_LATENCY = Histogram(
    'agent_a_inference_latency_seconds',
    'Time spent running YOLO inference',
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0]
)
_FRAMES_PROCESSED = Counter('agent_a_frames_processed_total', 'Total number of frames processed by Agent A')
_TRUCKS_DETECTED  = Counter('agent_a_trucks_detected_total', 'Total number of trucks detected by Agent A')
_DETECTION_CONF   = Histogram('agent_a_detection_confidence', 'Confidence score of detected trucks', buckets=[0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99])

class AgentAConfig(BaseSettings):
    # Kafka
    kafka_bootstrap: str = Field(default="10.255.32.143:9092")
    
    # NGINX RTMP
    nginx_host: str = Field(default="10.255.32.56")
    nginx_port: int = Field(default=1935)
    
    # MinIO
    minio_host: str = Field(default="10.255.32.82")
    minio_port: int = Field(default=9000)
    minio_user: str = Field(...) # The '...' means this is strictly required
    minio_password: str = Field(...) # The '...' means this is strictly required
    minio_secure: bool = Field(default=False)
    
    # App Operational Config
    gate_id: str = Field(default="1")
    models_path: str = Field(default="/app/AI_APP/agentA/data")
    decision_timeout: int = Field(default=60)
    
    # Use properties to dynamically construct dependent values
    @property
    def stream_low(self) -> str:
        return f"rtmp://{self.nginx_host}:{self.nginx_port}/streams_low/gate{self.gate_id}"
        
    @property
    def minio_bucket_name(self) -> str:
        return f"agenta-{self.gate_id}"
    
    @property
    def minio_config(self) -> dict:
        return {
            "endpoint": f"{self.minio_host}:{self.minio_port}",
            "access_key": self.minio_user,
            "secret_key": self.minio_password,
            "secure": self.minio_secure
        }
    
    @property
    def kafka_topic_produce(self) -> str:
        return KafkaTopicFactory.truck_detected(self.gate_id)
    
    @property
    def kafka_topic_consume(self) -> List[str]:
        return [KafkaTopicFactory.reset_agent_a(self.gate_id)]

class AgentA:
    """
    Agent A:
    - Continuously monitors a low-quality stream.
    - Detects trucks with YOLO.
    - Publishes 'truck-detected-GATE_ID' events to Kafka
    """

    def __init__(
        self,
        config: AgentAConfig,
        object_detector: Optional[ObjectDetector] = None,
        stream_manager: Optional[StreamManager] = None,
        kafka_producer: Optional[KafkaProducerWrapper] = None,
        kafka_consumer: Optional[KafkaConsumerWrapper] = None,
        image_storage: Optional[ImageStorage] = None,
        drawer: Optional[BoundingBoxDrawer] = None,
    ):
        self.config = config
        
        try:
            self.yolo = object_detector or ObjectDetector(config.models_path + "/truck_model.pt", 7)
        except FileNotFoundError as e:
            logger.critical(f"Model file not found — cannot start AgentA: {e}")
            raise SystemExit(1) from e
        except RuntimeError as e:
            logger.critical(f"Failed to load YOLO model — cannot start AgentA: {e}")
            raise SystemExit(1) from e
        
        self.drawer = drawer or BoundingBoxDrawer(color="green", thickness=2, label="truck")
        self.image_storage = image_storage or ImageStorage(config.minio_config, config.minio_bucket_name)
        self.stream_manager = stream_manager or StreamManager(config.stream_low)
        self.kafka_producer = kafka_producer or KafkaProducerWrapper(config.kafka_bootstrap)
        self.kafka_consumer = kafka_consumer or KafkaConsumerWrapper(self.config.kafka_bootstrap, f"agenta-{self.config.gate_id}-group", self.config.kafka_topic_consume)
        
        self.stream_manager.connect()
        self.running = True
        self.awaiting_reset = False
        self.last_message_time = 0
        
        # --- Prometheus Metrics ---
        self.inference_latency   = _INFERENCE_LATENCY
        self.frames_processed    = _FRAMES_PROCESSED
        self.trucks_detected     = _TRUCKS_DETECTED
        self.detection_confidence = _DETECTION_CONF
        
    def start(self) -> None:
        """Main loop for Agent A."""

        logger.info(f"Starting Agent A main loop (stream={self.config.stream_low}, kafka bootstrap={self.config.kafka_bootstrap}) …")

        # Main processing cycle
        while self.running:
            now = time.time()
            try:
                if self.awaiting_reset and (now - self.last_message_time) <= self.config.decision_timeout:
                    # Wait for reset-agentA before resuming detection
                    topic, message_obj, truck_id = self.kafka_consumer.consume_typed_message(timeout=0.1)
                    if topic is None:
                        # No message received (timeout)
                        if int(now) % 10 == 0:
                            logger.info("Waiting for reset signal from V_Brain...")
                        continue
                        
                    logger.info(f"Reset received (reason={message_obj.reason}), resuming detection...")
                
                if now - self.last_message_time > self.config.decision_timeout:
                        logger.info("Reset timeout exceeded while waiting for decision, resuming detection anyway...")
                
                self._process_detection()

                self.awaiting_reset = True   # truck detected — wait for reset before next detection
            except Exception as e:
                logger.exception(f"Exception during detection loop: {e}")
                time.sleep(1)

    def stop(self) -> None:
        """Gracefully stop Agent A."""
        logger.info("Stopping Agent A…")
        self.running = False
        self._cleanup()
        
    
    def _cleanup(self) -> None:
        """Release resources and perform cleanup."""
        logger.info("Cleaning up resources for Agent A…")
        self.stream_manager.release()
        self.kafka_producer.flush()
        self.kafka_producer.close()
    
    def _process_detection(self) -> None:
        """
        Continuously capture and process frames for truck detection.
        Returns only when a truck has been successfully detected and the Kafka event is published.
        """
        while self.running:
            # Wait until stream is actually ready
            frame = None
            while frame is None and self.running:
                frame = self.stream_manager.read()
                if frame is None:
                    time.sleep(0.1)
            
            if not self.running or frame is None:
                break

            # Run YOLO inference
            logger.debug("Frame captured, running truck detection…")
            try:
                with self.inference_latency.time():
                    results = self.yolo.detect(frame)
                
                self.frames_processed.inc()

                if results is None:
                    logger.warning("YOLO model returned no results (None).")
                    continue

                # Check for positive detection
                if not self.yolo.object_found(results):
                    logger.debug("No truck detected in this frame.")
                    continue
                
                truck_id = "TRK" + str(uuid.uuid4())[:8]
                boxes = self.yolo.get_boxes(results)  # [x1,y1,x2,y2,conf]
                num_boxes = len(boxes)
                max_conf = max((b[4] for b in boxes), default=0.0)

                # Draw detected boxes on the frame (labelled)
                try:
                    frame = self.drawer.draw_box(frame, cast(List[Box], boxes))
                    self.image_storage.upload_memory_image(frame, f"{truck_id}_{int(time.time())}.jpg", image_type="annotated_frames")
                except Exception as e:
                    logger.exception(f"Error drawing boxes: {e}")

                # Record metrics
                self.trucks_detected.inc(num_boxes)
                self.detection_confidence.observe(max_conf)

                message = KafkaMessageProto.truck_detected(confidence=max_conf, num_detections=num_boxes)
                self.kafka_producer.produce(
                    topic=self.config.kafka_topic_produce,
                    data=message.to_dict(),
                    headers={"truck_id": truck_id}
                )
                
                # Force delivery callbacks to process immediately so we see the log
                self.kafka_producer.flush(timeout=1)
                self.last_message_time = time.time()
                logger.info(f"Truck detected! truck_id={truck_id}, confidence={max_conf:.2f}, num_detections={num_boxes}.")

                # Truck detected and message sent; return to the main loop
                return

            except Exception as e:
                logger.exception(f"Error preparing Kafka event: {e}")
                time.sleep(0.1)


