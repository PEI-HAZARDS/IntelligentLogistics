# API Gateway - Intelligent Logistics

API Gateway is the central entry point for all frontend applications (Web and Mobile). It aggregates multiple backend services and provides real-time notifications via WebSocket.

## Architecture

```
Frontend Apps
    ↓
API Gateway (FastAPI + WebSocket)
    ↓
    ├── Data Module (REST API)
    ├── Kafka Consumer (decisions)
    └── WebSocket Manager (broadcast)
```

## Features

### 1. HTTP Proxy
Forwards REST requests to internal services:
- `/api/arrivals/*` → Data Module
- `/api/workers/*` → Data Module
- `/api/alerts/*` → Data Module
- `/api/drivers/*` → Data Module
- `/api/statistics/*` → Data Module

### 2. WebSocket Real-Time
Broadcast real-time notifications to connected frontends.

### 3. Kafka Consumer
Consumes decisions from Decision Engine and propagates via WebSocket.

## WebSocket - Real-Time Notifications

### Connection

Frontend connects per gate:
```javascript
const ws = new WebSocket('ws://gateway:8000/api/ws/decisions/{gate_id}');

ws.onmessage = (event) => {
  const notification = JSON.parse(event.data);
  console.log(notification);
};
```

### Server Messages

```json
{
  "type": "decision_update",
  "payload": {
    "appointment_id": 42,
    "truck_id": "AA-00-BB",
    "status": "approved",
    "gate_id": 1,
    "timestamp": "2024-01-15T10:30:00Z"
  }
}
```

### Data Flow

```
Decision Engine → Kafka (agent-decision-{gate_id})
    ↓
API Gateway (consumer thread)
    ↓
WebSocketManager.broadcast_to_gate(gate_id, payload)
    ↓
All clients connected to that gate
```

## Highway Infraction Notifications

When a hazmat truck is detected on a restricted highway:

```http
PATCH /api/arrivals/{appointment_id}/highway-infraction
```

**Note**: Currently this endpoint does **not** send a WebSocket notification. To add it:

```python
async def flag_highway_infraction(
    appointment_id: int,
    request: Request
):
    result = await internal_client.patch(
        f"/arrivals/{appointment_id}/highway-infraction"
    )
    
    # Broadcast via WebSocket
    ws_manager = request.app.state.ws_manager
    gate_id = str(request.app.state.gate_id)
    await ws_manager.broadcast_to_gate(gate_id, {
        "type": "highway_infraction",
        "payload": result
    })
    
    return result
```

## Main Endpoints

### Health
```http
GET /health
```

### Arrivals (Proxy)
```http
GET    /api/arrivals
GET    /api/arrivals/stats
GET    /api/arrivals/next/{gate_id}
GET    /api/arrivals/pin/{arrival_id}
PATCH  /api/arrivals/{id}/highway-infraction
PATCH  /api/arrivals/{id}/status
```

### Workers (Proxy)
```http
POST /api/workers/login
GET  /api/workers/me
```

### WebSocket
```http
WS /api/ws/decisions/{gate_id}
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GATEWAY_PORT` | `8000` | Gateway port |
| `DATA_MODULE_URL` | `http://data-module:8000` | Data Module URL |
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka:9092` | Kafka brokers |
| `KAFKA_DECISION_TOPIC` | `agent-decision-1` | Kafka decisions topic |
| `CORS_ALLOW_ORIGINS` | `["*"]` | Allowed CORS origins |

### Docker

```bash
# Start gateway
docker-compose up api-gateway

# Logs
docker-compose logs -f api-gateway
```

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python -m src.main

# Tests
pytest tests/
```

## CORS

By default, allows all origins (`*`). For production, configure:

```env
CORS_ALLOW_ORIGINS='["http://localhost:5173", "http://localhost:5174"]'
```

## Monitoring

Prometheus endpoints exposed at `/metrics` (via FastAPI Instrumentator).
