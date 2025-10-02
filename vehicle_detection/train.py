import ultralytics
from ultralytics import YOLO

print("Ultralytics version:", ultralytics.__version__)

model = YOLO("yolov8n.yaml")    # YOLOv8 nano

# Other versions:
# Nano (n): Faster and smaller
# Small (s): Mix of speed and accuracy
# Medium (m): Mid-sized
# Large (l): Higher accuracy
# Extra Large (x): The largest and most accurate -> rodar no IT

model.train(data="conf.yaml", epochs = 300) # epochs -> number of training cycles 

 