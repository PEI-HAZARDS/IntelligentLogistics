from ultralytics import YOLO
import os

model = YOLO("bestx.pt")  # load a pretrained YOLOv8n model

os.makedirs("results", exist_ok=True)

for image in os.listdir("./dataset/test/images"):
    if image.endswith(('.png', '.jpg', '.jpeg')):
        img_path = os.path.join("./dataset/test/images", image)
        results = model(img_path)
        results[0].save(filename=os.path.join("results", f"result_{image}"))    
