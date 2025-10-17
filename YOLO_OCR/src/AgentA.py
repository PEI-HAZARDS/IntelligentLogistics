from src.Logger import *
from src.RTSPstream import *
from src.YOLO_Truck import *

RTSP_STREAM_LOW = "rtsp://10.255.35.86:554/stream2"

# Agent to detect trucks on low quality RTSP stream using YOLO model
class AgentA:
    def __init__(self):
        self.logger = GlobalLogger().get_logger()
        self.yolo = YOLO_Truck()
        self.running = True

    def run(self):
        self.logger.info("Agent A is running...")
        
        cap = RTSPStream(RTSP_STREAM_LOW)
        window_name = "Agent A - Truck Detection"

        while self.running:
            frame = cap.read()
            if frame is None:
                continue  # no frame yet

            # Run detection
            self.logger.info("Running truck detection...")
            results = self.yolo.detect(frame)

            # TODO: Wake up Agent B if truck detected (Pub/Sub)
            if self.yolo.truck_found(results):
                boxes = self.yolo.get_boxes(results)
                size = len(boxes)
                self.logger.info(f"{size} truck(s) detected.")
                for box in boxes:
                    x1, y1, x2, y2, conf = map(float, box)
                    if conf < 0.5:
                        continue

                    label = f"Truck ({conf*100:.1f}%)"
                    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
                    cv2.putText(frame, label, (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)

            else:
                self.logger.info("No truck detected.")

            cv2.imshow(window_name, frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                cap.release()
                cv2.destroyAllWindows()
                break
        
    def stop(self):
        self.logger.info("Stopping Agent A...")
        self.running = False
        self.yolo.close()
        self.logger.info("Agent A stopped.")