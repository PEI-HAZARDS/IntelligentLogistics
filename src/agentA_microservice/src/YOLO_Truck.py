from ultralytics import YOLO # type: ignore
import contextlib
import io
import logging
logging.getLogger('ultralytics').setLevel(logging.WARNING)

class YOLO_Truck:
    def __init__(self):
        self.model_path = 'agentA_microservice/data/truck_model.pt'
        self.input_shape = (416, 416)  # multiple of 32, height, width
        self.model = YOLO(self.model_path)
        self.truck_class_id = 7

    def detect(self, image, suppress_output=True):
        if suppress_output:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                results = self.model(image, classes=[self.truck_class_id])
        else:
            results = self.model(image, classes=[self.truck_class_id])
        return results
    
    def get_boxes(self, results):
        boxes = []
        for r in results[0].boxes:
            x1, y1, x2, y2 = r.xyxy[0]
            conf = float(r.conf[0])
            boxes.append([x1, y1, x2, y2, conf])
        return boxes
    
    def truck_found(self, results):
        return len(results[0].boxes) > 0
    
    def close(self):    
        self.model.close()