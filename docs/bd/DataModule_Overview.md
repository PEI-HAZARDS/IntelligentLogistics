# Data Module — System Overview

## Overview

The Data Module is the central source-of-truth microservice for the Intelligent Logistics port terminal system. It manages all persistent state across three databases and exposes RESTful APIs for the Decision Engine, API Gateway, and frontend applications.

**Runtime:** Python 3.12 / FastAPI (uvicorn)
**Architecture:** Domain-Driven Design with layered architecture (domain → application → infrastructure)

---

## Architecture Patterns

The module applies six key patterns to guarantee data consistency across a polyglot persistence setup:

| Pattern | What It Solves |
|---------|----------------|
| **CQRS** | Write-side (PostgreSQL) and read-side (Redis/MongoDB) are independently optimized. Reads never block writes. |
| **Unit of Work + Repository** | All write operations go through abstract repositories coordinated by a UoW with explicit commit/rollback. Business logic never imports ORM sessions. |
| **Transactional Outbox** | Domain events are persisted atomically with state changes in PostgreSQL. The outbox worker projects them to MongoDB and Redis — no dual-write risk. |
| **Idempotent Inbox** | Kafka events are deduplicated via `UNIQUE(event_id)` in `inbox_events` before business logic executes. Duplicates ACK + NOOP. |
| **Strangler Fig** | Legacy synchronous paths coexist with new event-driven handlers. Migration is incremental — `ContainerMoved` uses the full pipeline while decision queries are progressively migrated. |
| **Polyglot Persistence** | PostgreSQL for ACID transactions, MongoDB for immutable event logs and analytics, Redis for sub-millisecond cache and real-time counters. |

---

## Databases

### PostgreSQL — Source of Truth

Stores all transactional state with referential integrity. Key tables:

| Entity | Description |
|--------|-------------|
| `appointment` | Scheduled arrivals — core aggregate with `version` (optimistic concurrency) and `arrival_id` (PRT-XXXX via SQL sequence trigger) |
| `visit` | Actual gate visits (entry/exit timestamps, shift assignment) |
| `driver` | Truck drivers with session-based auth |
| `worker` | Port staff (Manager/Operator inheritance via FK) |
| `company` | Transport companies (NIF) |
| `booking` / `cargo` | Reservations with hazmat ADR flags |
| `terminal` / `gate` / `dock` | Port infrastructure |
| `shift` | Work shifts per gate |
| `alert` | Safety and operational alerts |
| `inbox_events` | Kafka consumer inbox (RECEIVED → PROCESSING → PROCESSED/FAILED/DEAD_LETTER) |
| `outbox_events` | Transactional outbox (PENDING → PUBLISHED/FAILED/DEAD_LETTER) |

**Triggers (10):** arrival_id sequence generation, status transition validation, visit auto-completion, entry_time auto-set, alert timestamp, shift_alert_history, created_at timestamps.

**Indexes:** 26+ covering appointment lookups, visit composites, shift scheduling, alert queries, worker/driver active status.

**Migration:** `src/V_APP/Data_Module/scripts/migrationDBv2.sql` — idempotent (IF NOT EXISTS, OR REPLACE).

### MongoDB — Event Store + CQRS Read Models

| Collection | Purpose | Write Source |
|------------|---------|-------------|
| `agent_detections` | Per-agent detection events (AgentA/B/C) | Decision Engine via HTTP |
| `decision_events` | Full decision journey documents | `persist_decision_event()` + outbox worker |
| `appointments_read` | CQRS read model (appointment snapshots) | Outbox worker projection |
| `alerts_read` | Alert read model | Alert handlers (write-through) |
| `drivers_read` / `workers_read` | Reference data projections | Handlers (write-through) |
| `statistics_hourly` | Pre-aggregated metrics | Statistics queries (ad-hoc) |
| `notifications` | Operator notifications | Notification queries |

**Indexes:** truck_id + timestamp on agent_detections, gate_id + created_at on decision_events, appointment_id lookup.

