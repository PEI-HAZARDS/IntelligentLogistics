from shared_utils.Logger import *
from shared_utils.RTSPstream import *
from agentA_microservice.src.YOLO_Truck import *
from agentB_microservice.src.AgentB import *
from time import sleep

RTSP_STREAM_LOW = "rtsp://10.255.35.86:554/stream2"
MESSAGE_INTERVAL = 15

# Agent to detect trucks on low quality RTSP stream using YOLO model
class AgentA:
    def __init__(self, broker):
        self.logger = GlobalLogger().get_logger()
        self.yolo = YOLO_Truck()
        self.running = True
        self.broker = broker
        self.last_message_time = 0

    def run(self):
        self.logger.info("Agent A is running...")
        
        cap = RTSPStream(RTSP_STREAM_LOW)
        #window_name = "Agent A - Truck Detection"

        # Create a resizable window
        #cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

        # Define window size (width, height)
        #cv2.resizeWindow(window_name, 960, 540)

        while self.running:
            frame = cap.read()
            if frame is None:
                continue  # no frame yet

            # Run detection
            self.logger.info("Running truck detection...")
            results = self.yolo.detect(frame)

            if self.yolo.truck_found(results):
                now = time.time()
                if now - self.last_message_time < MESSAGE_INTERVAL:
                    self.logger.info("Truck detected but waiting to send next message...")
                    continue  # Skip sending message if interval not passed

                self.last_message_time = now
                boxes = self.yolo.get_boxes(results)
                size = len(boxes)
                self.logger.info(f"{size} truck(s) detected.")
                self.broker.put_message({"type": "truck_detected"})
                self.logger.info(f"Sent truck detection message to Agent B.")

                #for box in boxes:
                #    x1, y1, x2, y2, conf = map(float, box)
                #    if conf < 0.5:
                #        continue
#
                #    label = f"Truck ({conf*100:.1f}%)"
                #    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
                #    cv2.putText(frame, label, (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)

            else:
                self.logger.info("No truck detected.")

            #cv2.imshow(window_name, frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                cap.release()
                cv2.destroyAllWindows()
                break
        
    def stop(self):
        self.logger.info("Stopping Agent A...")
        self.running = False
        self.yolo.close()
        self.logger.info("Agent A stopped.")