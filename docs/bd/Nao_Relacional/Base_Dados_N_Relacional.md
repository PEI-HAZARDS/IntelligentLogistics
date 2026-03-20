# Non-Relational Database Architecture (MongoDB + Redis)

**Project:** PEI — Intelligent Logistics
**Last updated:** 2026-03-20

The non-relational layer complements PostgreSQL (source of truth) with two specialized databases:

- **MongoDB** — immutable event store, CQRS read models, and analytics aggregations
- **Redis** — sub-millisecond cache, deduplication, real-time counters, and session correlation

This follows a **Polyglot Persistence** strategy: each database is chosen for its strengths, and consistency between them is guaranteed by the **Transactional Outbox** pattern (no direct multi-database writes in the command path).

---

## 1. MongoDB — Event Store + Read Models

MongoDB stores data that is append-heavy, schema-flexible, and optimized for analytical queries. The Data Module interacts with MongoDB via PyMongo (`infrastructure/persistence/mongo.py`).

### 1.1 Collections

| Collection | Purpose | Write Source | Read Consumers |
|------------|---------|-------------|----------------|
| `agent_detections` | Per-agent detection events from AgentA (truck), AgentB (license plate), AgentC (hazmat) | Decision Engine → `POST /decisions/detection-event` | Statistics queries, truck journey timeline |
| `decision_events` | Full decision journey — aggregated detections, engine decision, operator decision, timing, PostgreSQL updates | `persist_decision_event()` in decision_queries.py + outbox worker generic projection | Frontend event feed, audit trail, analytics |
| `appointments_read` | CQRS read model — appointment snapshots projected from outbox events | Outbox worker (`project_to_mongo`) | `GET /arrivals` list endpoint (Mongo → PG fallback) |
| `alerts_read` | Alert read model | Alert handlers (write-through after UoW commit) | Alert dashboard |
| `drivers_read` | Driver reference data | Driver handlers (write-through) | Backoffice queries |
| `workers_read` | Worker reference data | Worker handlers (write-through) | Backoffice queries |
| `statistics_hourly` | Pre-aggregated metrics (hourly buckets) | `compute_hourly_statistics()` (ad-hoc) | Manager dashboard |
| `notifications` | Operator notifications | `create_notification()` | Notification feed |

### 1.2 Document Schemas

#### agent_detections

```json
{
  "detection_id": "det_AgentB_1708167000_001",
  "truck_id": "TRUCK-12345",
  "agent_type": "AgentB",
  "gate_id": 1,
  "timestamp": "2025-02-17T10:30:01Z",
  "detection_data": {
    "type": "license_plate_detection",
    "confidence": 0.87,
    "license_plate": "AA-00-BB",
    "crop_url": "http://minio:9000/crops/lp_12345.jpg"
  },
  "processing": {
    "consumed_by_decision_engine": true,
    "processing_latency_ms": 45
  }
}
```

#### decision_events

```json
{
  "decision_id": "dec_gate1_1708167002_42",
  "truck_id": "TRUCK-12345",
  "gate_id": 1,
  "appointment_id": 42,
  "agent_detections": {
    "truck_detection": { "confidence": 0.98, "crop_url": "..." },
    "license_plate_detection": { "license_plate": "AA-00-BB", "confidence": 0.87 },
    "hazmat_detection": { "un_number": "1203", "kemler_code": "33", "confidence": 0.92 }
  },
  "decision_engine": {
    "timestamp": "2025-02-17T10:30:02Z",
    "initial_decision": "ACCEPTED",
    "decision_reason": "license_plate_matched",
    "processing_time_ms": 350
  },
  "operator_decision": null,
  "final_decision": "ACCEPTED",
  "final_decision_source": "agent",
  "postgres_updates": {
    "appointment_updated": true,
    "appointment_new_status": "IN_PROCESS",
    "alerts_created": 0
  },
  "timing": {
    "detection_to_decision_ms": 2000,
    "decision_to_persistence_ms": 150,
    "total_pipeline_ms": 2150
  },
  "created_at": "2025-02-17T10:30:03Z",
  "version": 1
}
```

### 1.3 Indexes

```javascript
// agent_detections
db.agent_detections.createIndex({"truck_id": 1, "timestamp": 1});
db.agent_detections.createIndex({"gate_id": 1, "created_at": -1});
db.agent_detections.createIndex({"agent_type": 1, "created_at": -1});

// decision_events
db.decision_events.createIndex({"truck_id": 1}, {unique: true});
db.decision_events.createIndex({"gate_id": 1, "created_at": -1});
db.decision_events.createIndex({"appointment_id": 1});
db.decision_events.createIndex({"decision_engine.final_decision": 1, "created_at": -1});

// appointments_read
db.appointments_read.createIndex({"appointment_id": 1}, {unique: true});
db.appointments_read.createIndex({"status": 1, "scheduled_start_time": -1});
```

