from shared.stream_reader import StreamReader
from shared.object_detector import ObjectDetector
from shared.paddle_ocr import OCR
from shared.image_storage import ImageStorage
from shared.plate_classifier import PlateClassifier

import os
import time
import cv2 # type: ignore
import json
import uuid
from queue import Queue, Empty
from confluent_kafka import Producer, Consumer, KafkaException, KafkaError # type: ignore
import logging
from typing import Optional, Tuple
from prometheus_client import start_http_server, Counter, Histogram # type: ignore

# --- Configuration ---
# Load environment variables or fallback to default network settings
NGINX_RTMP_HOST = os.getenv("NGINX_RTMP_HOST", "10.255.32.80")
NGINX_RTMP_PORT = os.getenv("NGINX_RTMP_PORT", "1935")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "10.255.32.143:9092")
GATE_ID = os.getenv("GATE_ID", "1")
STREAM_HIGH = f"rtmp://{NGINX_RTMP_HOST}:{NGINX_RTMP_PORT}/streams_high/gate{GATE_ID}"

# MinIO Configuration
MINIO_HOST = os.getenv("MINIO_HOST", "10.255.32.82")
MINIO_PORT = os.getenv("MINIO_PORT", "9000")

MINIO_CONF = {
    "endpoint": f"{MINIO_HOST}:{MINIO_PORT}",
    "access_key": os.getenv("ACCESS_KEY"),
    "secret_key": os.getenv("SECRET_KEY"),
    "secure": False  # use HTTPS
}

BUCKET_NAME = os.getenv("BUCKET_NAME", "lp-crops")

# --- Operational Constants ---
MAX_CONNECTION_RETRIES = 10
RETRY_DELAY = 5  # seconds
TOPIC_CONSUME = f"truck-detected-{GATE_ID}"
TOPIC_PRODUCE = f"lp-results-{GATE_ID}"

logger = logging.getLogger("AgentB")


