"""
Kafka Flow Dashboard - WebSocket Server
Subscribes to all Kafka topics and broadcasts messages to connected clients.
"""
import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Set

from confluent_kafka import Consumer, KafkaError
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Configuration
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "10.255.32.143:9092")
GATE_ID = os.getenv("GATE_ID", "1")

# Paths
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# Topics to monitor
TOPICS = [
    f"truck-detected-{GATE_ID}",
    f"lp-results-{GATE_ID}",
    f"hz-results-{GATE_ID}",
    f"decision-results-{GATE_ID}",
]

# Topic display names and colors
TOPIC_CONFIG = {
    f"truck-detected-{GATE_ID}": {"name": "🚛 Truck Detected", "color": "#3498db", "order": 1},
    f"lp-results-{GATE_ID}": {"name": "📋 License Plate", "color": "#2ecc71", "order": 2},
    f"hz-results-{GATE_ID}": {"name": "⚠️ Hazard Plate", "color": "#f39c12", "order": 3},
    f"decision-results-{GATE_ID}": {"name": "✅ Decision", "color": "#9b59b6", "order": 4},
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("KafkaDashboard")

app = FastAPI(title="Kafka Flow Dashboard")

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connected WebSocket clients
clients: Set[WebSocket] = set()

# Background task reference to prevent garbage collection
_consumer_task = None


async def broadcast(message: dict):
    """Broadcast message to all connected clients."""
    disconnected = set()
    for client in clients:
        try:
            await client.send_json(message)
        except Exception:
            disconnected.add(client)
    
    for client in disconnected:
        clients.discard(client)


def create_consumer():
    """Create Kafka consumer for all topics."""
    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": f"kafka-dashboard-consumer-{uuid.uuid4()}",
        "auto.offset.reset": "latest",
        "enable.auto.commit": True,
    })
    consumer.subscribe(TOPICS)
    logger.info(f"Subscribed to topics: {TOPICS}")
    return consumer


def _parse_message_data(msg) -> dict:
    """Parse Kafka message value to dict."""
    try:
        return json.loads(msg.value().decode("utf-8"))
    except json.JSONDecodeError:
        return {"raw": msg.value().decode("utf-8")}


def _extract_truck_id(msg) -> str | None:
    """Extract truck_id from Kafka message headers."""
    headers = msg.headers() or []
    for key, value in headers:
        if key in ("truckId", "truck_id") and value:
            return value.decode() if isinstance(value, bytes) else str(value)
    return None


def _build_dashboard_message(topic: str, truck_id: str | None, data: dict) -> dict:
    """Build dashboard message from Kafka message data."""
    config = TOPIC_CONFIG.get(topic, {"name": topic, "color": "#95a5a6", "order": 99})
    return {
        "type": "kafka_message",
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "topic": topic,
        "topicName": config["name"],
        "topicColor": config["color"],
        "topicOrder": config["order"],
        "truckId": truck_id or data.get("truckId", "N/A"),
        "data": data,
    }


async def _process_kafka_message(msg):
    """Process a single Kafka message and broadcast to clients."""
    topic = msg.topic()
    data = _parse_message_data(msg)
    truck_id = _extract_truck_id(msg)
    
    dashboard_msg = _build_dashboard_message(topic, truck_id, data)
    
    logger.info(f"[DEBUG] Processing msg topic={topic} truckId={truck_id}")
    logger.info(f"Broadcasting: {dashboard_msg['topicName']} - truckId={dashboard_msg['truckId']}")
    await broadcast(dashboard_msg)


async def kafka_consumer_loop():
    """Main Kafka consumer loop."""
    consumer = create_consumer()
    
    try:
        while True:
            msg = consumer.poll(timeout=0.1)
            
            if msg is None:
                await asyncio.sleep(0.01)
                continue
            
            if msg.error():
                if msg.error().code() != KafkaError._PARTITION_EOF:
                    logger.error(f"Kafka error: {msg.error()}")
                continue
            
            await _process_kafka_message(msg)
            
    except Exception as e:
        logger.exception(f"Consumer error: {e}")
    finally:
        consumer.close()


@app.on_event("startup")
async def startup():
    """Start Kafka consumer on app startup."""
    global _consumer_task
    _consumer_task = asyncio.create_task(kafka_consumer_loop())
    logger.info("Kafka Dashboard started")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for dashboard clients."""
    await websocket.accept()
    clients.add(websocket)
    logger.info(f"Client connected. Total clients: {len(clients)}")
    
    try:
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "message": "Connected to Kafka Flow Dashboard",
            "topics": list(TOPIC_CONFIG.keys()),
        })
        
        # Keep connection alive
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                # Send ping
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(websocket)
        logger.info(f"Client disconnected. Total clients: {len(clients)}")


@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """Serve the dashboard HTML."""
    html_path = TEMPLATES_DIR / "index.html"
    return FileResponse(html_path)


@app.get("/health")
async def health():
    return {"status": "ok", "clients": len(clients), "topics": TOPICS}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8091)