---

## 2. Redis — Cache + Counters + Dedup

Redis provides low-latency reads and atomic operations. The Data Module interacts via `infrastructure/persistence/redis.py`.

### 2.1 Key Patterns

| Pattern | Type | TTL | Purpose |
|---------|------|-----|---------|
| `dedup:event:{event_id}` | String (SET NX) | 5min | Idempotent event processing — prevents duplicate Kafka event handling |
| `dedup:plate:{lp}:gate:{id}:tb:{ts}` | String (SET NX) | 5min | Detection deduplication — prevents repeated processing of same plate detection |
| `decision:plate:{lp}:gate:{id}:tb:{ts}` | String (JSON) | 1h | Decision result cache — fast replay without re-querying |
| `appointment:{id}:details` | Hash (HSET) | 30min | Hot appointment cache — single-entity CQRS read |
| `lp_lookup:{plate}:appointments` | Set (SADD) | 10min | License plate → appointment_id reverse index |
| `counter:gate:{id}:hour:{YYYYMMDDHH}:{metric}` | Counter (INCR) | 2h | Real-time gate counters (detections, decisions, alerts) |
| `pending_review:{truck_id}` | String (JSON) | 30min | Operator decision correlation — correlates Kafka MANUAL_REVIEW with operator response |

### 2.2 CQRS Read Pattern

```
GET /arrivals/{id}
  ├─ HGETALL appointment:{id}:details
  │   └─ cache hit → return immediately (< 10ms)
  ├─ cache miss → query MongoDB appointments_read
  │   └─ found → return + populate Redis cache
  └─ Mongo miss → query PostgreSQL (authoritative fallback)
      └─ found → return + populate Redis + Mongo caches
```

### 2.3 Dedup Pattern

```
POST /decisions/process (with event_id)
  ├─ SET NX dedup:event:{event_id} EX 300
  │   └─ key already exists → return cached result (idempotent NOOP)
  └─ key set → proceed with business logic
```

---

## 3. Consistency Model

The system follows **eventual consistency** between PostgreSQL and the read models:

```
Command Path (synchronous):
  HTTP Request → Command Handler → PostgreSQL + Outbox (atomic commit) → Response

Projection Path (asynchronous):
  Outbox Worker (polls every 2s) → project_to_mongo() + project_to_redis()
```

- **PostgreSQL** is always consistent (single atomic transaction via Unit of Work)
- **MongoDB/Redis** reflect state with 2-5 second delay (outbox worker poll interval)
- **Outbox worker** retries with exponential backoff (2^n sec, max 60s, jitter) and marks DEAD_LETTER after 5 failures
- **Read endpoints** fall back to PostgreSQL on cache miss — never serve stale data without a fresh source

This model eliminates the impossible promise of strong consistency across three databases and replaces it with mathematically guaranteed eventual consistency via the Transactional Outbox pattern.

---

## 4. Aggregation Queries

### Real-time dashboard (Redis)
```python
counters = get_all_active_counters(gate_id)
# Response: {"detections": 45, "decisions_accepted": 35, ...}
# Latency: ~5ms
```

### Pipeline performance (MongoDB)
```javascript
db.decision_events.aggregate([
  {$match: {gate_id: 1, created_at: {$gte: cutoff}}},
  {$group: {
    _id: "$gate_id",
    total: {$sum: 1},
    avg_pipeline_ms: {$avg: "$timing.total_pipeline_ms"}
  }}
])
// Latency: ~150ms
```

### Truck journey timeline (MongoDB)
```javascript
db.agent_detections.find({truck_id: "TRUCK-12345"}).sort({timestamp: 1})
db.decision_events.findOne({truck_id: "TRUCK-12345"})
// Latency: ~80ms
```

---

## 5. Related Documentation

- **Decision flow examples:** `Decision_Flow_Examples.md` (3 scenarios with full MongoDB documents)
- **Event flow architecture:** `Phase2-NoSql-Event_Flow.md` (Mermaid diagrams + step-by-step)
- **Relational schema:** `../Relacional/Base_Dados_relacional.md`
- **Data Module README:** `src/V_APP/Data_Module/README.md`
