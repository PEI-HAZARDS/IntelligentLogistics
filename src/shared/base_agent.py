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

from shared.stream_reader import StreamReader
from shared.object_detector import ObjectDetector
from shared.paddle_ocr import OCR
from shared.image_storage import ImageStorage
from shared.plate_classifier import PlateClassifier


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

    # Consensus configuration
    DECISION_THRESHOLD = 8
    CONSENSUS_PERCENTAGE = 0.8
    MAX_FRAMES = 40
    MIN_TEXT_LENGTH = 4
    MIN_CONFIDENCE_CONSENSUS = 0.80
    MIN_DETECTION_CONFIDENCE = 0.4

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
        
        # Runtime state
        self.running = True
        self.frames_queue = Queue()
        self.stream = None
        
        # Consensus state
        self._init_consensus_state()
        
        # Storage
        self.crop_storage = ImageStorage(self.minio_conf, self.get_storage_bucket())
        
        # Kafka setup
        self._init_kafka()
        
        # Metrics
        self.init_metrics()
        
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

    def _init_consensus_state(self):
        """Initialize consensus algorithm state."""
        self.consensus_reached = False
        self.counter = {}  # {position: {character: count}}
        self.decided_chars = {}  # {position: character}
        self.frames_processed = 0
        self.length_counter = {}  # {length: count}
        self.best_crop = None
        self.best_confidence = 0.0
        self.candidate_crops = []  # [{"crop": array, "text": str, "confidence": float}]
        
        # Stream reconnection tracking
        self.consecutive_none_frames = 0
        self.max_none_frames_before_reconnect = 10

    def _init_kafka(self):
        """Initialize Kafka consumer and producer."""
        self.logger.info(f"[{self.agent_name}/Kafka] Connecting to kafka via '{self.kafka_bootstrap}' …")
        
        # Consumer
        self.consumer = Consumer({
            "bootstrap.servers": self.kafka_bootstrap,
            "group.id": f"{self.agent_name.lower()}-group",
            "auto.offset.reset": "latest",
            "enable.auto.commit": True,
            "session.timeout.ms": 10000,
            "max.poll.interval.ms": 300000,
        })
        
        self.consumer.subscribe([self.get_consume_topic()])
        
        # Producer
        self.producer = Producer({
            "bootstrap.servers": self.kafka_bootstrap,
        })

    # ========================================================================
    # Abstract methods - must be implemented by child classes
    # ========================================================================

    @abstractmethod
    def get_agent_name(self) -> str:
        """Return agent identifier (e.g., 'AgentB', 'AgentC')."""
        pass

    @abstractmethod
    def get_yolo_model_path(self) -> str:
        """Return path to YOLO model file."""
        pass

    @abstractmethod
    def get_storage_bucket(self) -> str:
        """Return MinIO bucket name for storing crops."""
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

    def _connect_to_stream_with_retry(self, max_retries: int = 10):
        """
        Attempt to connect to RTMP stream with automatic retry.
        
        Args:
            max_retries: Maximum number of connection attempts
            
        Returns:
            StreamReader instance
            
        Raises:
            ConnectionError: If connection fails after max retries
        """
        retry_delay = 5  # seconds
        
        for attempt in range(1, max_retries + 1):
            try:
                self.logger.info(
                    f"[{self.agent_name}] Connection attempt {attempt}/{max_retries} to: {self.stream_url}")
                stream = StreamReader(self.stream_url)
                self.logger.info(f"[{self.agent_name}] Successfully connected to stream!")
                return stream
            
            except ConnectionError as e:
                self.logger.warning(
                    f"[{self.agent_name}] Connection failed (attempt {attempt}/{max_retries}): {e}")

                if attempt < max_retries:
                    self.logger.info(
                        f"[{self.agent_name}] Waiting {retry_delay}s before retry...")
                    time.sleep(retry_delay)
                else:
                    self.logger.error(
                        f"[{self.agent_name}] Max retries reached. Could not connect to stream.")
                    raise
            except Exception as e:
                self.logger.exception(
                    f"[{self.agent_name}] Unexpected error during connection: {e}")
                raise

    def _handle_stream_failure(self):
        """
        Handle consecutive frame read failures and attempt reconnection if needed.
        
        Returns:
            bool: True if reconnection was attempted and successful, False otherwise
        """
        self.consecutive_none_frames += 1
        self.logger.debug(
            f"[{self.agent_name}] No frame available from stream "
            f"({self.consecutive_none_frames} consecutive failures).")
        
        # If stream appears dead, attempt reconnection
        if self.consecutive_none_frames >= self.max_none_frames_before_reconnect:
            self.logger.warning(
                f"[{self.agent_name}] Stream appears dead after {self.consecutive_none_frames} "
                "failed reads. Attempting reconnection...")
            
            # Release old connection
            if self.stream is not None:
                try:
                    self.stream.release()
                    self.logger.info(f"[{self.agent_name}] Released old stream connection.")
                except Exception as e:
                    self.logger.error(f"[{self.agent_name}] Error releasing old stream: {e}")
            
            # Attempt to reconnect
            try:
                self.stream = self._connect_to_stream_with_retry()
                self.consecutive_none_frames = 0  # Reset counter on successful reconnection
                self.logger.info(f"[{self.agent_name}] Successfully reconnected to stream!")
                return True
            except Exception as e:
                self.logger.error(f"[{self.agent_name}] Failed to reconnect: {e}")
                time.sleep(5)  # Wait before next attempt
                return False
        
        return False

    def _reset_consensus_state(self):
        """Reset consensus algorithm state."""
        self.counter = {}
        self.decided_chars = {}
        self.consensus_reached = False
        self.best_crop = None
        self.best_confidence = 0.0
        self.candidate_crops = []
        self.frames_processed = 0
        self.length_counter = {}
        self.consecutive_none_frames = 0
        self.logger.debug(f"[{self.agent_name}] Consensus state reset.")

    def _get_frames(self, num_frames: int = 30):
        """
        Capture frames from RTMP/RTSP stream with automatic reconnection.
        
        Args:
            num_frames: Number of frames to capture
        """
        if self.stream is None:
            self.logger.info(
                f"[{self.agent_name}] Connecting to RTMP stream (via Nginx): {self.stream_url}")
            try:
                self.stream = self._connect_to_stream_with_retry()
            except Exception as e:
                self.logger.exception(f"[{self.agent_name}] Failed to connect to stream: {e}")
                return

        self.logger.info(f"[{self.agent_name}] Reading {num_frames} frame(s) from RTMP…")

        captured = 0
        while captured < num_frames and self.running:
            try:
                frame = self.stream.read()
                if frame is not None:
                    self.frames_queue.put(frame)
                    captured += 1
                    self.consecutive_none_frames = 0  # Reset on successful read
                    self.logger.debug(f"[{self.agent_name}] Captured {captured}/{num_frames}.")
                else:
                    # Handle stream failure and attempt reconnection if needed
                    if self._handle_stream_failure():
                        # Reconnection successful, continue capturing
                        continue
                    else:
                        # Wait briefly before next attempt
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
        return self.running and not self.consensus_reached and self.frames_processed < self.MAX_FRAMES

    def _run_yolo_detection(self, frame):
        """Run YOLO detection on frame."""
        self.logger.info(f"[{self.agent_name}] YOLO running…")
        
        results = self.yolo.detect(frame)
        self.frames_processed += 1

        if not results:
            self.logger.debug(f"[{self.agent_name}] YOLO did not return a result for this frame.")
            return None

        if not self.yolo.object_found(results):
            self.logger.info(f"[{self.agent_name}] No {self.get_object_type()} detected for this frame.")
            return None

        boxes = self.yolo.get_boxes(results)
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

        # Store candidate crop
        text_normalized = text.upper().replace("-", "")
        self.candidate_crops.append({
            "crop": crop.copy(),
            "text": text_normalized,
            "confidence": ocr_conf
        })
        self.logger.debug(
            f"[{self.agent_name}] Added candidate crop: '{text_normalized}' (conf={ocr_conf:.2f})")

        self._add_to_consensus(text, ocr_conf)

        if self._check_full_consensus():
            final_text = self._build_final_text()
            self.logger.info(f"[{self.agent_name}] Full consensus achieved: '{final_text}'")
            best_crop = self._select_best_crop(final_text)
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
                crop, _ = self._extract_crop(box, frame, i)
                if crop is None:
                    continue

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
        self._reset_consensus_state()

        while self._should_continue_processing():
            frame = self._get_next_frame()
            if frame is None:
                return None, None, None

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

        return self._get_best_partial_result()

    # ========================================================================
    # Consensus algorithm
    # ========================================================================

    def _normalize_text(self, text: str) -> str:
        """Normalize text for consensus: uppercase and remove dashes."""
        return text.upper().replace("-", "")

    def _is_valid_for_consensus(self, text_normalized: str, confidence: float) -> bool:
        """Check if OCR result is valid for consensus algorithm."""
        if confidence < self.MIN_CONFIDENCE_CONSENSUS:
            self.logger.debug(
                f"[{self.agent_name}] Confidence too low ({confidence:.2f}), skipping")
            return False

        if len(text_normalized) < self.MIN_TEXT_LENGTH:
            self.logger.debug(
                f"[{self.agent_name}] Text too short ('{text_normalized}'), skipping")
            return False

        return True

    def _track_text_length(self, text_len: int) -> bool:
        """
        Track text length and validate against most common length.
        
        Returns:
            True if text length is acceptable, False otherwise
        """
        if text_len not in self.length_counter:
            self.length_counter[text_len] = 0
        self.length_counter[text_len] += 1

        if sum(self.length_counter.values()) < 3:
            return True

        most_common_length = max(self.length_counter.items(), key=lambda x: x[1])[0]
        if text_len != most_common_length:
            self.logger.debug(
                f"[{self.agent_name}] Text length mismatch: {text_len} chars, "
                f"expected {most_common_length} (most common). Skipping to avoid misalignment.")
            return False

        return True

    def _get_vote_weight(self, confidence: float) -> int:
        """Return vote weight based on confidence level."""
        return 2 if confidence >= 0.95 else 1

    def _update_position_decision(self, pos: int, char: str):
        """Update decision for a character position if threshold reached."""
        if self.counter[pos][char] < self.DECISION_THRESHOLD:
            return

        if pos not in self.decided_chars:
            self.decided_chars[pos] = char
            self.logger.debug(f"[{self.agent_name}] Position {pos} decided: '{char}'")
        elif self.decided_chars[pos] != char:
            old_char = self.decided_chars[pos]
            self.decided_chars[pos] = char
            self.logger.debug(f"[{self.agent_name}] Position {pos} changed: '{old_char}' -> '{char}'")

    def _add_to_consensus(self, text: str, confidence: float):
        """
        Add OCR result to consensus algorithm.
        Vote for each character at its position.
        """
        text_normalized = self._normalize_text(text)

        if not self._is_valid_for_consensus(text_normalized, confidence):
            return

        if not self._track_text_length(len(text_normalized)):
            return

        self.logger.debug(
            f"[{self.agent_name}] Adding to consensus: '{text_normalized}' "
            f"(conf={confidence:.2f}, len={len(text_normalized)})")

        # Initialize positions
        for pos in range(len(text_normalized)):
            if pos not in self.counter:
                self.counter[pos] = {}

        # Add votes for each character
        vote_weight = self._get_vote_weight(confidence)
        for pos, char in enumerate(text_normalized):
            if char not in self.counter[pos]:
                self.counter[pos][char] = 0

            self.counter[pos][char] += vote_weight
            self._update_position_decision(pos, char)

    def _check_full_consensus(self) -> bool:
        """
        Check if consensus reached based on percentage of decided positions.
        """
        if not self.counter:
            return False

        total_positions = len(self.counter)
        decided_count = len(self.decided_chars)

        required_positions = math.ceil(total_positions * self.CONSENSUS_PERCENTAGE)

        if decided_count >= required_positions:
            self.logger.info(
                f"[{self.agent_name}] Consensus reached! {decided_count}/{total_positions} "
                f"positions decided (need {required_positions}) ✓")
            self.consensus_reached = True
            return True

        self.logger.debug(
            f"[{self.agent_name}] Consensus check: {decided_count}/{total_positions} "
            f"positions decided (need {required_positions})")
        return False

    def _build_final_text(self) -> str:
        """Build final text from decided characters."""
        if not self.decided_chars:
            return ""

        text_chars = []
        for pos in sorted(self.decided_chars.keys()):
            text_chars.append(self.decided_chars[pos])

        final_text = "".join(text_chars)
        self.logger.debug(f"[{self.agent_name}] Built final text: '{final_text}'")
        return final_text

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein (edit) distance between two strings."""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]

    def _select_best_crop(self, final_text: str):
        """
        Select best crop based on similarity to final consensus text.
        
        Returns:
            Crop image or None
        """
        if not self.candidate_crops:
            self.logger.warning(f"[{self.agent_name}] No candidate crops available")
            return None
        
        if not final_text:
            best = max(self.candidate_crops, key=lambda x: x["confidence"])
            self.logger.debug(
                f"[{self.agent_name}] No final text, using highest confidence crop: '{best['text']}'")
            return best["crop"]
        
        # Calculate scores for each candidate
        scored_crops = []
        for candidate in self.candidate_crops:
            distance = self._levenshtein_distance(candidate["text"], final_text)
            max_len = max(len(candidate["text"]), len(final_text), 1)
            similarity = 1 - (distance / max_len)
            scored_crops.append({
                "crop": candidate["crop"],
                "text": candidate["text"],
                "confidence": candidate["confidence"],
                "distance": distance,
                "similarity": similarity
            })
        
        # Sort by similarity (descending), then confidence (descending)
        scored_crops.sort(key=lambda x: (x["similarity"], x["confidence"]), reverse=True)
        
        best = scored_crops[0]
        self.logger.info(
            f"[{self.agent_name}] Selected best crop: '{best['text']}' "
            f"(similarity={best['similarity']:.2f}, distance={best['distance']}, "
            f"conf={best['confidence']:.2f}) for final text '{final_text}'"
        )
        
        self.best_crop = best["crop"]
        self.best_confidence = best["confidence"]
        
        return best["crop"]

    def _get_best_partial_result(self):
        """
        Return best partial result if full consensus not reached.
        Fill undecided positions with most voted character.
        """
        if not self.counter:
            self.logger.warning(
                f"[{self.agent_name}] No valid {self.get_object_type()}s detected in any frame.")
            return None, None, None

        text_chars = []
        total_positions = max(self.counter.keys()) + 1

        for pos in range(total_positions):
            if pos in self.decided_chars:
                text_chars.append(self.decided_chars[pos])
            elif pos in self.counter and self.counter[pos]:
                best_char = max(self.counter[pos].items(), key=lambda x: x[1])[0]
                text_chars.append(best_char)
            else:
                text_chars.append("_")

        partial_text = "".join(text_chars)

        decided_count = len(self.decided_chars)
        confidence = decided_count / total_positions
        confidence = min(confidence, 0.95)

        best_crop = self._select_best_crop(partial_text)

        self.logger.info(
            f"[{self.agent_name}] Partial result: '{partial_text}' "
            f"({decided_count}/{total_positions} decided, conf={confidence:.2f})")

        return partial_text, confidence, best_crop

    # ========================================================================
    # Kafka operations
    # ========================================================================

    def _delivery_callback(self, err: Optional[KafkaError], msg) -> None:
        """Kafka message delivery confirmation callback."""
        if err is not None:
            self.logger.error(
                f"[{self.agent_name}/Kafka] Message delivery failed: {err} "
                f"(topic={msg.topic()}, partition={msg.partition()})"
            )
        else:
            self.logger.debug(
                f"[{self.agent_name}/Kafka] Message delivered successfully to "
                f"{msg.topic()}[{msg.partition()}] at offset {msg.offset()}"
            )

    def _poll_latest_message(self):
        """
        Poll Kafka for latest message, skipping old ones.
        
        Returns:
            Latest message or None
        """
        msgs_buffer = []
        
        # Drain old messages
        while True:
            temp_msg = self.consumer.poll(timeout=0.1)
            if temp_msg is None:
                break
            if temp_msg.error():
                continue
            msgs_buffer.append(temp_msg)
        
        # Return only the latest message
        if msgs_buffer:
            skipped = len(msgs_buffer) - 1
            if skipped > 0:
                self.logger.info(
                    f"[{self.agent_name}] Skipped {skipped} old messages, processing latest only")
            return msgs_buffer[-1]
        
        # Wait for new message if buffer was empty
        return self.consumer.poll(timeout=1.0)

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

    def _upload_crop_to_storage(self, truck_id: str, text: str) -> Optional[str]:
        """
        Upload best crop to MinIO storage.
        
        Returns:
            Crop URL or None if upload fails
        """
        if self.best_crop is None:
            return None
        
        try:
            object_name = self._generate_crop_filename(truck_id, text)
            crop_url = self.crop_storage.upload_memory_image(self.best_crop, object_name)
            
            if crop_url:
                self.logger.info(f"[{self.agent_name}] Crop uploaded: {crop_url}")
            else:
                self.logger.warning(f"[{self.agent_name}] Failed to upload crop to MinIO")
            
            return crop_url
        except Exception as e:
            self.logger.exception(f"[{self.agent_name}] Error uploading crop to MinIO: {e}")
            return None

    def _generate_crop_filename(self, truck_id: str, text: str) -> str:
        """
        Generate crop filename for MinIO storage.
        Can be overridden by child classes for custom naming.
        """
        return f"{self.agent_name.lower()}_{truck_id}_{text}.jpg"

    def _publish_detection(self, truck_id: str, detection_result: Dict[str, Any], 
                          confidence: float, crop_url: Optional[str]):
        """
        Publish detection event to Kafka.
        
        Args:
            truck_id: Truck identifier
            detection_result: Detection-specific data
            confidence: Detection confidence
            crop_url: MinIO crop URL
        """
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        payload = self.build_publish_payload(truck_id, detection_result, confidence, crop_url)
        payload["timestamp"] = timestamp
        
        self.logger.info(f"[{self.agent_name}] Publishing '{self.get_produce_topic()}' (truckId={truck_id}) …")

        self.producer.produce(
            topic=self.get_produce_topic(),
            key=None,
            value=json.dumps(payload).encode("utf-8"),
            headers={"truckId": truck_id},
            callback=self._delivery_callback
        )

        self.producer.poll(0)

    def _process_message(self, msg):
        """
        Process single Kafka message and handle detection.
        Can be overridden by child classes for custom processing logic.
        """
        truck_id = self._extract_truck_id(msg)
        self.logger.info(
            f"[{self.agent_name}] Received 'truck-detected' (truckId={truck_id}). Starting pipeline…")
        
        # Run detection pipeline
        text, confidence, _crop = self.process_detection()
        
        # Handle empty results
        if not text:
            self.logger.warning(f"[{self.agent_name}] No final text results — publishing empty message.")
            self._publish_empty_result(truck_id)
            return
        
        # Upload crop to storage
        crop_url = self._upload_crop_to_storage(truck_id, text)
        
        # Parse detection result (can be overridden)
        detection_result = self._parse_detection_result(text)
        
        # Publish results
        self._publish_detection(truck_id, detection_result, confidence, crop_url)
        
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

    def _publish_empty_result(self, truck_id: str):
        """
        Publish empty result when detection fails.
        Can be overridden by child classes.
        """
        self._publish_detection(truck_id, {"text": "N/A"}, -1, None)

    def _cleanup_resources(self):
        """Release all resources gracefully."""
        self.logger.info(f"[{self.agent_name}] Freeing resources…")
        
        # Release stream
        try:
            if self.stream is not None:
                self.stream.release()
                self.logger.debug(f"[{self.agent_name}] RTMP stream released.")
        except Exception as e:
            self.logger.exception(f"[{self.agent_name}] Error releasing RTMP stream: {e}")
        
        # Flush producer
        try:
            self.producer.flush(5)
        except Exception:
            pass
        
        # Close consumer
        try:
            self.consumer.close()
        except Exception:
            pass

    def _loop(self):
        """Main processing loop."""
        self.logger.info(
            f"[{self.agent_name}] Main loop starting… (topic in='{self.get_consume_topic()}')")

        try:
            while self.running:
                msg = self._poll_latest_message()
                
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
