from agentC_microservice.src.RTSPstream import RTSPStream
from agentC_microservice.src.YOLO_Hazard_Plate import *
from agentC_microservice.src.PaddleOCR import *
from agentC_microservice.src.CropStorage import CropStorage
from agentC_microservice.src.PlateClassifier import PlateClassifier

import os
import time
import cv2
import json
import uuid
from queue import Queue, Empty
from confluent_kafka import Producer, Consumer, KafkaException, KafkaError
import logging
from typing import Optional, Tuple

# --- Configuration ---
# Load environment variables or fallback to default network settings
NGINX_RTMP_HOST = os.getenv("NGINX_RTMP_HOST", "10.255.32.35")
NGINX_RTMP_PORT = os.getenv("NGINX_RTMP_PORT", "1935")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "10.255.32.143:9092")
GATE_ID = os.getenv("GATE_ID", "gate01")
RTSP_STREAM_HIGH = os.getenv("RTSP_STREAM_HIGH", f"rtmp://{NGINX_RTMP_HOST}:{NGINX_RTMP_PORT}/streams_high/{GATE_ID}")

# MinIO Configuration
MINIO_HOST = os.getenv("MINIO_HOST", "10.255.32.132")
MINIO_PORT = os.getenv("MINIO_PORT", "9000")

MINIO_CONF = {
    "endpoint": f"{MINIO_HOST}:{MINIO_PORT}",
    "access_key": os.getenv("ACCESS_KEY"),
    "secret_key": os.getenv("SECRET_KEY"),
    "secure": False  # use HTTPS
}

BUCKET_NAME = os.getenv("BUCKET_NAME", "hz-crops")

# --- Operational Constants ---
MAX_CONNECTION_RETRIES = 10
RETRY_DELAY = 5  # seconds
TOPIC_CONSUME = f"truck-detected-{GATE_ID}"
TOPIC_PRODUCE = f"hz-results-{GATE_ID}"

logger = logging.getLogger("AgentC")


