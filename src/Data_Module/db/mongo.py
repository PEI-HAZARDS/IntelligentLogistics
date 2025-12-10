from pymongo import MongoClient
from config import settings

mongo_client = MongoClient(
    settings.mongo_url,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000
)

db = mongo_client["intelligent_logistics"]

detections_collection = db["detections"]
events_collection = db["events"]
system_logs_collection = db["system_logs"]
ocr_failures_collection = db["ocr_failures"]

# Índices (executados apenas 1 vez — Mongo ignora duplicados)
detections_collection.create_index(
    [("timestamp", 1), ("matricula_detectada", 1), ("gate_id", 1), ("processed", 1)]
)