from shared_utils.Logger import *
from shared_utils.RTSPstream import *
from agentB_microservice.src.YOLO_License_Plate import *
from agentB_microservice.src.OCR import *
import time
import os
import cv2
from queue import Queue, Empty

RTSP_STREAM_HIGH = "rtsp://10.255.35.86:554/stream1"
CROPS_PATH = "agentB_microservice/data/lp_crops"
os.makedirs(CROPS_PATH, exist_ok=True)


class AgentB:
    """
    Agent B:
    - Waits for 'truck_detected' messages from the broker.
    - On detection, fetches frames from the high-quality RTSP stream.
    - Runs YOLO to detect license plates.
    - Uses OCR to extract license plate text.
    """

    def __init__(self, broker):
        self.logger = GlobalLogger().get_logger()
        self.yolo = YOLO_License_Plate()
        self.ocr = OCR()
        self.running = True
        self.broker = broker
        self.frames_queue = Queue()
        self.stream = RTSPStream(RTSP_STREAM_HIGH)

    def run(self):
        self.logger.info(f"[AgentB] Starting main loop...")

        while self.running:
            try:
                message = self.broker.get_message(timeout=1)
                self.logger.debug("[AgentB] Checking broker messages...")

                if message and message.get("type") == "truck_detected":
                    self.logger.info("[AgentB] Received 'truck_detected' event from Agent A.")
                    self.process_license_plate_detection()
                else:
                    time.sleep(1)
            except Exception as e:
                self.logger.exception(f"[AgentB] Exception in main loop: {e}")

    def _get_frames(self, num_frames=5):
        """Capture a few frames from the RTSP stream."""

        self.logger.info(f"[AgentB] Attempting to read {num_frames} frames from RTSP stream...")
        captured = 0
        while captured < num_frames and self.running:
            try:
                frame = self.stream.read()
                if frame is not None:
                    self.frames_queue.put(frame)
                    captured += 1
                    self.logger.debug(f"[AgentB] Captured frame {captured}/{num_frames}.")
                else:
                    self.logger.debug("[AgentB] No frame available yet, retrying...")
                    time.sleep(0.1)
            except Exception as e:
                self.logger.exception(f"[AgentB] Error capturing frame: {e}")
                time.sleep(0.2)
        

    def process_license_plate_detection(self):
        """Main license plate detection and OCR processing logic."""

        self.logger.info("[AgentB] Starting license plate detection pipeline...")
        self._get_frames(1)

        if self.frames_queue.empty():
            self.logger.warning("[AgentB] No frames were captured from RTSP stream.")
            return

        lp_results = []
        while self.running and not self.frames_queue.empty():
            try:
                frame = self.frames_queue.get_nowait()
                self.logger.debug("[AgentB] Retrieved frame from queue for processing.")
            except Empty:
                self.logger.warning("[AgentB] Frame queue unexpectedly empty.")
                time.sleep(0.05)
                continue

            try:
                self.logger.info("[AgentB] Running YOLO license plate detection...")
                results = self.yolo.detect(frame)

                if not results:
                    self.logger.debug("[AgentB] YOLO returned no results for this frame.")
                    continue

                if self.yolo.found_license_plate(results):
                    boxes = self.yolo.get_boxes(results)
                    self.logger.info(f"[AgentB] Detected {len(boxes)} license plate(s).")

                    for i, box in enumerate(boxes, start=1):
                        x1, y1, x2, y2, conf = map(float, box)
                        if conf < 0.5:
                            self.logger.debug(f"[AgentB] Skipping low-confidence detection ({conf:.2f}).")
                            continue

                        lp_crop = frame[int(y1):int(y2), int(x1):int(x2)]
                        crop_path = f"{CROPS_PATH}/lp_crop_{int(time.time())}_{i}.jpg"
                        cv2.imwrite(crop_path, lp_crop)
                        self.logger.debug(f"[AgentB] Saved license plate crop: {crop_path}")

                        self.logger.info("[AgentB] Running OCR extraction...")
                        try:
                            text, conf = self.ocr.extract_text(lp_crop)
                            lp_results.append((text, conf))
                            self.logger.info(f"[AgentB] OCR result: '{text}' (confidence: {conf:.2f})")
                        except Exception as e:
                            self.logger.exception(f"[AgentB] OCR extraction failed: {e}")

                else:
                    self.logger.info("[AgentB] No license plate detected in this frame.")

            except Exception as e:
                self.logger.exception(f"[AgentB] Error during detection loop: {e}")

        if not lp_results:
            self.logger.warning("[AgentB] No license plates detected in any captured frames.")
            return

        try:
            final_text, conf = self.compute_results(lp_results)
            self.logger.info(f"[AgentB] Final license plate: '{final_text}' (confidence: {conf:.2f})")
        except Exception as e:
            self.logger.exception(f"[AgentB] Error computing final results: {e}")

    def compute_results(self, results):
        """Combine or select final result from YOLO+OCR pipeline."""

        self.logger.debug("[AgentB] Computing final OCR result from collected detections...")
        return results[-1][0], results[-1][1]  # Placeholder logic

    def stop(self):
        self.logger.info("[AgentB] Stopping agent and releasing resources...")
        try:
            self.yolo.close()
        except Exception as e:
            self.logger.exception(f"[AgentB] Error closing YOLO model: {e}")
        self.logger.info("[AgentB] Agent stopped successfully.")
