"""
Base Agent Template

This module provides a base agent class following the Template Method pattern.
It extracts common behavior from AgentB and AgentC, leaving specific implementations
for child classes to override.

The base agent handles:
- Kafka consumer/producer setup and lifecycle
- Stream connection management
- Frame buffering and queue management
- Consensus algorithm for text extraction across multiple frames
- Crop selection based on text similarity
- MinIO storage integration
- Prometheus metrics
- Main processing loop with message polling
"""

import os
import time
import json
import uuid
import math
from abc import ABC, abstractmethod
from queue import Queue, Empty
from confluent_kafka import Producer, Consumer, KafkaException, KafkaError # type: ignore
import logging
from typing import Optional, Tuple, Dict, Any
from prometheus_client import Counter, Histogram # type: ignore

from shared.stream_manager import StreamManager
from shared.object_detector import ObjectDetector
from shared.paddle_ocr import OCR
from shared.image_storage import ImageStorage
from shared.plate_classifier import PlateClassifier
from shared.bounding_box_drawer import BoundingBoxDrawer
from shared.kafka_wrapper import KafkaProducerWrapper, KafkaConsumerWrapper
from shared.consensus_algorithm import ConsensusAlgorithm

MAX_FRAMES = 40

class BaseAgent(ABC):
    """
    Base agent class that implements common detection and consensus logic.
    
    Child classes should override:
    - get_agent_name(): Return agent identifier
    - get_yolo_model_path(): Return path to YOLO model
    - get_storage_bucket(): Return MinIO bucket name
    - get_consume_topic(): Return Kafka consumer topic
    - get_produce_topic(): Return Kafka producer topic
    - is_valid_detection(): Validate detection box (e.g., plate classification)
    - build_publish_payload(): Build Kafka message payload
    - init_metrics(): Initialize Prometheus metrics
    - get_object_type(): Return detected object type name for logging
    """

    def __init__(self):
        """Initialize base agent with common components."""
        # Agent identification
        self.agent_name = self.get_agent_name()
        self.logger = logging.getLogger(self.agent_name)
        
        # Load environment configuration
        self._load_config()
        
        # Initialize models
        self.yolo = ObjectDetector(self.get_yolo_model_path())
        self.ocr = OCR()
        self.classifier = PlateClassifier()
        self.drawer = BoundingBoxDrawer(color=self.get_bbox_color(), thickness=2, label=self.get_bbox_label())
        self.annotated_frames_storage = ImageStorage(self.minio_conf, self.get_annotated_frames_bucket())
        self.crop_storage = ImageStorage(self.minio_conf, self.get_crops_bucket())
        self.stream_manager = StreamManager(self.stream_url)
        self.kafka_producer = KafkaProducerWrapper(self.kafka_bootstrap)
        self.kafka_consumer = KafkaConsumerWrapper(self.kafka_bootstrap, f"{self.agent_name.lower()}-group", [self.get_consume_topic()])
        self.consensus_algorithm = ConsensusAlgorithm()
        
        # Runtime state
        self.running = True
        self.frames_queue = Queue()
        self.stream = None
        self.truck_id = ""
        
        # Metrics
        self.init_metrics()
        self.frames_processed = 0

        self.logger.info(f"[{self.agent_name}] Initialized successfully")

    def _load_config(self):
        """Load environment configuration."""
        nginx_host = os.getenv("NGINX_RTMP_HOST", "10.255.32.80")
        nginx_port = os.getenv("NGINX_RTMP_PORT", "1935")
        gate_id = os.getenv("GATE_ID", "1")
        
        self.gate_id = gate_id
        self.stream_url = f"rtmp://{nginx_host}:{nginx_port}/streams_high/gate{gate_id}"
        self.kafka_bootstrap = os.getenv("KAFKA_BOOTSTRAP", "10.255.32.143:9092")
        
        # MinIO configuration
        minio_host = os.getenv("MINIO_HOST", "10.255.32.82")
        minio_port = os.getenv("MINIO_PORT", "9000")
        
        self.minio_conf = {
            "endpoint": f"{minio_host}:{minio_port}",
            "access_key": os.getenv("ACCESS_KEY"),
            "secret_key": os.getenv("SECRET_KEY"),
            "secure": False
        }

        self.MAX_FRAMES = float(os.getenv("MAX_FRAMES", MAX_FRAMES))
        self.MIN_DETECTION_CONFIDENCE = float(os.getenv("MIN_DETECTION_CONFIDENCE", 0.4))

    # ========================================================================
    # Abstract methods - must be implemented by child classes
    # ========================================================================

    @abstractmethod
    def get_agent_name(self) -> str:
        """Return agent identifier (e.g., 'AgentB', 'AgentC')."""
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
    def get_annotated_frames_bucket(self) -> str:
        """Return bucket name for annotated frames."""
        pass

    @abstractmethod
    def get_crops_bucket(self) -> str:
        """Return bucket name for crops."""
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
    def is_valid_detection(self, crop, confidence: float, box_index: int) -> bool:
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
    def build_publish_payload(self, truck_id: str, detection_result: Dict[str, Any], 
                              confidence: float, crop_url: Optional[str]) -> Dict[str, Any]:
        """
        Build Kafka message payload for publishing detection results.
        
        Args:
            truck_id: Truck identifier
            detection_result: Dictionary with detection-specific data
            confidence: Detection confidence
            crop_url: MinIO crop URL
            
        Returns:
            Dictionary payload to be JSON-encoded
        """
        pass

    @abstractmethod
    def init_metrics(self):
        """Initialize Prometheus metrics specific to this agent."""
        pass

    @abstractmethod
    def get_object_type(self) -> str:
        """Return detected object type name (e.g., 'license plate', 'hazard plate')."""
        pass

    # ========================================================================
    # Template methods - common behavior with extension points
    # ========================================================================
    
    def loop(self):
        """Main processing loop."""
        self.logger.info(
            f"[{self.agent_name}] Main loop starting… (topic in='{self.get_consume_topic()}')")
        
        # Clear any stale messages on startup
        self.kafka_consumer.clear_stale_messages()

        try:
            while self.running:
                msg = self.kafka_consumer.consume_message(timeout=1.0)
                
                if msg is None or msg.error():
                    continue
                
                self._process_message(msg)
                
        except KeyboardInterrupt:
            self.logger.info(f"[{self.agent_name}] Interrupted by user.")
        except KafkaException as e:
            self.logger.exception(f"[{self.agent_name}/Kafka] Kafka error: {e}")
        except Exception as e:
            self.logger.exception(f"[{self.agent_name}] Unexpected error: {e}")
        finally:
            self._cleanup_resources()

    def stop(self):
        """Gracefully stop agent."""
        self.logger.info(f"[{self.agent_name}] Stopping agent…")
        self.running = False

    def _get_frames(self, num_frames: int = 30):
        """
        Capture frames from RTMP/RTSP stream with automatic reconnection.
        
        Args:
            num_frames: Number of frames to capture
        """
        self.logger.info(f"[{self.agent_name}] Reading {num_frames} frame(s) from RTMP…")

        captured = 0
        while captured < num_frames and self.running:
            try:
                frame = self.stream_manager.read()
                if frame is not None:
                    self.frames_queue.put(frame)
                    captured += 1
                    self.logger.debug(f"[{self.agent_name}] Captured {captured}/{num_frames}.")
                else:
                    time.sleep(0.1)
            
            except Exception as e:
                self.logger.exception(f"[{self.agent_name}] Error when capturing frame {e}")
                time.sleep(0.2)

    def _get_next_frame(self):
        """Get next frame from queue, capturing more if needed."""
        if self.frames_queue.empty():
            self.logger.debug(f"[{self.agent_name}] Frames queue is empty, capturing more frames.")
            self._get_frames(5)
        
        if self.frames_queue.empty():
            self.logger.warning(f"[{self.agent_name}] No frame captured from RTSP.")
            return None
        
        try:
            frame = self.frames_queue.get_nowait()
            self.logger.debug(f"[{self.agent_name}] Frame obtained from queue.")
            return frame
        
        except Empty:
            self.logger.warning(f"[{self.agent_name}] Frames queue is empty.")
            time.sleep(0.05)
            return None

    def _clear_frames_queue(self):
        """Clear all remaining frames from queue."""
        remaining = self.frames_queue.qsize()
        if remaining > 0:
            self.logger.debug(f"[{self.agent_name}] Clearing {remaining} remaining frames from queue")
            while not self.frames_queue.empty():
                try:
                    self.frames_queue.get_nowait()
                except Empty:
                    break

    def _should_continue_processing(self) -> bool:
        """Check if frame processing should continue."""
        return self.running and not self.consensus_algorithm.consensus_reached and self.frames_processed < self.MAX_FRAMES

    def _run_yolo_detection(self, frame):
        """Run YOLO detection on frame."""
        self.logger.info(f"[{self.agent_name}] YOLO running…")
        
        inference_latency = getattr(self, 'inference_latency', None)
        if inference_latency:
            with inference_latency.time():
                results = self.yolo.detect(frame)
        else:
            results = self.yolo.detect(frame)

        if not results:
            self.logger.debug(f"[{self.agent_name}] YOLO did not return a result for this frame.")
            return None

        if not self.yolo.object_found(results):
            self.logger.info(f"[{self.agent_name}] No {self.get_object_type()} detected for this frame.")
            return None

        boxes = self.yolo.get_boxes(results)

        try:
            annotated_frame = frame.copy()
            annotated_frame = self.drawer.draw_box(annotated_frame, boxes)
            self.annotated_frames_storage.upload_memory_image(annotated_frame, f"{self.truck_id}_{int(time.time())}.jpg")
        except Exception as e:
            self.logger.exception(f"[{self.agent_name}] Error drawing boxes: {e}")
        
        plates_detected = getattr(self, 'plates_detected', None)
        hazards_detected = getattr(self, 'hazards_detected', None)
        
        if plates_detected:
            for _ in boxes:
                plates_detected.inc()

        if hazards_detected:
            for _ in boxes:
                hazards_detected.inc()

        self.logger.info(f"[{self.agent_name}] {len(boxes)} {self.get_object_type()}(s) detected.")
        return boxes

    def _extract_crop(self, box, frame, box_index: int) -> Optional[Tuple]:
        """
        Extract and validate crop from detection box.
        
        Returns:
            (crop, confidence) or (None, None) if invalid
        """
        x1, y1, x2, y2, conf = map(float, box)

        if conf < self.MIN_DETECTION_CONFIDENCE:
            self.logger.info(f"[{self.agent_name}] Ignored low confidence box (conf={conf:.2f}).")
            return None, None

        crop = frame[int(y1):int(y2), int(x1):int(x2)]
        
        if not self.is_valid_detection(crop, conf, box_index):
            return None, None

        self.logger.info(f"[{self.agent_name}] Crop {box_index} accepted")
        return crop, conf

    def _process_ocr_result(self, crop, crop_index: int):
        """
        Run OCR on crop and process result.
        
        Returns:
            (final_text, confidence, best_crop) if consensus reached, else None
        """
        self.logger.info(f"[{self.agent_name}] OCR extracting text…")
        text, ocr_conf = self.ocr._extract_text(crop)

        if not text or ocr_conf <= 0.0:
            self.logger.debug(f"[{self.agent_name}] OCR returned no valid text for crop {crop_index}")
            return None

        self.logger.info(f"[{self.agent_name}] OCR: '{text}' (conf={ocr_conf:.2f})")

        ocr_confidence = getattr(self, 'ocr_confidence', None)
        if ocr_confidence:
            ocr_confidence.observe(ocr_conf)

        # Store candidate crop with OCR text (overwrites fallback entry)
        text_normalized = text.upper().replace("-", "")
        self.consensus_algorithm.add_candidate_crop(crop.copy(), text_normalized, ocr_conf, is_fallback=False)
        
        self.logger.debug(
            f"[{self.agent_name}] Added candidate crop: '{text_normalized}' (conf={ocr_conf:.2f})")

        self.consensus_algorithm.add_to_consensus(text_normalized, ocr_conf)

        if self.consensus_algorithm.check_full_consensus():
            final_text = self.consensus_algorithm.build_final_text()
            self.logger.info(f"[{self.agent_name}] Full consensus achieved: '{final_text}'")
            best_crop = self.consensus_algorithm.select_best_crop(final_text)
            return final_text, 1.0, best_crop

        return None

    def _process_single_frame(self, frame):
        """
        Process a single video frame.
        
        Returns:
            (text, conf, crop) if consensus is reached, else None
        """
        try:
            boxes = self._run_yolo_detection(frame)
            if boxes is None:
                return None

            for i, box in enumerate(boxes, start=1):
                crop, yolo_conf = self._extract_crop(box, frame, i) # type: ignore
                if crop is None:
                    continue

                # Always add valid crops to candidates (even if OCR fails)
                # This ensures we have crops available for fallback selection
                self.consensus_algorithm.add_candidate_crop(crop.copy(), "", yolo_conf, is_fallback=True)

                try:
                    result = self._process_ocr_result(crop, i)
                    if result:
                        return result
                except Exception as e:
                    self.logger.exception(f"[{self.agent_name}] OCR failure: {e}")

        except Exception as e:
            self.logger.exception(f"[{self.agent_name}] Error processing frame: {e}")

        return None

    def process_detection(self):
        """
        Main detection pipeline.
        
        Returns:
            tuple: (text, confidence, crop_image) or (None, None, None)
        """
        self.logger.info(f"[{self.agent_name}] Starting detection pipeline…")
        self.consensus_algorithm.reset()
        self.frames_processed = 0

        while self._should_continue_processing():
            frame = self._get_next_frame()
            if frame is None:
                return None, None, None
            
            frames_metric = getattr(self, 'frames_processed_metric', None)
            if frames_metric:
                frames_metric.inc()
            
            self.frames_processed += 1
            self.logger.debug(
                f"[{self.agent_name}] Processing frame {self.frames_processed}/{self.MAX_FRAMES}")

            result = self._process_single_frame(frame)
            if result:
                text, conf, crop = result
                self.logger.info(f"[{self.agent_name}] Consensus reached: '{text}' (conf={conf:.2f})")
                self._clear_frames_queue()
                return text, conf, crop

        if self.frames_processed >= self.MAX_FRAMES:
            self.logger.info(
                f"[{self.agent_name}] Frame limit reached ({self.MAX_FRAMES}), returning best partial result")

        return self.consensus_algorithm.get_best_partial_result(self.get_object_type())

    def _extract_truck_id(self, msg) -> str:
        """
        Extract truckId from message headers.
        
        Returns:
            truckId or generates a new UUID if not found
        """
        for k, v in (msg.headers() or []):
            if k == "truckId" and v is not None:
                return v.decode() if isinstance(v, (bytes, bytearray)) else str(v)
        return str(uuid.uuid4())

    def _upload_crop_to_storage(self, text: str) -> Optional[str]:
        """
        Upload best crop to MinIO storage.
        
        Uses self.truck_id which is set when receiving a Kafka message.
        
        Returns:
            Crop URL or None if upload fails
        """
        if self.consensus_algorithm.best_crop is None:
            return None
        
        try:
            best_crop = self.consensus_algorithm.best_crop
            crop_url = self.crop_storage.upload_memory_image(best_crop, f"{self.truck_id}_{int(time.time())}.jpg")
            
            if crop_url:
                self.logger.info(f"[{self.agent_name}] Crop uploaded: {crop_url}")
            else:
                self.logger.warning(f"[{self.agent_name}] Failed to upload crop to MinIO")
            
            return crop_url
        except Exception as e:
            self.logger.exception(f"[{self.agent_name}] Error uploading crop to MinIO: {e}")
            return None

    def _publish_detection(self, detection_result: Dict[str, Any], 
                          confidence: float, crop_url: Optional[str]):
        """
        Publish detection event to Kafka.
        
        Uses self.truck_id which is set when receiving a Kafka message.
        
        Args:
            detection_result: Detection-specific data
            confidence: Detection confidence
            crop_url: MinIO crop URL
        """
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        payload = self.build_publish_payload(self.truck_id, detection_result, confidence, crop_url)
        payload["timestamp"] = timestamp
        
        self.logger.info(f"[{self.agent_name}] Publishing '{self.get_produce_topic()}' (truckId={self.truck_id}) …")

        self.kafka_producer.produce(self.get_produce_topic(), payload, headers={"truckId": self.truck_id})

    def _process_message(self, msg):
        """
        Process single Kafka message and handle detection.
        Can be overridden by child classes for custom processing logic.
        """
        # Set truck_id as instance variable for use throughout the processing cycle
        self.truck_id = self._extract_truck_id(msg)
        self.logger.info(
            f"[{self.agent_name}] Received 'truck-detected' (truckId={self.truck_id}). Starting pipeline…")

        # Run detection pipeline and always use the returned crop
        text, confidence, crop = self.process_detection()

        crop_url = None
        if crop is not None:
            # Always upload the returned crop, even if text is N/A
            try:
                crop_url = self.crop_storage.upload_memory_image(crop, f"{self.truck_id}_{int(time.time())}.jpg")
                self.logger.info(f"[{self.agent_name}] Crop uploaded: {crop_url}")
            except Exception as e:
                self.logger.exception(f"[{self.agent_name}] Error uploading crop to MinIO: {e}")
        else:
            self.logger.warning(f"[{self.agent_name}] No crop available for upload")

        # Handle text results
        if not text:
            self.logger.warning(f"[{self.agent_name}] No final text results — using fallback.")
            text = "N/A"
            confidence = confidence if confidence is not None else 0.0

        # Parse detection result (can be overridden)
        detection_result = self._parse_detection_result(text)

        # Publish results
        self._publish_detection(detection_result, confidence, crop_url) # type: ignore

        # Clear frames queue for next detection
        with self.frames_queue.mutex:
            self.frames_queue.queue.clear()

    def _parse_detection_result(self, text: str) -> Dict[str, Any]:
        """
        Parse detection text into structured result.
        Default implementation returns text as-is.
        Can be overridden by child classes for custom parsing.
        """
        return {"text": text}

    def _publish_empty_result(self):
        """
        Publish empty result when detection fails.
        
        Uses self.truck_id which is set when receiving a Kafka message.
        Can be overridden by child classes.
        """
        self._publish_detection({"text": "N/A"}, -1, None)

    def _cleanup_resources(self):
        """Release all resources gracefully."""
        self.logger.info(f"[{self.agent_name}] Freeing resources…")
        
        self.stream_manager.release()
        self.kafka_producer.flush()
