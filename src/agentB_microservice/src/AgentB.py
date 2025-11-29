from agentB_microservice.src.RTSPstream import RTSPStream
from agentB_microservice.src.YOLO_License_Plate import *
from agentB_microservice.src.OCR import *
from agentB_microservice.src.CropStorage import CropStorage

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
MINIO_CONF = {
    "endpoint": os.getenv("MINIO_HOST"),
    "access_key": os.getenv("ACCESS_KEY"),
    "secret_key": os.getenv("SECRET_KEY"),
    "secure": True  #use HTTPS
}

BUCKET_NAME = os.getenv("BUCKET_NAME", "lp-crops")

# --- Operational Constants ---
MAX_CONNECTION_RETRIES = 10
RETRY_DELAY = 5  # seconds
TOPIC_CONSUME = f"truck-detected-{GATE_ID}"
TOPIC_PRODUCE = "lp-results-{GATE_ID}"

logger = logging.getLogger("AgentB")


class AgentB:
    """
    Agent B:
    - Consumes 'truck-detected' events from Kafka.
    - Upon receipt, connects to/reads from the High-Quality RTSP stream.
    - Detects license plates using YOLO and extracts text using OCR.
    - Uses a consensus algorithm to validate characters across multiple frames.
    - Publishes 'license-plate-detected' to Kafka, propagating the correlationId.
    """

    def __init__(self):
        # Initialize models
        self.yolo = YOLO_License_Plate()
        self.ocr = OCR()
        self.running = True
        self.frames_queue = Queue()

        # Connect on-demand when a Kafka event is received.
        self.stream = None

        # --- Consensus State Initialization ---
        # Counter for consensus: each position (0-7) maps to character votes
        self.counter = {
            0: {},  # Position 0
            1: {},  # Position 1
            2: {},  # Position 2
            3: {},  # Position 3
            4: {},  # Position 4
            5: {},  # Position 5
            6: {},  # Position 6 
            7: {}   # Position 7 
        }
        
        # Tracking decided characters and best crops
        self.decided_chars = {}
        self.decision_threshold = 5  # Votes required to confirm a character
        self.best_crop = None
        self.best_confidence = 0.0

        self.crop_storage = CropStorage(MINIO_CONF, BUCKET_NAME)

        # Initialize Kafka
        logger.info(f"[AgentB/Kafka] Connecting to kafka via '{KAFKA_BOOTSTRAP}' …")

        # Kafka Consumer configuration
        self.consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": "agentB-group",
            "auto.offset.reset": "latest",  # "latest" to get only new messages
            "enable.auto.commit": True,     # Real-time processing
            "session.timeout.ms": 10000,
            "max.poll.interval.ms": 300000,
        })

        self.consumer.subscribe([TOPIC_CONSUME])

        # Kafka Producer configuration
        self.producer = Producer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
        })

    def _reset_consensus_state(self):
        """Resets the internal state of the consensus algorithm."""
        for pos in self.counter:
            self.counter[pos] = {}
        
        self.decided_chars = {}
        self.best_crop = None
        self.best_confidence = 0.0

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
                f"[AgentB] Connecting to RTMP stream (via Nginx): {RTSP_STREAM_HIGH}")
            try:
                self.stream = RTSPStream(RTSP_STREAM_HIGH)
            
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

    def process_license_plate_detection(self):
        """
        Main pipeline to detect and extract license plate text.
        
        Returns:
            tuple: (plate_text, confidence, crop_image) or (None, None, None)
        """
        logger.info("[AgentB] Starting license plate pipeline detection process…")

        # Reset consensus state before starting new detection
        self._reset_consensus_state()
        
        # Capture frames
        self._get_frames(30)
        
        if self.frames_queue.empty():
            logger.warning("[AgentB] No frame captured from RTSP.")
            return None, None, None

        # Process frames until consensus is reached or queue is empty
        while self.running and not self.frames_queue.empty():
            try:
                frame = self.frames_queue.get_nowait()
                logger.debug("[AgentB] Frame obtained from queue.")

            except Empty:
                logger.warning("[AgentB] Frames queue is empty.")
                time.sleep(0.05)
                continue

            # Process single frame
            result = self._process_single_frame(frame)
            
            # If full consensus reached, return immediately
            if result:
                text, conf, crop = result
                logger.info(f"[AgentB] Consensus reached: '{text}' (conf={conf:.2f})")
                return text, conf, crop
        
        # If no full consensus, return the best partial result found
        return self._get_best_partial_result()

    def _process_single_frame(self, frame):
        """
        Processes a single video frame.
        Retuns (text, conf, crop) if consensus is reached, else None.
        """
        
        try:
            logger.info("[AgentB] YOLO (LP) running…")
            results = self.yolo.detect(frame)

            if not results:
                logger.debug("[AgentB] YOLO did not return a result for this frame.")
                return None

            if not self.yolo.found_license_plate(results):
                logger.info("[AgentB] No license plate detected for this frame.")
                return None

            boxes = self.yolo.get_boxes(results)
            logger.info(f"[AgentB] {len(boxes)} license plates detected.")

            for i, box in enumerate(boxes, start=1):
                x1, y1, x2, y2, conf = map(float, box)
                
                if conf < 0.75:
                    logger.info(f"[AgentB] Ignored low confidence box (conf={conf:.2f}).")
                    continue

                # Extract Crop
                crop = frame[int(y1):int(y2), int(x1):int(x2)]

                # Run OCR
                logger.info("[AgentB] OCR extracting text…")
                try:
                    text, ocr_conf = self.ocr._extract_text(crop)
                    
                    if not text or ocr_conf <= 0.0:
                        logger.debug(f"[AgentB] OCR returned no valid text for crop {i}")
                        continue
                    
                    logger.info(f"[AgentB] OCR: '{text}' (conf={ocr_conf:.2f})")
                    
                    # Update best crop
                    if ocr_conf > self.best_confidence:
                        self.best_crop = crop
                        self.best_confidence = ocr_conf
                    
                    # Add to consensus voting
                    self._add_to_consensus(text, ocr_conf)
                    
                    # Check if consensus has been reached
                    if self._check_full_consensus():
                        final_text = self._build_final_text()
                        logger.info(f"[AgentB] Full consensus achieved: '{final_text}'")
                        return final_text, 1.0, crop
                    
                except Exception as e:
                    logger.exception(f"[AgentB] OCR failure: {e}")

        except Exception as e:
            logger.exception(f"[AgentB] Error processing frame: {e}")
        
        return None

    def _add_to_consensus(self, text: str, confidence: float):
        """
        Adds an OCR result to the consensus voting algorithm.
        """
        # Ignore low confidence results
        if confidence < 0.5:
            logger.debug(f"[AgentB] Confidence too low ({confidence:.2f}), skipping")
            return

        logger.debug(f"[AgentB] Adding to consensus: '{text}'")

        # Expand dictionary if text has more positions than currently tracked
        for pos in range(len(text)):
            if pos not in self.counter:
                self.counter[pos] = {}

        # Vote for each character in the correct position
        for pos, char in enumerate(text):
            if char not in self.counter[pos]:
                self.counter[pos][char] = 0
            
            # Weighted voting: High confidence gets double vote
            if confidence >= 0.8:
                self.counter[pos][char] += 2
            else:
                self.counter[pos][char] += 1

            # Check consensus for this specific position
            if self.counter[pos][char] >= self.decision_threshold:
                if pos not in self.decided_chars:
                    self.decided_chars[pos] = char
                    logger.debug(f"[AgentB] Position {pos} decided: '{char}'")

    def _check_full_consensus(self) -> bool:
        """
        Checks if all necessary positions have been decided.
        """
        decided_count = len(self.decided_chars)
        total_simbols = len(self.counter)

        # Consider consensus reached if at least 6 characters are decided
        if decided_count == total_simbols:
            logger.debug(f"[AgentB] Consensus check: {decided_count}/6+ positions decided ✓")
            return True
        
        logger.debug(f"[AgentB] Consensus check: {decided_count}/6 positions decided")
        return False

    def _build_final_text(self) -> str:
        """Constructs the final text from the decided characters."""
        text_chars = []
        for pos in sorted(self.decided_chars.keys()):
            text_chars.append(self.decided_chars[pos])
        
        final_text = "".join(text_chars)
        return final_text
    
    def _get_best_partial_result(self):
        """
        Returns the best partial result if full consensus was not reached.
        """
        if not self.decided_chars:
            logger.warning("[AgentB] No valid license plates detected in any frame.")
            return None, None, None
        
        # Build partial text
        partial_text = self._build_partial_text()
        
        # Calculate confidence based on how many characters were decided
        confidence = len(self.decided_chars) / 6.0  # Normalize to 6 characters
        confidence = min(confidence, 0.95)  # Max 0.95 for partial result
        
        logger.info(f"[AgentB] Partial result: '{partial_text}' (conf={confidence:.2f})")
        
        return partial_text, confidence, self.best_crop

    def _build_partial_text(self) -> str:
        """
        Constructs partial text, filling undecided positions with '_'.
        """
        # Determine expected length
        max_pos = max(self.counter.keys())
        expected_length = max_pos
        
        # Heuristic: If the longest plate length appears rarely, assume standard size (max - 1)
        if len(self.counter[max_pos]) < 10:
            expected_length = max_pos - 1
        
        text_chars = []
        for pos in range(expected_length):
            if pos in self.decided_chars:
                text_chars.append(self.decided_chars[pos])
            else:
                # Use the character with the most votes, if any
                if pos in self.counter and self.counter[pos]:
                    # Get item with max count from dictionary
                    best_char = max(self.counter[pos].items(), key=lambda x: x[1])[0]
                    text_chars.append(best_char)
                else:
                    text_chars.append("_")
        
        final_text = "".join(text_chars)
        return final_text

    def _delivery_callback(self, err: Optional[KafkaError], msg) -> None:
        """
        Callback for Kafka message delivery confirmation.
        
        Args:
            err: Error object if delivery failed
            msg: Message object with metadata
        """

        if err is not None:
            logger.error(
                f"[AgentA/Kafka] Message delivery failed: {err} "
                f"(topic={msg.topic()}, partition={msg.partition()})"
            )
        else:
            logger.debug(
                f"[AgentA/Kafka] Message delivered successfully to "
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

    def _loop(self):
        """Main loop for Agent B."""
        logger.info(
            f"[AgentB] Main loop starting… (topic in='{TOPIC_CONSUME}')")

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
                
                # If messages exist, take only the last one
                if msgs_buffer:
                    msg = msgs_buffer[-1]  # ← Last message in buffer
                    skipped = len(msgs_buffer) - 1
                    if skipped > 0:
                        logger.info(f"[AgentB] Skipped {skipped} old messages, processing latest only")
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
                    logger.warning("[AgentB] Invalid message (JSON). Ignored.")
                    continue

                # Extract truckId (Propagate if exists)
                truck_id = None
                for k, v in (msg.headers() or []):
                    if k == "truckId" and v is not None:
                        truck_id = v.decode() if isinstance(v, (bytes, bytearray)) else str(v)
                        break
                if truck_id is None:
                    truck_id = str(uuid.uuid4())

                logger.info(f"[AgentB] Received 'truck-detected' (truckId={truck_id}). Starting LP pipeline…")
                
                # Run License Plate Detection Pipeline
                plate_text, plate_conf, _lp_img = self.process_license_plate_detection()

                if not plate_text:
                    logger.warning("[AgentB] No final text results — not publishing.")
                    continue
                
                # Upload best crop to MinIO
                crop_url = None
                if self.best_crop is not None:
                    try:
                        # Generate unique object name
                        object_name = f"lp_{truck_id}_{plate_text}.jpg"
                        crop_url = self.crop_storage.upload_memory_image(self.best_crop, object_name)
                        
                        if crop_url:
                            logger.info(f"[AgentB] Crop uploaded to MinIO: {crop_url}")
                        else:
                            logger.warning("[AgentB] Failed to upload crop to MinIO")
                    except Exception as e:
                        logger.exception(f"[AgentB] Error uploading crop to MinIO: {e}")
                
                # Publish result
                self._publish_lp_detected(
                    truck_id=truck_id,
                    plate_text=plate_text,
                    plate_conf=plate_conf,
                    crop_url=crop_url
                )

                # Clear frames queue for next detection
                with self.frames_queue.mutex:
                    self.frames_queue.queue.clear()
                
        except KeyboardInterrupt:
            logger.info("[AgentB] Interrupted by user.")
        except KafkaException as e:
            logger.exception(f"[AgentB/Kafka] Kafka error: {e}")
        except Exception as e:
            logger.exception(f"[AgentB] Unexpected error: {e}")
        finally:
            logger.info("[AgentB] Freeing resources…")
            try:
                if self.stream is not None:
                    self.stream.release()
                    logger.debug("[AgentB] RTMP stream released.")
            except Exception as e:
                logger.exception(f"[AgentB] Error releasing RTMP stream: {e}")
            try:
                self.producer.flush(5)
            except Exception:
                pass
            try:
                self.consumer.close()
            except Exception:
                pass

    def stop(self):
        """Gracefully stop Agent B."""

        logger.info("[AgentB] Stopping agent and freeing resources…")
        self.running = False