class AgentB:
    """
    Agent B:
    - Consumes 'truck-detected' events from Kafka.
    - Upon receipt, connects to/reads from the High-Quality RTSP stream.
    - Detects license plates using YOLO and extracts text using OCR.
    - Uses a consensus algorithm to validate characters across multiple frames.
    - Publishes 'license-plate-detected' to Kafka, propagating the truckId.
    """

    def __init__(self):
        # Initialize models
        self.yolo = ObjectDetector("/agentB/data/license_plate_model.pt")
        self.ocr = OCR()
        self.classifier = PlateClassifier()
        self.running = True
        self.frames_queue = Queue()


        # Connect on-demand when a Kafka event is received.
        self.stream = None

        # ============================================================
        # CONSENSUS STATE
        # ============================================================
        
        # Flag indicating if full consensus reached
        self.consensus_reached = False
        
        # Dynamic counter: each position maps {character: count}
        # Example: {0: {'A': 3, 'B': 1}, 1: {'B': 4}, ...}
        self.counter = {}

        # Tracking of already decided characters: {position: character}
        self.decided_chars = {}

        # Threshold for decision (how many times it needs to appear)
        self.decision_threshold = 8

        # Minimum percentage of decided positions for consensus (80%)
        self.consensus_percentage = 0.8

        # Maximum frames to process before returning best result
        self.max_frames = 40
        
        # Counter for processed frames
        self.frames_processed = 0
        
        # Track text lengths to find most common length
        self.length_counter = {}  # {length: count}

        # Best crop so far
        self.best_crop = None
        self.best_confidence = 0.0
        
        # Store all candidate crops for later selection based on final text similarity
        # Each entry: {"crop": np.array, "text": str, "confidence": float}
        self.candidate_crops = []

        self.crop_storage = ImageStorage(MINIO_CONF, BUCKET_NAME)
        self.crop_fails = ImageStorage(MINIO_CONF, "failed-crops")

        # Initialize Kafka
        logger.info(f"[AgentB/Kafka] Connecting to kafka via '{KAFKA_BOOTSTRAP}' …")

        # Kafka Consumer configuration
        self.consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": "agentB-group",
            "auto.offset.reset": "latest",  # "latest" to fetch the latest available message
            "enable.auto.commit": True,  # to read in real-time
            "session.timeout.ms": 10000,
            "max.poll.interval.ms": 300000,
        })

        self.consumer.subscribe([TOPIC_CONSUME])

        # Kafka Producer configuration
        self.producer = Producer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
        })
        
        # --- Prometheus Metrics ---
        self.inference_latency = Histogram(
            'agent_b_inference_latency_seconds', 
            'Time spent running YOLO (LP) inference',
            buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0]
        )
        self.frames_processed = Counter(
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
        
        # Start Prometheus metrics server
        # logger.info("[AgentB] Starting Prometheus metrics server on port 8000")
        # start_http_server(8000) - Started in init.py

    def _reset_consensus_state(self):
        """Resets the consensus algorithm state."""
        self.counter = {}
        self.decided_chars = {}
        self.consensus_reached = False
        self.best_crop = None
        self.best_confidence = 0.0
        self.candidate_crops = []  # Reset candidate crops
        self.frames_processed = 0
        self.length_counter = {}
        logger.debug("[AgentB] Consensus state reset.")

    def _get_frames(self, num_frames=30):
        """
        Captures a burst of frames from the RTMP/RTSP stream.
        
        Args:
            num_frames: The number of frames to buffer for processing.
        """
        # Connect to stream if not already
        if self.stream is None:
            logger.info(
                f"[AgentB] Connecting to RTMP stream (via Nginx): {STREAM_HIGH}")
            try:
                self.stream = StreamReader(STREAM_HIGH)
            
            except Exception as e:
                logger.exception(f"[AgentB] Failed to connect to stream: {e}")
                return

        logger.info(f"[AgentB] Reading {num_frames} frame(s) from RTMP…")

        captured = 0
        while captured < num_frames and self.running:
            try:
                frame = self.stream.read()
                if frame is not None:
                    self.frames_queue.put(frame)
                    captured += 1
                    logger.debug(f"[AgentB] Captured {captured}/{num_frames}.")
                
                else:
                    logger.debug("[AgentB] No frame yet, trying again…")
                    time.sleep(0.1)
            
            except Exception as e:
                logger.exception(f"[AgentB] Error when capturing frame {e}")
                time.sleep(0.2)

    def _get_next_frame(self):
        """
        Gets the next frame from the queue, capturing more if needed.
        Returns the frame or None if no frames available.
        """
        if self.frames_queue.empty():
            logger.debug("[AgentB] Frames queue is empty, capturing more frames.")
            self._get_frames(5)
        
        if self.frames_queue.empty():
            logger.warning("[AgentB] No frame captured from RTSP.")
            return None
        
        try:
            frame = self.frames_queue.get_nowait()
            logger.debug("[AgentB] Frame obtained from queue.")
            return frame
        except Empty:
            logger.warning("[AgentB] Frames queue is empty.")
            time.sleep(0.05)
            return None

    def _clear_frames_queue(self):
        """Clears all remaining frames from the queue."""
        remaining = self.frames_queue.qsize()
        if remaining > 0:
            logger.debug(f"[AgentB] Clearing {remaining} remaining frames from queue")
            while not self.frames_queue.empty():
                try:
                    self.frames_queue.get_nowait()
                except Empty:
                    break

    def _should_continue_processing(self) -> bool:
        """Checks if frame processing should continue."""
        return self.running and not self.consensus_reached and self.frames_processed < self.max_frames

    def process_license_plate_detection(self):
        """
        Main pipeline to detect and extract license plate text.
        
        Returns:
            tuple: (plate_text, confidence, crop_image) or (None, None, None)
        """
        logger.info("[AgentB] Starting license plate pipeline detection process…")
        self._reset_consensus_state()

        while self._should_continue_processing():
            frame = self._get_next_frame()
            if frame is None:
                return None, None, None

            self.frames_processed += 1
            logger.debug(f"[AgentB] Processing frame {self.frames_processed}/{self.max_frames}")

            result = self._process_single_frame(frame)
            if result:
                text, conf, crop = result
                logger.info(f"[AgentB] Consensus reached: '{text}' (conf={conf:.2f})")
                self._clear_frames_queue()
                return text, conf, crop

        if self.frames_processed >= self.max_frames:
            logger.info(f"[AgentB] Frame limit reached ({self.max_frames}), returning best partial result")

        return self._get_best_partial_result()

    def _run_yolo_detection(self, frame):
        """
        Runs YOLO detection on a frame.
        Returns boxes list or None if no detection.
        """
        logger.info("[AgentB] YOLO (LP) running…")
        with self.inference_latency.time():
            results = self.yolo.detect(frame)
        
        self.frames_processed += 1

        if not results:
            logger.debug("[AgentB] YOLO did not return a result for this frame.")
            return None

        if not self.yolo.object_found(results):
            logger.info("[AgentB] No license plate detected for this frame.")
            return None

        boxes = self.yolo.get_boxes(results)
        logger.info(f"[AgentB] {len(boxes)} license plates detected.")
        return boxes

    def _is_valid_license_plate_box(self, box, frame, box_index: int):
        """
        Validates a detection box and extracts crop if valid license plate.
        Returns (crop, confidence) or (None, None) if invalid.
        """
        x1, y1, x2, y2, conf = map(float, box)

        if conf < 0.4:
            logger.info(f"[AgentB] Ignored low confidence box (conf={conf:.2f}).")
            return None, None

        crop = frame[int(y1):int(y2), int(x1):int(x2)]
        classification = self.classifier.classify(crop)

        if classification == PlateClassifier.HAZARD_PLATE:
            logger.info(f"[AgentB] Crop {box_index} rejected as {classification}, uploading to MinIO for analysis.")
            return None, None

        logger.info(f"[AgentB] Crop {box_index} accepted as LICENSE_PLATE")
        self.plates_detected.inc()
        return crop, conf

    def _process_ocr_result(self, crop, crop_index: int):
        """
        Runs OCR on crop and processes result.
        Returns (final_text, confidence, best_crop) if consensus reached, else None.
        """
        logger.info("[AgentB] OCR extracting text…")
        text, ocr_conf = self.ocr._extract_text(crop)

        if not text or ocr_conf <= 0.0:
            logger.debug(f"[AgentB] OCR returned no valid text for crop {crop_index}")
            return None

        logger.info(f"[AgentB] OCR: '{text}' (conf={ocr_conf:.2f})")
        self.ocr_confidence.observe(ocr_conf)

        # Store candidate crop
        text_normalized = text.upper().replace("-", "")
        self.candidate_crops.append({
            "crop": crop.copy(),
            "text": text_normalized,
            "confidence": ocr_conf
        })
        logger.debug(f"[AgentB] Added candidate crop: '{text_normalized}' (conf={ocr_conf:.2f})")

        self._add_to_consensus(text, ocr_conf)

        if self._check_full_consensus():
            final_text = self._build_final_text()
            logger.info(f"[AgentB] Full consensus achieved: '{final_text}'")
            best_crop = self._select_best_crop(final_text)
            return final_text, 1.0, best_crop

        return None

    def _process_single_frame(self, frame):
        """
        Processes a single video frame.
        Returns (text, conf, crop) if consensus is reached, else None.
        """
        try:
            boxes = self._run_yolo_detection(frame)
            if boxes is None:
                return None

            for i, box in enumerate(boxes, start=1):
                crop, _ = self._is_valid_license_plate_box(box, frame, i)
                if crop is None:
                    continue

                try:
                    result = self._process_ocr_result(crop, i)
                    if result:
                        return result
                except Exception as e:
                    logger.exception(f"[AgentB] OCR failure: {e}")

        except Exception as e:
            logger.exception(f"[AgentB] Error processing frame: {e}")

        return None

    def _normalize_text(self, text: str) -> str:
        """Normalizes text for consensus: uppercase and remove dashes."""
        return text.upper().replace("-", "")

    def _is_valid_for_consensus(self, text_normalized: str, confidence: float) -> bool:
        """Checks if OCR result is valid for consensus algorithm."""
        if confidence < 0.80:
            logger.debug(f"[AgentB] Confidence too low ({confidence:.2f}), skipping")
            return False

        if len(text_normalized) < 4:
            logger.debug(f"[AgentB] Text too short ('{text_normalized}'), skipping")
            return False

        return True

    def _track_text_length(self, text_len: int) -> bool:
        """
        Tracks text length and validates against most common length.
        Returns True if text length is acceptable, False otherwise.
        """
        if text_len not in self.length_counter:
            self.length_counter[text_len] = 0
        self.length_counter[text_len] += 1

        if sum(self.length_counter.values()) < 3:
            return True

        most_common_length = max(self.length_counter.items(), key=lambda x: x[1])[0]
        if text_len != most_common_length:
            logger.debug(
                f"[AgentB] Text length mismatch: {text_len} chars, "
                f"expected {most_common_length} (most common). Skipping to avoid misalignment.")
            return False

        return True

    def _get_vote_weight(self, confidence: float) -> int:
        """Returns vote weight based on confidence level."""
        return 2 if confidence >= 0.95 else 1

    def _update_position_decision(self, pos: int, char: str):
        """Updates decision for a character position if threshold reached."""
        if self.counter[pos][char] < self.decision_threshold:
            return

        if pos not in self.decided_chars:
            self.decided_chars[pos] = char
            logger.debug(f"[AgentB] Position {pos} decided: '{char}'")
        elif self.decided_chars[pos] != char:
            old_char = self.decided_chars[pos]
            self.decided_chars[pos] = char
            logger.debug(f"[AgentB] Position {pos} changed: '{old_char}' -> '{char}'")

    def _add_to_consensus(self, text: str, confidence: float):
        """
        Adds OCR result to consensus algorithm.
        Votes for each character at its position.
        """
        text_normalized = self._normalize_text(text)

        if not self._is_valid_for_consensus(text_normalized, confidence):
            return

        if not self._track_text_length(len(text_normalized)):
            return

        logger.debug(
            f"[AgentB] Adding to consensus: '{text_normalized}' (conf={confidence:.2f}, len={len(text_normalized)})")

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
        Checks if consensus reached based on percentage of decided positions.
        Example: if 8 positions and 80% = 6.4, needs 7 decided positions.
        """
        if not self.counter:
            return False

        total_positions = len(self.counter)
        decided_count = len(self.decided_chars)

        # Calculate how many positions need to be decided (round up)
        import math
        required_positions = math.ceil(
            total_positions * self.consensus_percentage)

        if decided_count >= required_positions:
            logger.info(
                f"[AgentB] Consensus reached! {decided_count}/{total_positions} positions decided (need {required_positions}) ✓")
            self.consensus_reached = True
            return True

        logger.debug(
            f"[AgentB] Consensus check: {decided_count}/{total_positions} positions decided (need {required_positions})")
        return False


    def _build_final_text(self) -> str:
        """Builds final text from decided characters."""
        if not self.decided_chars:
            return ""

        # Build text in position order
        text_chars = []
        for pos in sorted(self.decided_chars.keys()):
            text_chars.append(self.decided_chars[pos])

        final_text = "".join(text_chars)
        logger.debug(f"[AgentB] Built final text: '{final_text}'")

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
        Selects the best crop based on:
        1. Similarity to final consensus text (lower Levenshtein distance is better)
        2. OCR confidence as tiebreaker
        
        Returns the crop image or None.
        """
        if not self.candidate_crops:
            logger.warning("[AgentB] No candidate crops available")
            return None
        
        if not final_text:
            # Fallback to highest confidence if no final text
            best = max(self.candidate_crops, key=lambda x: x["confidence"])
            logger.debug(f"[AgentB] No final text, using highest confidence crop: '{best['text']}'")
            return best["crop"]
        
        # Calculate scores for each candidate
        scored_crops = []
        for candidate in self.candidate_crops:
            distance = self._levenshtein_distance(candidate["text"], final_text)
            # Normalize distance (0 = exact match, higher = worse)
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
        logger.info(
            f"[AgentB] Selected best crop: '{best['text']}' "
            f"(similarity={best['similarity']:.2f}, distance={best['distance']}, conf={best['confidence']:.2f}) "
            f"for final text '{final_text}'"
        )
        
        # Store for later reference
        self.best_crop = best["crop"]
        self.best_confidence = best["confidence"]
        
        return best["crop"]


    def _get_best_partial_result(self):
        """
        Returns best partial result if full consensus not reached.
        Fills undecided positions with most voted character.
        """
        if not self.counter:
            logger.warning(
                "[AgentB] No valid license plates detected in any frame.")
            return None, None, None

        # Build text with decided positions + best candidates
        text_chars = []
        total_positions = max(self.counter.keys()) + 1

        for pos in range(total_positions):
            if pos in self.decided_chars:
                # Use decided character
                text_chars.append(self.decided_chars[pos])
            elif pos in self.counter and self.counter[pos]:
                # Use character with most votes
                best_char = max(
                    self.counter[pos].items(), key=lambda x: x[1])[0]
                text_chars.append(best_char)
            else:
                # Position without data (unlikely)
                text_chars.append("_")

        partial_text = "".join(text_chars)

        # Calculate confidence based on percentage of decided positions
        decided_count = len(self.decided_chars)
        confidence = decided_count / total_positions
        # Maximum 0.95 for partial result
        confidence = min(confidence, 0.95)

        # Select best crop based on similarity to partial text
        best_crop = self._select_best_crop(partial_text)

        logger.info(
            f"[AgentB] Partial result: '{partial_text}' ({decided_count}/{total_positions} decided, conf={confidence:.2f})")

        return partial_text, confidence, best_crop

    def _delivery_callback(self, err: Optional[KafkaError], msg) -> None:
        """
        Callback for Kafka message delivery confirmation.
        
        Args:
            err: Error object if delivery failed
            msg: Message object with metadata
        """

        if err is not None:
            logger.error(
                f"[AgentB/Kafka] Message delivery failed: {err} "
                f"(topic={msg.topic()}, partition={msg.partition()})"
            )
        else:
            logger.debug(
                f"[AgentB/Kafka] Message delivered successfully to "
                f"{msg.topic()}[{msg.partition()}] at offset {msg.offset()}"
            )
    
    def _publish_lp_detected(self, truck_id, plate_text, plate_conf, crop_url):
        """
        Publishes the 'license-plate-detected' event to Kafka.
        Propagates the correlation ID and includes MinIO crop URL.
        """
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Construct JSON payload
        payload = {
            "timestamp": timestamp,
            "licensePlate": plate_text,
            "confidence": float(plate_conf if plate_conf is not None else 0.0),
            "cropUrl": crop_url
        }
        
        logger.info(
            f"[AgentB] Publishing '{TOPIC_PRODUCE}' (truckId={truck_id}, plate={plate_text}) …")

        # Send to Kafka
        self.producer.produce(
            topic=TOPIC_PRODUCE,
            key=None,
            value=json.dumps(payload).encode("utf-8"),
            headers={"truckId": truck_id},
            callback=self._delivery_callback
        )

        self.producer.poll(0)

    def _poll_latest_message(self):
        """
        Polls Kafka for the latest message, skipping old ones.
        Returns the latest message or None.
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
                logger.info(f"[AgentB] Skipped {skipped} old messages, processing latest only")
            return msgs_buffer[-1]
        
        # Wait for new message if buffer was empty
        return self.consumer.poll(timeout=1.0)

    def _extract_truck_id(self, msg) -> str:
        """
        Extracts truckId from message headers.
        Returns truckId or generates a new UUID if not found.
        """
        for k, v in (msg.headers() or []):
            if k == "truckId" and v is not None:
                return v.decode() if isinstance(v, (bytes, bytearray)) else str(v)
        return str(uuid.uuid4())

    def _upload_crop_to_storage(self, truck_id: str, plate_text: str) -> Optional[str]:
        """
        Uploads the best crop to MinIO storage.
        Returns the crop URL or None if upload fails.
        """
        if self.best_crop is None:
            return None
        
        try:
            object_name = f"lp_{truck_id}_{plate_text}.jpg"
            crop_url = self.crop_storage.upload_memory_image(self.best_crop, object_name)
            
            if crop_url:
                logger.info(f"[AgentB] Crop Final Consensus: {crop_url}")
            else:
                logger.warning("[AgentB] Failed to upload crop to MinIO")
            
            return crop_url
        except Exception as e:
            logger.exception(f"[AgentB] Error uploading crop to MinIO: {e}")
            return None

    def _process_message(self, msg):
        """
        Processes a single Kafka message and handles license plate detection.
        """
        
        # Extract truck ID
        truck_id = self._extract_truck_id(msg)
        logger.info(f"[AgentB] Received 'truck-detected' (truckId={truck_id}). Starting LP pipeline…")
        
        # Run detection pipeline
        plate_text, plate_conf, _lp_img = self.process_license_plate_detection()
        
        # Handle empty results
        if not plate_text:
            logger.warning("[AgentB] No final text results — publishing empty message.")
            self._publish_lp_detected(truck_id, "N/A", -1, None)
            return
        
        # Upload crop to storage
        crop_url = self._upload_crop_to_storage(truck_id, plate_text)
        
        # Publish results
        self._publish_lp_detected(truck_id, plate_text, plate_conf, crop_url)
        
        # Clear frames queue for next detection
        with self.frames_queue.mutex:
            self.frames_queue.queue.clear()

    def _cleanup_resources(self):
        """Releases all resources gracefully."""
        logger.info("[AgentB] Freeing resources…")
        
        # Release stream
        try:
            if self.stream is not None:
                self.stream.release()
                logger.debug("[AgentB] RTMP stream released.")
        except Exception as e:
            logger.exception(f"[AgentB] Error releasing RTMP stream: {e}")
        
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
        """Main loop for Agent B."""
        logger.info(f"[AgentB] Main loop starting… (topic in='{TOPIC_CONSUME}')")

        try:
            while self.running:
                msg = self._poll_latest_message()
                
                if msg is None or msg.error():
                    continue
                
                self._process_message(msg)
                
        except KeyboardInterrupt:
            logger.info("[AgentB] Interrupted by user.")
        except KafkaException as e:
            logger.exception(f"[AgentB/Kafka] Kafka error: {e}")
        except Exception as e:
            logger.exception(f"[AgentB] Unexpected error: {e}")
        finally:
            self._cleanup_resources()

    def stop(self):
        """Gracefully stop Agent B."""
        logger.info("[AgentB] Stopping agent…")
        self.running = False
