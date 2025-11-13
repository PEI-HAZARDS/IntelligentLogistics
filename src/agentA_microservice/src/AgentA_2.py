from shared_utils.Logger import *
from shared_utils.RTSPstream import *
from agentA_microservice.src.YOLO_Truck import *
from agentB_microservice.src.AgentB_2 import *
import time
from time import sleep

RTSP_STREAM_LOW = "rtsp://10.255.35.86:554/stream2"
MESSAGE_INTERVAL = 30  # seconds


class AgentA:
    """
    Agent A:
    - Continuously monitors a low-quality RTSP stream.
    - Detects trucks using the YOLO model.
    - Sends 'truck_detected' messages to the broker for Agent B.
    """

    def __init__(self, broker):
        self.logger = GlobalLogger().get_logger()
        self.yolo = YOLO_Truck()
        self.running = True
        self.broker = broker
        self.last_message_time = 0

    def run(self):
        self.logger.info("[AgentA] Starting Agent A main loop...")

        cap = None
        try:
            self.logger.info(f"[AgentA] Connecting to RTSP stream: {RTSP_STREAM_LOW}")
            cap = RTSPStream(RTSP_STREAM_LOW)
        except Exception as e:
            self.logger.exception(f"[AgentA] Failed to initialize RTSP stream: {e}")
            return

        while self.running:
            try:
                frame = cap.read()
                if frame is None:
                    self.logger.debug("[AgentA] No frame available from RTSP stream yet.")
                    time.sleep(0.2)
                    continue

                self.logger.debug("[AgentA] Frame successfully captured, running truck detection...")
                results = self.yolo.detect(frame)

                if results is None:
                    self.logger.warning("[AgentA] YOLO model returned no results (None).")
                    continue

                if self.yolo.truck_found(results):
                    now = time.time()
                    elapsed = now - self.last_message_time

                    if elapsed < MESSAGE_INTERVAL:
                        self.logger.info(f"[AgentA] Truck detected, but waiting {MESSAGE_INTERVAL - elapsed:.1f}s before next message.")
                        continue

                    self.last_message_time = now
                    try:
                        boxes = self.yolo.get_boxes(results)
                        size = len(boxes)
                        self.logger.info(f"[AgentA] Detected {size} truck(s). Sending message to Agent B...")
                        self.broker.put_message({"type": "truck_detected"})
                        self.logger.info("[AgentA] Message sent successfully to Agent B.")
                    except Exception as e:
                        self.logger.exception(f"[AgentA] Error sending detection message: {e}")

                else:
                    self.logger.debug("[AgentA] No truck detected in this frame.")

            except Exception as e:
                self.logger.exception(f"[AgentA] Exception during detection loop: {e}")
                time.sleep(1)  # Avoid busy looping on errors

        # Cleanup once stopped
        if cap:
            try:
                cap.release()
                self.logger.debug("[AgentA] RTSP stream released.")
            except Exception as e:
                self.logger.exception(f"[AgentA] Error releasing RTSP stream: {e}")

    def stop(self):
        """Gracefully stop Agent A."""
        self.logger.info("[AgentA] Stopping Agent A...")
        self.running = False

        try:
            self.yolo.close()
        except Exception as e:
            self.logger.exception(f"[AgentA] Error closing YOLO model: {e}")

        self.logger.info("[AgentA] Agent stopped successfully.")
