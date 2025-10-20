from shared_utils.Logger import *
from shared_utils.RTSPstream import *
from agentB_microservice.src.YOLO_License_Plate import *
from agentB_microservice.src.OCR import *
import time
import os
import cv2

RTSP_STREAM_HIGH = "rtsp://10.255.35.86:554/stream1"
CROPS_PATH = "agentB_microservice/data/lp_crops"
os.makedirs(CROPS_PATH, exist_ok=True)

# Agent to detect license plates on high quality RTSP stream using YOLO model
class AgentB:
    def __init__(self, broker):
        self.logger = GlobalLogger().get_logger()
        self.yolo = YOLO_License_Plate()
        self.ocr = OCR()
        self.running = True
        self.broker = broker

    def run(self):
        self.logger.info("Agent B is running...")

        while self.running:
            message = self.broker.get_message(timeout=1)
            self.logger.info("Agent B checking for messages...")
            if message and message.get("type") == "truck_detected":
                self.logger.info("Received truck detection message from Agent A.")
                self.process_license_plate_detection()
            else:
                time.sleep(1)  # Avoid busy waiting
    
    def process_license_plate_detection(self):
        cap = RTSPStream(RTSP_STREAM_HIGH)
        #window_name = "Agent B - License Plate Detection"
        # Create a resizable window
        #cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

        # Define window size (width, height)
        #cv2.resizeWindow(window_name, 960, 540)
        
        n = 0
        results = []
        # Capture n frames and compute results
        while n < 1:
            frame = cap.read()
            if frame is None:
                continue  # no frame yet

            # Run detection
            self.logger.info("Running license plate detection...")
            results = self.yolo.detect(frame)

            # License plate(s) found
            if self.yolo.found_license_plate(results):
                boxes = self.yolo.get_boxes(results)
                size = len(boxes)
                self.logger.info(f"{size} license(s) plate detected.")
                m = 1
                for box in boxes:
                    x1, y1, x2, y2, conf = map(float, box)
                    if conf < 0.5 or m > 2:
                        continue

                    #label = f"License Plate ({conf*100:.1f}%)"
                    #cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
                    #cv2.putText(frame, label, (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                    lp_crop = frame[int(y1):int(y2), int(x1):int(x2)]

                    self.logger.info("Extracting text from license plate [PADDLE OCR]...")    
                    text, conf = self.ocr.extract_text(lp_crop)
                    self.logger.info(f"Extracted text: {text}")
                    cv2.imwrite(f"{CROPS_PATH}/lp_crop_{int(time.time())}_{m}.jpg", lp_crop)
                    m += 1
                    #cv2.putText(frame, text, (int(x1), int(y2) + 20), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 2) # type: ignore
                    #cv2.putText(frame, text, (int(x1), int(y2) + 20), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 2) # type: ignore

            else:
                self.logger.info("No license plate detected.")

            #cv2.imshow(window_name, frame)

            #if cv2.waitKey(1) & 0xFF == ord('q'):
            #    cap.release()
            #    cv2.destroyAllWindows()
            #    break

            n += 1
        
        if not results:
            self.logger.info("No license plates detected in captured frames.")
            return
        
        final_text, conf = self.compute_results(results)
        self.logger.info(f"Final extracted license plate text: {final_text} with confidence {conf:.2f}")


    def compute_results(self, results):
        return results[-1][0], results[-1][1]

    def stop(self):
        self.logger.info("Stopping Agent B...")
        self.yolo.close()
        self.logger.info("Agent B stopped.")