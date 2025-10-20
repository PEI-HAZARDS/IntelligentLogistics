from shared_utils.Logger import *
from shared_utils.RTSPstream import *
from agentA_microservice.src.YOLO_Truck import *
from agentB_microservice.src.AgentB import *
from time import sleep

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

        # Create a resizable window
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

        # Define window size (width, height)
        cv2.resizeWindow(window_name, 960, 540)

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

                # Wake up Agent B
                #self.logger.info("Waking up Agent B...")
                #agentB = AgentB()
                #agentB.run()
                #self.stop()

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