class AgentC:
    """
    Agent C:
    - Consumes 'truck-detected' events from Kafka.
    - Upon receipt, connects to/reads from the High-Quality RTSP stream.
    - Detects hazard plates using YOLO and extracts text using OCR.
    - Uses a consensus algorithm to validate characters across multiple frames.
    - Publishes 'hazard-plate-detected' to Kafka, propagating the truckId.
    """

    def __init__(self):
        # Initialize models
        self.yolo = YOLO_Hazard_Plate()
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

        self.crop_storage = CropStorage(MINIO_CONF, BUCKET_NAME)

        # Initialize Kafka
        logger.info(f"[AgentC/Kafka] Connecting to kafka via '{KAFKA_BOOTSTRAP}' …")

        # Kafka Consumer configuration
        self.consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": "agentC-group",
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

    def _reset_consensus_state(self):
        """Resets the consensus algorithm state."""
        self.counter = {}
        self.decided_chars = {}
        self.consensus_reached = False
        self.best_crop = None
        self.best_confidence = 0.0
        self.frames_processed = 0
        self.length_counter = {}
        logger.debug("[AgentC] Consensus state reset.")

    def _get_frames(self, num_frames=30):
        """
        Captures a burst of frames from the RTMP/RTSP stream.
        
        Args:
            num_frames: The number of frames to buffer for processing.
        """
        # Connect to stream if not already
        if self.stream is None:
            logger.info(
                f"[AgentC] Connecting to RTMP stream (via Nginx): {RTSP_STREAM_HIGH}")
            try:
                self.stream = RTSPStream(RTSP_STREAM_HIGH)
            
            except Exception as e:
                logger.exception(f"[AgentC] Failed to connect to stream: {e}")
                return

        logger.info(f"[AgentC] Reading {num_frames} frame(s) from RTMP…")

        captured = 0
        while captured < num_frames and self.running:
            try:
                frame = self.stream.read()
                if frame is not None:
                    self.frames_queue.put(frame)
                    captured += 1
                    logger.debug(f"[AgentC] Captured {captured}/{num_frames}.")
                
                else:
                    logger.debug("[AgentC] No frame yet, trying again…")
                    time.sleep(0.1)
            
            except Exception as e:
                logger.exception(f"[AgentC] Error when capturing frame {e}")
                time.sleep(0.2)

    def process_hazard_plate_detection(self, truck_id: str):
        """
        Main pipeline to detect and extract license plate text.
        
        Returns:
            tuple: (plate_text, confidence, crop_image) or (None, None, None)
        """
        logger.info(
            "[AgentC] Starting license plate pipeline detection process…")

        # Reset consensus state before starting new detection
        self._reset_consensus_state()

        # Process frames until consensus is reached, frame limit reached, or queue is empty
        while self.running and not self.consensus_reached and self.frames_processed < self.max_frames:
            # Ensure there are frames to process
            if self.frames_queue.empty():
                logger.debug("[AgentC] Frames queue is empty, capturing more frames.")
                self._get_frames(5)

            # return None if no frames were returned
            if self.frames_queue.empty():
                logger.warning("[AgentC] No frame captured from RTSP.")
                return None, None, None
            
            try:
                frame = self.frames_queue.get_nowait()
                logger.debug("[AgentC] Frame obtained from queue.")

            except Empty:
                logger.warning("[AgentC] Frames queue is empty.")
                time.sleep(0.05)
                continue

            # Increment frame counter
            self.frames_processed += 1
            logger.debug(f"[AgentC] Processing frame {self.frames_processed}/{self.max_frames}")

            # Process single frame
            result = self._process_single_frame(frame, truck_id)

            # If full consensus reached, return immediately
            if result:
                text, conf, crop = result
                logger.info(
                    f"[AgentC] Consensus reached: '{text}' (conf={conf:.2f})")

                # Clear remaining frames from queue
                remaining = self.frames_queue.qsize()
                if remaining > 0:
                    logger.debug(f"[AgentC] Clearing {remaining} remaining frames from queue")
                    while not self.frames_queue.empty():
                        try:
                            self.frames_queue.get_nowait()
                        except Empty:
                            break

                return text, conf, crop

        # Check if frame limit reached
        if self.frames_processed >= self.max_frames:
            logger.info(f"[AgentC] Frame limit reached ({self.max_frames}), returning best partial result")

        # If full consensus not reached, return best partial result
        return self._get_best_partial_result()

    def _process_single_frame(self, frame, truck_id: str):
        """
        Processes a single video frame.
        Returns (text, conf, crop) if consensus is reached, else None.
        """

        try:
            logger.info("[AgentC] YOLO (LP) running…")
            results = self.yolo.detect(frame)

            if not results:
                logger.debug(
                    "[AgentC] YOLO did not return a result for this frame.")
                return None

            if not self.yolo.found_hazard_plate(results):
                logger.info(
                    "[AgentC] No license plate detected for this frame.")
                return None

            boxes = self.yolo.get_boxes(results)
            logger.info(f"[AgentC] {len(boxes)} license plates detected.")

            for i, box in enumerate(boxes, start=1):
                x1, y1, x2, y2, conf = map(float, box)

                if conf < 0.4:
                    logger.info(
                        f"[AgentC] Ignored low confidence box (conf={conf:.2f}).")
                    continue

                # Extract Crop
                crop = frame[int(y1):int(y2), int(x1):int(x2)]


                logger.info(f"[AgentC] Crop {i} accepted as LICENSE_PLATE")
                # ============================================================
                # Run OCR
                logger.info("[AgentC] OCR extracting text…")
                try:
                    text, ocr_conf = self.ocr._extract_text(crop)

                    if not text or ocr_conf <= 0.0:
                        logger.debug(
                            f"[AgentC] OCR returned no valid text for crop {i}")
                        continue

                    logger.info(
                        f"[AgentC] OCR: '{text}' (conf={ocr_conf:.2f})")

                    # Update best crop
                    if ocr_conf > self.best_confidence:
                        self.best_crop = crop
                        self.best_confidence = ocr_conf

                    # Add to consensus
                    self._add_to_consensus(text, ocr_conf)

                    # Check if consensus reached
                    if self._check_full_consensus():
                        final_text = self._build_final_text()
                        logger.info(
                            f"[AgentC] Full consensus achieved: '{final_text}'")
                        return final_text, 1.0, crop

                except Exception as e:
                    logger.exception(f"[AgentC] OCR failure: {e}")

        except Exception as e:
            logger.exception(f"[AgentC] Error processing frame: {e}")

        return None

    def _add_to_consensus(self, text: str, confidence: float):
        """
        Adds OCR result to consensus algorithm.
        Votes for each character at its position.
        """

        # Ignore low confidences
        if confidence < 0.80:
            logger.debug(
                f"[AgentC] Confidence too low ({confidence:.2f}), skipping")
            return

        # Normalize text (uppercase, remove only dashes, keep spaces for position tracking)
        text_normalized = text.upper().replace("-", "")

        # Ignore if too short
        if len(text_normalized) < 4:
            logger.debug(
                f"[AgentC] Text too short ('{text_normalized}'), skipping")
            return
        
        # Track the length of this text
        text_len = len(text_normalized)
        if text_len not in self.length_counter:
            self.length_counter[text_len] = 0
        self.length_counter[text_len] += 1
        
        # After collecting some samples, only accept the most common length
        # This prevents mixing "0N25" (4 chars) with "A0N25" (5 chars)
        if sum(self.length_counter.values()) >= 3:
            most_common_length = max(self.length_counter.items(), key=lambda x: x[1])[0]
            if text_len != most_common_length:
                logger.debug(
                    f"[AgentC] Text length mismatch: '{text_normalized}' has {text_len} chars, "
                    f"expected {most_common_length} (most common). Skipping to avoid misalignment.")
                return

        logger.debug(
            f"[AgentC] Adding to consensus: '{text_normalized}' (conf={confidence:.2f}, len={text_len})")

        # Dynamically expand dictionary for new positions
        for pos in range(len(text_normalized)):
            if pos not in self.counter:
                self.counter[pos] = {}

        # Add each character to consensus at correct position
        for pos, char in enumerate(text_normalized):
            if char not in self.counter[pos]:
                self.counter[pos][char] = 0

            # Confidence-weighted votes
            if confidence >= 0.95:
                self.counter[pos][char] += 2
            else:
                self.counter[pos][char] += 1

            # Check if this position reached threshold
            if self.counter[pos][char] >= self.decision_threshold:
                if pos not in self.decided_chars:
                    self.decided_chars[pos] = char
                    logger.debug(f"[AgentC] Position {pos} decided: '{char}'")
                elif self.decided_chars[pos] != char:
                    # If changed, update
                    old_char = self.decided_chars[pos]
                    self.decided_chars[pos] = char
                    logger.debug(
                        f"[AgentC] Position {pos} changed: '{old_char}' -> '{char}'")


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
                f"[AgentC] Consensus reached! {decided_count}/{total_positions} positions decided (need {required_positions})")
            self.consensus_reached = True
            return True

        logger.debug(
            f"[AgentC] Consensus check: {decided_count}/{total_positions} positions decided (need {required_positions})")
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
        logger.debug(f"[AgentC] Built final text: '{final_text}'")

        return final_text


    def _get_best_partial_result(self):
        """
        Returns best partial result if full consensus not reached.
        Fills undecided positions with most voted character.
        """
        if not self.counter:
            logger.warning(
                "[AgentC] No valid license plates detected in any frame.")
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

        logger.info(
            f"[AgentC] Partial result: '{partial_text}' ({decided_count}/{total_positions} decided, conf={confidence:.2f})")

        return partial_text, confidence, self.best_crop

    def _delivery_callback(self, err: Optional[KafkaError], msg) -> None:
        """
        Callback for Kafka message delivery confirmation.
        
        Args:
            err: Error object if delivery failed
            msg: Message object with metadata
        """

        if err is not None:
            logger.error(
                f"[AgentC/Kafka] Message delivery failed: {err} "
                f"(topic={msg.topic()}, partition={msg.partition()})"
            )
        else:
            logger.debug(
                f"[AgentC/Kafka] Message delivered successfully to "
                f"{msg.topic()}[{msg.partition()}] at offset {msg.offset()}"
            )
    
    def _publish_hz_detected(self, truck_id, plate_text, plate_conf, crop_url):
        """
        Publishes the 'license-plate-detected' event to Kafka.
        Propagates the correlation ID and includes MinIO crop URL.
        """
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Construct JSON payload
        payload = {
            "timestamp": timestamp,
            "hazardPlate": plate_text,
            "confidence": float(plate_conf if plate_conf is not None else 0.0),
            "cropUrl": crop_url
        }
        
        logger.info(
            f"[AgentC] Publishing '{TOPIC_PRODUCE}' (truckId={truck_id}, plate={plate_text}) …")

        # Send to Kafka
        self.producer.produce(
            topic=TOPIC_PRODUCE,
            key=None,
            value=json.dumps(payload).encode("utf-8"),
            headers={"truckId": truck_id},
            callback=self._delivery_callback
        )

        self.producer.poll(0)

    def _loop(self):
        """Main loop for Agent B."""
        logger.info(
            f"[AgentC] Main loop starting… (topic in='{TOPIC_CONSUME}')")

        try:
            while self.running:
                # SKIP OLD MESSAGES - Process only the latest
                msg = None
                msgs_buffer = []

                # Poll multiple times to drain old messages
                while True:
                    temp_msg = self.consumer.poll(timeout=0.1)
                    if temp_msg is None:
                        break  # No more messages
                    if temp_msg.error():
                        continue
                    msgs_buffer.append(temp_msg)

                # If there are messages, take only the last one
                if msgs_buffer:
                    msg = msgs_buffer[-1]  # Last message in buffer
                    skipped = len(msgs_buffer) - 1
                    if skipped > 0:
                        logger.info(
                            f"[AgentC] Skipped {skipped} old messages, processing latest only")
                else:
                    # Wait for new message
                    msg = self.consumer.poll(timeout=1.0)

                if msg is None:
                    continue
                if msg.error():
                    continue

                # Parse Input Payload
                try:
                    data = json.loads(msg.value())
                except json.JSONDecodeError:
                    logger.warning("[AgentC] Invalid message (JSON). Ignored.")
                    continue

                # Extract truckId (Propagate if exists)
                truck_id = None
                for k, v in (msg.headers() or []):
                    if k == "truckId" and v is not None:
                        truck_id = v.decode() if isinstance(v, (bytes, bytearray)) else str(v)
                        break
                if truck_id is None:
                    truck_id = str(uuid.uuid4())

                logger.info(
                    f"[AgentC] Received 'truck-detected' (truckId={truck_id}). Starting LP pipeline…")

                # Process license plate detection
                plate_text, plate_conf, _lp_img = self.process_hazard_plate_detection(truck_id)

                if not plate_text:
                    logger.warning("[AgentC] No final text results — publishing empty message.")
                    self._publish_hz_detected(truck_id, "N/A", -1, None)
                    continue
                
                # Upload best crop to MinIO
                crop_url = None
                if self.best_crop is not None:
                    try:
                        # Generate unique object name
                        object_name = f"lp_{truck_id}_{plate_text}.jpg"
                        crop_url = self.crop_storage.upload_memory_image(self.best_crop, object_name)
                        
                        if crop_url:
                            logger.info(f"[AgentC] Crop Final Consensus: {crop_url}")
                        else:
                            logger.warning("[AgentC] Failed to upload crop to MinIO")
                    except Exception as e:
                        logger.exception(f"[AgentC] Error uploading crop to MinIO: {e}")
                
                # Publish the license plate detected message
                self._publish_hz_detected(
                    truck_id=truck_id,
                    plate_text=plate_text,
                    plate_conf=plate_conf,
                    crop_url=crop_url
                )

                # Clear frames queue for next detection
                with self.frames_queue.mutex:
                    self.frames_queue.queue.clear()
                
        except KeyboardInterrupt:
            logger.info("[AgentC] Interrupted by user.")
        except KafkaException as e:
            logger.exception(f"[AgentC/Kafka] Kafka error: {e}")
        except Exception as e:
            logger.exception(f"[AgentC] Unexpected error: {e}")
        finally:
            logger.info("[AgentC] Freeing resources…")
            try:
                if self.stream is not None:
                    self.stream.release()
                    logger.debug("[AgentC] RTMP stream released.")
            except Exception as e:
                logger.exception(f"[AgentC] Error releasing RTMP stream: {e}")
            try:
                self.producer.flush(5)
            except Exception:
                pass
            try:
                self.consumer.close()
            except Exception:
                pass

    def stop(self):
        """Gracefully stop Agent C."""
        logger.info("[AgentC] Stopping agent…")
        self.running = False
