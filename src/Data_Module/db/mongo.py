from pymongo import MongoClient
from config import settings

client = MongoClient(settings.mongo_url)
db = client["intelligent_logistics"]  # Nome da BD

# Coleções baseadas na arquitetura
detections_collection = db["detections"]  # Detecções IA (camioes, matriculas)
events_collection = db["events"]  # Eventos operacionais (ações do operador)
system_logs_collection = db["system_logs"]  # Logs técnicos dos microserviços
ocr_failures_collection = db["ocr_failures"]  # Falhas de OCR

# Exemplo de documento para detections (como na referência)
# {
#   "timestamp": "2025-02-16T10:22:53Z",
#   "gate_id": 2,
#   "matricula_detectada": "00-AA-11",
#   "confidence": 0.93,
#   "source": "IA",
#   "image_path": "/detections/2025/02/16/abc123.jpg",
#   "processed": false,
#   "matched_chegada_id": null,
#   "alert_generated": false,
#   "metadata": {
#     "camera_id": "C1",
#     "yolo_model": "yolov11",
#     "latency_ms": 32
#   }
# }

# Índices recomendados (adiciona se necessário)
# detections_collection.create_index([("timestamp", 1), ("matricula_detectada", 1), ("gate_id", 1), ("processed", 1)])
