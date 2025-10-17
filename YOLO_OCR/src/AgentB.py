from src.Logger import *
from src.RTSPstream import *
from src.YOLO_License_Plate import *
from src.OCR import *

RTSP_STREAM_HIGH = "rtsp://10.255.35.86:554/stream1"

# Agent to detect license plates on high quality RTSP stream using YOLO model
class AgentB:
    def __init__(self):
        self.logger = GlobalLogger().get_logger()
        self.yolo = YOLO_License_Plate()
        self.ocr = OCR()

    def run(self):
        self.logger.info("Agent A is running...")
        
        cap = RTSPStream(RTSP_STREAM_HIGH)
        window_name = "Agent B - License Plate Detection"
        n = 0
        results = []

        # Capture 5 frames
        while n < 5:
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
                self.logger.info(f"{size} license plate(s) detected.")
                for box in boxes:
                    x1, y1, x2, y2, conf = map(float, box)
                    if conf < 0.5:
                        continue

                    label = f"License Plate ({conf*100:.1f}%)"
                    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
                    cv2.putText(frame, label, (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

                    lp_crop = frame[y1:y2, x1:x2]

                    text, conf = self.ocr.extract_text(lp_crop)
                    results.append((text, conf))
                    self.logger.info(f"Extracted text: {text}")
                    cv2.putText(frame, text, (x1, y2 + 20), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 2)

            else:
                self.logger.info("No license plate detected.")

            cv2.imshow(window_name, frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                cap.release()
                cv2.destroyAllWindows()
                break

            n += 1
        
        if not results:
            self.logger.info("No license plates detected in captured frames.")
            return
        
        final_text, conf = self.compute_results(results)
        self.logger.info(f"Final extracted license plate text: {final_text} with confidence {conf:.2f}")
    
    def compute_results(self, results):
        return "", 0.0

    def stop(self):
        self.logger.info("Stopping Agent B...")
        self.yolo.close()
        self.logger.info("Agent B stopped.")