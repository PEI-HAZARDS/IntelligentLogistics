from agentA_microservice.src.RTSPstream import RTSPStream # type: ignore
from agentA_microservice.src.YOLO_Truck import * # type: ignore
import os
import time
import uuid
from confluent_kafka import Producer, KafkaError  # type: ignore
from typing import Optional
import json
import logging

# --- Configuration ---
# Load environment variables or fallback to default network settings
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "10.255.32.143:9092")
NGINX_RTMP_HOST = os.getenv("NGINX_RTMP_HOST", "10.255.32.35")
NGINX_RTMP_PORT = os.getenv("NGINX_RTMP_PORT", "1935")
GATE_ID = os.getenv("GATE_ID", "gate01")
RTSP_STREAM_LOW = os.getenv("RTSP_STREAM_LOW", f"rtmp://{NGINX_RTMP_HOST}:{NGINX_RTMP_PORT}/streams_low/gate{GATE_ID}")

# --- Operational Constants ---
MAX_CONNECTION_RETRIES = 10
RETRY_DELAY = 5         # Wait time between connection attempts
MESSAGE_INTERVAL = 30   # Throttle: Limit alerts to one every 30 seconds
KAFKA_TOPIC = f"truck-detected-{GATE_ID}"

logger = logging.getLogger("AgentA")

class AgentA:
    """
    Agent A:
    - Continuously monitors a low-quality stream.
    - Detects trucks with YOLO.
    - Publishes 'truck-detected-GATE_ID' events to Kafka
    """

    def __init__(self):
        # Initialize detection model
        self.yolo = YOLO_Truck() # type: ignore
        self.running = True
        self.last_message_time = 0
        
        # Initialize Kafka Producer
        logger.info(f"[AgentA/Kafka] Connecting to kafka via '{KAFKA_BOOTSTRAP}' …")
        self.producer = Producer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "log_level": 1,
        })
    
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

    def _publish_truck_detected(self, max_conf: float, num_boxes: int):
        """Publishes the 'truck-detected-GATE_ID' event to Kafka."""

        # Generate unique ID and timestamp for the event
        truck_id = "TRK" + str(uuid.uuid4())[:8]
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Construct JSON payload
        payload = {
            "timestamp": timestamp,
            "confidence": float(max_conf),
            "detections": int(num_boxes)
        }

        logger.info(f"[AgentA] Publishing '{KAFKA_TOPIC}' (truckId={truck_id}, detections={num_boxes}, max_conf={max_conf:.2f}) …")

        # Send asynchronously to Kafka
        self.producer.produce(
            topic=KAFKA_TOPIC,
            key=None,
            value=json.dumps(payload).encode("utf-8"),
            headers={"truckId": truck_id},
            callback=self._delivery_callback
        )

        # Trigger delivery callbacks
        self.producer.poll(0)

    def _connect_to_stream_with_retry(self, max_retries=MAX_CONNECTION_RETRIES):
        """
        Attempts to connect to RTMP stream with automatic retry.
        Waits for the nginx-rtmp service to be available.
        """
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    f"[AgentA] Connection attempt {attempt}/{max_retries} to: {RTSP_STREAM_LOW}")
                cap = RTSPStream(RTSP_STREAM_LOW)
                logger.info("[AgentA] Successfully connected to stream!")
                return cap
            
            except ConnectionError as e:
                logger.warning(
                    f"[AgentA] Connection failed (attempt {attempt}/{max_retries}): {e}")

                # Wait before retrying if not the last attempt
                if attempt < max_retries:
                    logger.info(
                        f"[AgentA] Waiting {RETRY_DELAY}s before retry...")
                    time.sleep(RETRY_DELAY)
                else:
                    logger.error(
                        "[AgentA] Max retries reached. Could not connect to stream.")
                    raise
            except Exception as e:
                logger.exception(
                    f"[AgentA] Unexpected error during connection: {e}")
                raise

    def _loop(self):
        """Main loop for Agent A."""

        logger.info(f"[AgentA] Starting Agent A main loop (stream={RTSP_STREAM_LOW}, kafka bootstrap={KAFKA_BOOTSTRAP}) …")

        # Attempt initial stream connection
        cap = None
        try:
            cap = self._connect_to_stream_with_retry()

        except Exception as e:
            logger.exception(f"[AgentA] Failed to initialize stream after retries: {e}")
            return

        # Main processing cycle
        while self.running:
            try:
                frame = cap.read() # type: ignore
                if frame is None:
                    logger.debug("[AgentA] No frame available from RTSP stream yet.")
                    time.sleep(0.2)
                    continue

                # Run YOLO inference
                logger.debug("[AgentA] Frame captured, running truck detection…")
                results = self.yolo.detect(frame)

                if results is None:
                    logger.warning("[AgentA] YOLO model returned no results (None).")
                    continue

                # Check for positive detection
                if self.yolo.truck_found(results):
                    now = time.time()
                    elapsed = now - self.last_message_time

                    # Check throttling interval (Debounce)
                    if elapsed < MESSAGE_INTERVAL:
                        logger.info(f"[AgentA] Truck detected, but waiting {MESSAGE_INTERVAL - elapsed:.1f}s before next message.")
                        continue

                    # Extract stats and publish to Kafka
                    try:
                        boxes = self.yolo.get_boxes(results)  # [x1,y1,x2,y2,conf]
                        num_boxes = len(boxes)
                        max_conf = max((b[4] for b in boxes), default=0.0)
                        self.last_message_time = now
                        self._publish_truck_detected(max_conf, num_boxes)

                    except Exception as e:
                        logger.exception(f"[AgentA] Error preparing Kafka event: {e}")

                else:
                    logger.debug("[AgentA] No truck detected in this frame.")

            except Exception as e:
                logger.exception(f"[AgentA] Exception during detection loop: {e}")
                time.sleep(1)

        # Cleanup: Release video resources
        if cap:
            try:
                cap.release()
                logger.debug("[AgentA] RTSP stream released.")
            except Exception as e:
                logger.exception(f"[AgentA] Error releasing RTSP stream: {e}")

        # Cleanup: Flush pending Kafka messages
        try:
            logger.info("[AgentA/Kafka] Flushing producer…")
            self.producer.flush(10)

        except Exception as e:
            logger.exception(f"[AgentA/Kafka] Error on flush: {e}")

    def stop(self):
        """Gracefully stop Agent A."""

        logger.info("[AgentA] Stopping Agent A…")
        self.running = False