from abc import ABC, abstractmethod
import time
import numpy as np # type: ignore
from typing import Any, Dict, List, Optional, Tuple, cast

from pydantic_settings import BaseSettings # type: ignore
from pydantic import Field, SecretStr # type: ignore
from AI_APP.shared.src.stream_manager import StreamManager
from AI_APP.shared.src.object_detector import ObjectDetector
from AI_APP.shared.src.paddle_ocr import OCR
from AI_APP.shared.src.image_storage import ImageStorage
from AI_APP.shared.src.plate_classifier import PlateClassifier
from AI_APP.shared.src.bounding_box_drawer import BoundingBoxDrawer, Box
from shared.src.kafka_wrapper import KafkaProducerWrapper, KafkaConsumerWrapper
from AI_APP.shared.src.consensus_algorithm import ConsensusAlgorithm
from shared.src.kafka_protocol import Message
from queue import Queue, Empty
import logging

class BaseAgentConfig(BaseSettings):
    # Kafka
    kafka_bootstrap: str = Field(default="10.255.32.143:9092")

    # MediaMTX RTSP (low-latency UDP stream consumption)
    mediamtx_host: str = Field(default="10.255.32.56")
    mediamtx_port: int = Field(default=8554)

    # MinIO
    minio_host: str = Field(default="10.255.32.82")
    minio_port: int = Field(default=9000)
    minio_user: str = Field(...)
    minio_password: SecretStr = Field(...)
    minio_secure: bool = Field(default=False)

    # App Operational Config
    gate_id: str = Field(default="1")
    models_path: str = Field(default="/app/AI_APP")

    # Detection parameters
    max_frames: int = Field(default=40)
    min_detection_confidence: float = Field(default=0.4)
    frames_batch_size: int = Field(default=5)

    # Use properties to dynamically construct dependent values
    @property
    def stream_url(self) -> str:
        return f"rtsp://{self.mediamtx_host}:{self.mediamtx_port}/streams_high/gate{self.gate_id}"

    @property
    def minio_config(self) -> Dict[str, Any]:
        return {
            "endpoint": f"{self.minio_host}:{self.minio_port}",
            "access_key": self.minio_user,
            "secret_key": self.minio_password.get_secret_value(),
            "secure": self.minio_secure,
        }