### Redis — Cache + Counters + Dedup

| Key Pattern | TTL | Purpose |
|-------------|-----|---------|
| `dedup:event:{event_id}` | 5min | Idempotent event processing (SET NX) |
| `dedup:plate:{lp}:gate:{id}:tb:{ts}` | 5min | Detection deduplication |
| `decision:plate:{lp}:gate:{id}:...` | 1h | Decision result cache |
| `appointment:{id}:details` | 30min | Hot appointment cache (HSET) |
| `lp_lookup:{plate}:appointments` | 10min | License plate → appointment_id |
| `counter:gate:{id}:hour:{h}:*` | 2h | Real-time gate counters (INCR) |
| `pending_review:{truck_id}` | 30min | Operator decision correlation |

---

## Event-Driven Pipeline

### Write Path (ContainerMoved)

```
Kafka (agent-decision-{gate_id})
  │
  ▼
KafkaDecisionConsumer
  │  builds EventEnvelope (UUIDv7 event_id)
  ▼
ContainerMovedHandler
  ├─ Inbox INSERT (idempotency gate)
  ├─ Aggregate lock (SELECT FOR UPDATE)
  ├─ State transition + Outbox APPEND
  ├─ UoW COMMIT (single PG transaction)
  └─ Kafka offset commit
          │
          ▼
    Outbox Worker (background)
      ├─ project_to_mongo() → upsert
      ├─ project_to_redis() → cache + counter
      ├─ Mark PUBLISHED
      └─ Retry (exp backoff) or DEAD_LETTER
```

### Read Path (CQRS)

```
GET /arrivals/{id}
  ├─ Redis cache hit? → return (< 10ms)
  ├─ MongoDB read model? → return + cache
  └─ PostgreSQL fallback → return + cache
```

---

## Key API Endpoints

| Category | Key Endpoints |
|----------|---------------|
| **Health** | `GET /health` |
| **Arrivals** | `GET /arrivals`, `GET /arrivals/{id}`, `GET /arrivals/next/{gate_id}`, `POST /arrivals/{id}/decision` |
| **Decisions** | `POST /decisions/process`, `POST /decisions/query-appointments`, `POST /decisions/detection-event` |
| **Drivers** | `POST /drivers/login`, `POST /drivers/claim`, `GET /drivers/me/today` |
| **Workers** | `POST /workers/login`, `GET /workers/me` |
| **Alerts** | `GET /alerts`, `POST /alerts/hazmat`, `GET /alerts/reference/adr-codes` |
| **Statistics** | `GET /statistics/summary`, `/by-company`, `/volume`, `/alerts` |

Full Swagger docs at `http://localhost:8080/docs`.

---

## Authentication

### Workers (Web — Operator/Manager)
- Email + password (bcrypt)
- Test: `manager@example.pt` / `password123`, `worker@porto.pt` / `password123`

### Drivers (Mobile App)
- Driver's license + password
- Sequential delivery control via `/claim` (PIN = arrival_id)
- Test: `PT12345678` / `driver123`
- Debug mode: `DEBUG_MODE=true` bypasses sequential validation

---

## Highway Infraction System

Hazmat trucks detected on restricted highways before port entry:

```
Highway Camera → AgentC (hazmat detection) → Decision Engine
  → PATCH /arrivals/{id}/highway-infraction
  → WebSocket notification → Frontend
```

`appointment.highway_infraction BOOLEAN DEFAULT FALSE`

---

## Related Documentation

- **Relational schema:** `docs/bd/Relacional/Base_Dados_relacional.md`
- **Non-relational schema:** `docs/bd/Nao_Relacional/`
- **ER diagrams:** `docs/bd/Relacional/*.drawio`
- **Domain model:** `docs/bd/domain_model.png`
- **Refactor plan:** `docs/elaboration/data_module_refactor_plan.md`
- **Architecture guardrails:** `CLAUDE.md` (11 guardrails governing the refactor)
