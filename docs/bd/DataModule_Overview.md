# Data Module - System Overview

## Overview

The Data Module is the central microservice for data that manages persistence and business logic of the Intelligent Logistics system.

## Databases

### PostgreSQL - Relational Data
Stores structured data from the port terminal:
- **Workers**: Operators and managers (email/password authentication)
- **Drivers**: Truck drivers (drivers_license/password authentication)
- **Companies**: Transport companies
- **Trucks**: Vehicle license plates
- **Appointments**: Delivery/pickup schedules
- **Bookings/Cargo**: Reservations and cargo
- **Visits**: Entry/exit records
- **Alerts**: Safety alerts (hazmat)
- **Gates/Docks/Shifts**: Terminal infrastructure

### MongoDB - Events
System event log for audit and analytics.

### Redis - Cache
Cache for decisions and statistics (TTL 30s).

## Highway Infraction System

### Data Model

**Appointments** table includes:
```sql
highway_infraction BOOLEAN DEFAULT FALSE
```

Marks hazmat trucks detected on restricted highways before port entry.

### Detection Flow

```
Highway Camera (stream 2)
  → AgentC (detects hazmat)
  → Decision Module (not yet implemented)
  → PATCH /arrivals/{id}/highway-infraction
  → WebSocket broadcast → Frontend
```

### API Endpoints

**Flag as infraction:**
```http
PATCH /api/v1/arrivals/{appointment_id}/highway-infraction
```

**Query statistics (includes infractions):**
```http
GET /api/v1/arrivals/stats?gate_id=1
Response: { "infractions": 2, ... }
```

## Real-Time Notification System

### WebSocket

Frontend connects to API Gateway:
```javascript
ws://gateway:8000/api/ws/decisions/{gate_id}
```

Messages received:
```json
{
  "type": "decision_update",
  "payload": { "appointment_id": 42, "status": "approved", ... }
}
```

### Kafka → WebSocket Flow

```
Decision Engine (Kafka: agent-decision-{gate_id})
  → API Gateway (consumer thread)
  → WebSocketManager.broadcast_to_gate()
  → Frontend (real-time)
```

## Authentication

### Managers/Operators (Web)
- Email/password
- Test credentials:
  - Manager: `manager@example.pt` / `password123`
  - Operator: `worker@porto.pt` / `password123`

### Drivers (Mobile)
- Drivers license/password
- Test credential: `PT12345678` / `driver123`

## Seed Scripts

- `data_init_sample.py`: 20 appointments for MVP demo
- `data_init_realistic.py`: Realistic data for Aveiro Port

Run:
```bash
docker-compose exec data-module python scripts/data_init_sample.py
```