class BaseAgent(ABC):
    """
    Base agent class that implements common detection and consensus logic.
    
    Child classes must implement:
    - get_agent_name(): Return agent identifier
    - initialize_ocr(): Initialize and return OCR instance
    - get_bbox_color(): Return bounding box colour
    - get_bbox_label(): Return bounding box label
    - get_yolo_model_path(): Return path to YOLO model
    - get_bucket(): Return MinIO bucket name
    - get_consume_topic(): Return Kafka topic to consume from
    - get_produce_topic(): Return Kafka topic to produce to
    - is_valid_detection(): Validate a detection box
    - _build_message_for_detection(): Build the Kafka message for a detection result
    - init_metrics(): Initialize Prometheus metrics
    - get_object_type(): Return detected object type name for logging
    - get_detection_metric(): Return the single Prometheus counter to increment per detected box
    """

    def __init__(
        self,
        config: Optional[BaseAgentConfig] = None,
        stream_manager: Optional[StreamManager] = None,
        object_detector: Optional[ObjectDetector] = None,
        ocr: Optional[OCR] = None,
        classifier: Optional[PlateClassifier] = None,
        drawer: Optional[BoundingBoxDrawer] = None,
        annotated_frames_storage: Optional[ImageStorage] = None,
        crop_storage: Optional[ImageStorage] = None,
        kafka_producer: Optional[KafkaProducerWrapper] = None,
        kafka_consumer: Optional[KafkaConsumerWrapper] = None,
        consensus_algorithm: Optional[ConsensusAlgorithm] = None,
    ) -> None:
        """
        Initialize base agent with common components.
        
        Args:
            config: Optional BaseAgentConfig instance (loaded from env if not provided)
            stream_manager: Optional StreamManager instance (for testing)
            object_detector: Optional ObjectDetector instance (for testing)
            ocr: Optional OCR instance (for testing)
            classifier: Optional PlateClassifier instance (for testing)
            drawer: Optional BoundingBoxDrawer instance (for testing)
            annotated_frames_storage: Optional ImageStorage instance (for testing)
            crop_storage: Optional ImageStorage instance (for testing)
            kafka_producer: Optional KafkaProducerWrapper instance (for testing)
            kafka_consumer: Optional KafkaConsumerWrapper instance (for testing)
            consensus_algorithm: Optional ConsensusAlgorithm instance (for testing)
        """
        # Agent identification
        self.agent_name = self.get_agent_name()
        self.logger = logging.getLogger(self.agent_name)

        # Load configuration
        self.config = config or BaseAgentConfig()
        
        # Initialize models - use provided dependencies or create defaults
        self.yolo = object_detector or ObjectDetector(self.get_yolo_model_path())
        self.ocr = ocr or self.initialize_ocr()
        self.classifier = classifier or PlateClassifier()
        self.drawer = drawer or BoundingBoxDrawer(color=self.get_bbox_color(), thickness=2, label=self.get_bbox_label())
        self.image_storage = annotated_frames_storage or ImageStorage(self.config.minio_config, self.get_bucket())
        self.crop_storage = crop_storage or self.image_storage
        self.stream_manager = stream_manager or StreamManager(self.config.stream_url)
        self.kafka_producer = kafka_producer or KafkaProducerWrapper(self.config.kafka_bootstrap)
        self.kafka_consumer = kafka_consumer or KafkaConsumerWrapper(self.config.kafka_bootstrap, f"{self.agent_name.lower()}-{self.config.gate_id}-group", [self.get_consume_topic()])
        self.consensus_algorithm = consensus_algorithm or ConsensusAlgorithm()
        
        # Runtime state
        self.running = True
        self.frames_queue = Queue()
        self.truck_id = ""
        
        # Metrics — subclasses set real values inside init_metrics();
        # base class guarantees these attributes always exist.
        self.frames_processed_metric: Optional[object] = None
        self.inference_latency: Optional[object] = None
        self.ocr_confidence: Optional[object] = None
        self.init_metrics()
        self.frames_processed = 0

        self.logger.info(f"Initialized {self.agent_name}")

    # ========================================================================
    # Abstract methods - must be implemented by child classes
    # ========================================================================

    @abstractmethod
    def get_agent_name(self) -> str:
        """Return agent identifier (e.g., 'AgentB', 'AgentC')."""
        pass
    
    @abstractmethod
    def initialize_ocr(self) -> OCR:
        """Initialize and return OCR instance."""
        pass
    
    @abstractmethod
    def get_bbox_color(self) -> str:
        """Return bbox color (e.g., 'Red', 'Green')."""
        pass
    
    @abstractmethod
    def get_bbox_label(self) -> str:
        """Return label color (e.g., 'truck', 'car')."""
        pass

    @abstractmethod
    def get_yolo_model_path(self) -> str:
        """Return path to YOLO model file."""
        pass

    @abstractmethod
    def get_bucket(self) -> str:
        """Return bucket name."""
        pass

    @abstractmethod
    def get_consume_topic(self) -> str:
        """Return Kafka topic to consume from."""
        pass

    @abstractmethod
    def get_produce_topic(self) -> str:
        """Return Kafka topic to produce to."""
        pass

    @abstractmethod
    def is_valid_detection(self, crop: np.ndarray, confidence: float, box_index: int) -> bool:
        """
        Validate detection box (e.g., check plate classification).
        
        Args:
            crop: Cropped image
            confidence: Detection confidence
            box_index: Box index for logging
            
        Returns:
            True if detection is valid, False otherwise
        """
        pass

    @abstractmethod
    def _build_message_for_detection(self, text: str, confidence: float, crop_url: Optional[str]) -> Message:
        """
        Build the appropriate message for this agent's detection result.
        
        This method bridges between the generic detection pipeline (which returns text)
        and the agent-specific message format.
        
        Args:
            text: Detected text from OCR
            confidence: Detection confidence
            crop_url: MinIO crop URL
            
        Returns:
            Message object appropriate for this agent
        """
        pass

    @abstractmethod
    def init_metrics(self) -> None:
        """Initialize Prometheus metrics specific to this agent."""
        pass

    @abstractmethod
    def get_object_type(self) -> str:
        """Return detected object type name (e.g., 'license plate', 'hazard plate')."""
        pass

    @abstractmethod
    def get_detection_metric(self) -> Optional[object]:
        """Return the single Prometheus counter to increment per detected box, or None."""
        pass

    # ========================================================================
    # Template methods - common behavior with extension points
    # ========================================================================
    
    def start(self) -> None:
        """Main loop for agent."""

        self.logger.info(f"Starting {self.agent_name} main loop (stream={self.config.stream_url}, kafka bootstrap={self.config.kafka_bootstrap}) …")
        
        # Clear any stale messages on startup
        self.kafka_consumer.clear_stale_messages()
        
        # Main processing cycle
        while self.running:
            try:
                _, message_obj, truck_id = self.kafka_consumer.consume_typed_message(timeout=0.1)
                
                # No relevant message received, continue to next iteration
                if truck_id is None:
                    continue
                
                self.truck_id = truck_id
                self.logger.info(f"Received message for truck_id={truck_id}, processing detection...")
                
                # Process frame for truck detection
                self._process_message(message_obj)

            except Exception as e:
                self.logger.exception(f"Exception during detection loop: {e}")
                time.sleep(1)
    
    def stop(self) -> None:
        """Gracefully stop the agent."""
        self.logger.info(f"Stopping {self.agent_name}…")
        self.running = False
        self._cleanup()
    
    def _process_message(self, message_obj: Any) -> None:
        """
        Orchestrate a full detection cycle for one incoming Kafka message.

        Runs the detection pipeline, uploads the best crop to MinIO via
        ``self.crop_storage``, builds the agent-specific result message, and
        publishes it to Kafka.  Always produces a message (text defaults to
        'N/A' when no detection is made) so downstream consumers are not
        left waiting.

        Args:
            message_obj: Typed message object received from the Kafka consumer.
        """
        self.logger.info(f"Processing truck: {self.truck_id}")
        
        self.logger.info("Connecting to video stream…")
        self.stream_manager.connect()
    
        # Run detection pipeline and always use the returned crop
        text, confidence, crop = self.process_detection()  
        
        self.logger.info("Releasing to video stream…")
        self.stream_manager.release()
        
        crop_url = None
        if crop is not None:
            # Always upload the returned crop, even if text is N/A
            try:
                crop_url = self.crop_storage.upload_memory_image(
                    crop, 
                    f"{self.truck_id}_{int(time.time())}.jpg", 
                    image_type="crops"
                )
                self.logger.debug("Crop uploaded")
            except Exception as e:
                self.logger.error(f"Crop upload error: {e}")
        else:
            self.logger.debug("No crop available")

        confidence = confidence if confidence is not None else 0.0
        if not text:
            self.logger.debug("No text result, using N/A")
            text = "N/A"

        # Build message based on agent type
        message = self._build_message_for_detection(text, confidence, crop_url)

        # Publish results
        self._publish_detection(message)

        # Clear frames queue for next detection
        self._clear_frames_queue()
    
    def process_detection(self) -> Tuple[Optional[str], Optional[float], Optional[Any]]:
        """
        Main detection pipeline.
        
        Returns:
            tuple: (text, confidence, crop_image) or (None, None, None)
        """
        self.logger.info("Starting detection pipeline")
        self.consensus_algorithm.reset()
        self.frames_processed = 0

        while self._should_continue_processing():
            frame = self._get_next_frame()
            if frame is None:
                return None, None, None
            
            if self.frames_processed_metric:
                self.frames_processed_metric.inc() # type: ignore
            
            self.frames_processed += 1
            self.logger.debug(f"Frame {self.frames_processed}/{int(self.config.max_frames)} obtained, running detection…")

            result = self._process_frame(frame)
            if result:
                text, conf, crop = result
                self._clear_frames_queue()
                return text, conf, crop

        if self.frames_processed >= self.config.max_frames:
            self.logger.info(f"Frame limit reached ({int(self.config.max_frames)}), using partial result")

        return self.consensus_algorithm.get_best_partial_result(self.get_object_type())

    def _should_continue_processing(self) -> bool:
        """Check if frame processing should continue."""
        return self.running and not self.consensus_algorithm.consensus_reached and self.frames_processed < self.config.max_frames

    def _get_next_frame(self) -> Optional[np.ndarray]:
        if self.frames_queue.empty():
            self._add_frames_queue(self.config.frames_batch_size)
        try:
            return self.frames_queue.get_nowait()
        except Empty:
            self.logger.debug("No frame available after capture attempt")
        return None
    
    def _add_frames_queue(self, num_frames: int = 30) -> None:
        """
        Capture frames from RTMP/RTSP stream with automatic reconnection.
        
        Args:
            num_frames: Number of frames to capture
        """
        self.logger.debug(f"Reading {num_frames} frames")

        captured = 0
        while captured < num_frames and self.running:
            try:
                frame = self.stream_manager.read()
                if frame is not None:
                    self.frames_queue.put(frame)
                    captured += 1
                    self.logger.debug(f"Captured {captured}/{num_frames}")
                else:
                    time.sleep(0.1)
            
            except Exception as e:
                self.logger.warning(f"Frame capture error: {e}")
                time.sleep(0.2)
    
    def _process_frame(self, frame: np.ndarray) -> Optional[Tuple[str, float, np.ndarray]]:
        """
        Process a single video frame.
        
        Returns:
            (text, conf, crop) if consensus is reached, else None
        """
        try:
            boxes = self._run_yolo_inference(frame)
            if boxes is None:
                return None

            for i, box in enumerate(boxes, start=1):
                crop, yolo_conf = self._extract_crop(box, frame, i)
                if crop is None or yolo_conf is None:
                    continue

                # Always add valid crops to candidates (even if OCR fails)
                # This ensures we have crops available for fallback selection
                self.consensus_algorithm.add_candidate_crop(crop.copy(), "", yolo_conf, is_fallback=True)

                try:
                    result = self._process_ocr_result(crop)
                    if result:
                        return result
                except Exception as e:
                    self.logger.warning(f"OCR failure on crop {i}: {e}")
                    continue  # process remaining crops instead of aborting

        except Exception as e:
            self.logger.error(f"Frame processing error: {e}")
            raise

        return None
    
    def _run_yolo_inference(self, frame: np.ndarray) -> Optional[List[Any]]:
        """Run YOLO detection on frame."""
        self.logger.info("Running YOLO detection...")
        
        if self.inference_latency:
            with self.inference_latency.time(): # type: ignore
                results = self.yolo.detect(frame)
        else:
            results = self.yolo.detect(frame)

        if not results:
            self.logger.debug("No YOLO result")
            return None

        if not self.yolo.object_found(results):
            self.logger.info(f"No {self.get_object_type()} detected")
            return None

        boxes = self.yolo.get_boxes(results)

        try:
            annotated_frame = frame.copy()
            annotated_frame = self.drawer.draw_box(annotated_frame, cast(List[Box], boxes))
            self.image_storage.upload_memory_image(annotated_frame, f"{self.truck_id}_{int(time.time())}.jpg", image_type="annotated_frames")
        
        except Exception as e:
            self.logger.warning(f"Error drawing boxes: {e}")
        
        detection_metric = self.get_detection_metric()
        if detection_metric is not None:
            for _ in boxes:
                detection_metric.inc() # type: ignore

        self.logger.info(f"Detected {len(boxes)} {self.get_object_type()}")
        return boxes
    
    def _extract_crop(self, box: Any, frame: np.ndarray, box_index: int) -> Tuple[Optional[np.ndarray], Optional[float]]:
        """
        Extract and validate crop from detection box.
        
        Returns:
            (crop, confidence) or (None, None) if invalid
        """
        x1, y1, x2, y2, conf = map(float, box)

        if conf < self.config.min_detection_confidence:
            self.logger.debug(f"Low confidence box ignored ({conf:.2f})")
            return None, None

        crop = frame[int(y1):int(y2), int(x1):int(x2)]
        
        if not self.is_valid_detection(crop, conf, box_index):
            return None, None

        self.logger.debug(f"Crop {box_index} valid")
        return crop, conf
    
    def _process_ocr_result(self, crop: np.ndarray) -> Optional[Tuple[str, float, np.ndarray]]:
        """
        Run OCR on crop and process result.
        
        Returns:
            (final_text, confidence, best_crop) if consensus reached, else None
        """
        self.logger.info("Running OCR")
        text, ocr_conf = self.ocr.extract_text(crop)

        if not text or ocr_conf <= 0.0:
            return None

        if self.ocr_confidence:
            self.ocr_confidence.observe(ocr_conf) # type: ignore

        # Store candidate crop with OCR text (overwrites fallback entry)
        text_normalized = text.upper().replace("-", "")
        self.consensus_algorithm.add_candidate_crop(crop.copy(), text_normalized, ocr_conf, is_fallback=False)
        
        self.logger.debug(f"Candidate: '{text_normalized}' ({ocr_conf:.2f})")

        self.consensus_algorithm.add_to_consensus(text_normalized, ocr_conf)

        if self.consensus_algorithm.check_full_consensus():
            final_text = self.consensus_algorithm.build_final_text()
            confidence = self.consensus_algorithm.compute_consensus_confidence()
            self.logger.info(f"Consensus: '{final_text}' (confidence={confidence:.3f})")
            best_crop = self.consensus_algorithm.select_best_crop(final_text)
            return final_text, confidence, best_crop # type: ignore

        return None
    
    def _clear_frames_queue(self) -> None:
        count = 0
        while not self.frames_queue.empty():
            try:
                self.frames_queue.get_nowait()
                count += 1
            except Empty:
                break
        if count:
            self.logger.debug(f"Cleared {count} frames from queue")
    
    def _publish_detection(self, message: Message) -> None:
        """
        Publish detection event to Kafka.
        
        Uses self.truck_id which is set when receiving a Kafka message.
        
        Args:
            message: Message object to publish
        """

        self.kafka_producer.produce(
            topic=self.get_produce_topic(),
            data=message.to_dict(),
            headers={"truckId": self.truck_id}
        )
    
    def _cleanup(self) -> None:
        """Release resources and perform cleanup."""
        self.logger.info(f"Cleaning up resources for {self.agent_name}…")
        self.stream_manager.release()
        self.kafka_producer.flush()
        self.kafka_producer.close()
        self.kafka_consumer.close()