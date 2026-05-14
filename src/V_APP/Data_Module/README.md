# Data Module — Intelligent Logistics

The **Data Module** is the source-of-truth microservice for the Intelligent Logistics port terminal system. It owns all persistent state and exposes RESTful APIs consumed by the Decision Engine, API Gateway, and frontend applications.

The module follows a **Domain-Driven Design** layered architecture with **Polyglot Persistence** (PostgreSQL + MongoDB + Redis), applying industry patterns to guarantee data consistency, resilience, and low-latency reads across a distributed event-driven platform.

---

## Architecture Patterns

| Pattern | Purpose | Implementation |
|---------|---------|----------------|
| **CQRS** | Separate read and write models for independent optimization and scaling. Write-side targets PostgreSQL; read-side serves from Redis/MongoDB projections with PostgreSQL fallback. | `application/use_cases/` (commands) vs `application/queries/` + `routes/` (reads) |
| **Unit of Work + Repository** | Coordinate multiple repository writes in a single database transaction with explicit commit/rollback semantics. Business logic depends only on abstractions, never on ORM sessions. | `domain/interfaces.py` (ports), `infrastructure/persistence/unit_of_work.py` (adapter) |
| **Transactional Outbox** | Guarantee that domain state changes and their corresponding events are persisted atomically. An outbox row is written in the same PostgreSQL transaction as the aggregate mutation — no dual-write risk. | `infrastructure/persistence/outbox_repository.py`, `scripts/simple_outbox_worker.py` |
| **Idempotent Inbox** | Ensure at-least-once Kafka delivery does not produce duplicate side effects. Each consumed event is inserted into `inbox_events` with a `UNIQUE(event_id)` constraint before business logic executes. | `infrastructure/persistence/inbox_repository.py` |
| **Strangler Fig** | Incrementally migrate legacy synchronous paths to the new event-driven architecture without rewriting the entire module at once. Legacy endpoints are preserved while new command handlers are routed through UoW+Outbox. | `kafka_decision_consumer.py` (routes `ContainerMoved` through handler while legacy paths coexist) |
| **Polyglot Persistence** | Use the right database for each workload: PostgreSQL for ACID transactional state, MongoDB for immutable event logs and analytics, Redis for sub-millisecond cache and real-time counters. | `infrastructure/persistence/postgres.py`, `mongo.py`, `redis.py` |

### References

- [CQRS — Command Query Responsibility Segregation](https://www.linkedin.com/pulse/difference-between-cqrs-cors-pratheek-sridhara-i8mjc/)
- [Unit of Work — Python DDD Patterns](https://medium.com/technology-hits/unit-of-work-python-domain-driven-design-patterns-f07a675588ee)
- [Strangler Fig Pattern — Microsoft Azure Architecture](https://learn.microsoft.com/en-us/azure/architecture/patterns/strangler-fig)
- [Polyglot Persistence — Modern Data Architecture](https://medium.com/@rachoork/polyglot-persistence-a-strategic-approach-to-modern-data-architecture-e2a4f957f50b)

---

## Architecture Overview

```mermaid
flowchart TB
    subgraph Clients
        DE["Decision Engine"]
        GW["API Gateway"]
        KF["Kafka Broker"]
    end

    subgraph DataModule["Data Module (Port 8080)"]
        direction TB
        API["FastAPI Routes"]

        subgraph Domain["domain/"]
            EVT["EventEnvelope"]
            IFC["Interfaces (Ports)"]
        end

        subgraph Application["application/"]
            CMD["Command Handlers<br/>(UoW + Outbox)"]
            QRY["Query Functions<br/>(CQRS reads)"]
        end

        subgraph Infrastructure["infrastructure/"]
            REPO["Repository Adapters"]
            UOW["Unit of Work"]
            KAFKA_C["Kafka Consumer"]
        end

        subgraph Persistence
            PG[(PostgreSQL<br/>Source of Truth)]
            MONGO[(MongoDB<br/>Events + Analytics)]
            REDIS[(Redis<br/>Cache + Counters)]
        end

        subgraph Workers["scripts/"]
            OW["Outbox Worker<br/>(poll + project)"]
        end
    end

    DE <--> API
    GW <--> API
    KF --> KAFKA_C

    API --> CMD
    API --> QRY
    KAFKA_C --> CMD

    CMD --> UOW --> REPO --> PG
    QRY --> REDIS
    QRY -.->|fallback| PG
    QRY -.->|fallback| MONGO

    OW -->|poll PENDING| PG
    OW -->|project| MONGO
    OW -->|project| REDIS
```

---

## Project Structure

```
Data_Module/
├── main.py                          # FastAPI entrypoint + scheduler + lifespan
├── config.py                        # Pydantic Settings (env vars)
├── Dockerfile                       # Container image
├── entrypoint.sh                    # Container startup
├── requirements.txt                 # Python dependencies
│
├── domain/                          # Domain Layer (pure, no framework deps)
│   ├── events.py                    #   EventEnvelope (immutable, 11 fields)
│   │                                #   ConsumeContext (Kafka record metadata)
│   └── interfaces.py                #   Abstract ports: IUnitOfWork, IAppointmentStateRepository,
│                                    #   IAppointmentRepository, IInboxRepository, IOutboxRepository,
│                                    #   IAlertRepository, IDriverRepository, IWorkerRepository,
│                                    #   IVisitRepository
│
├── application/                     # Application Layer (orchestration)
│   ├── schemas.py                   #   Pydantic request/response models
│   ├── use_cases/                   #   Write-side command handlers
│   │   ├── container_moved_handler.py   Inbox → lock → command → Outbox → commit
│   │   ├── appointment_commands.py      cmd_process_decision, cmd_update_status,
│   │   │                                cmd_update_visit_state, cmd_flag_highway_infraction
│   │   ├── worker_handlers.py           Worker CRUD via UoW
│   │   ├── driver_handlers.py           Driver claim + session via UoW
│   │   └── alert_handlers.py            Alert creation + hazmat via UoW
│   └── queries/                     #   Read-side query functions
│       ├── arrival_queries.py           Appointment reads (Redis → Mongo → PG)
│       ├── decision_queries.py          Decision processing + MongoDB events
│       ├── manager_statistics_queries.py Dashboard aggregations
│       ├── statistics_queries.py        Real-time counters + timeline
│       ├── driver_queries.py            Driver lookup + auth
│       ├── worker_queries.py            Worker lookup + auth
│       ├── alert_queries.py             Alert reads
│       ├── cache_queries.py             Redis get-or-cache patterns
│       ├── event_queries.py             MongoDB event reads
│       └── notification_queries.py      Notification CRUD
│
├── infrastructure/                  # Infrastructure Layer (adapters)
│   ├── persistence/
│   │   ├── postgres.py                  SQLAlchemy engine + SessionLocal
│   │   ├── mongo.py                     PyMongo client + 12 collections
│   │   ├── redis.py                     Redis client + dedup + cache helpers
│   │   ├── sql_models.py               ORM models (Appointment, Driver, Worker, ...)
│   │   ├── inbox_outbox_models.py       InboxEvent + OutboxEvent tables
│   │   ├── unit_of_work.py             SqlAlchemyUnitOfWork (8 repositories)
│   │   ├── inbox_repository.py          Dedup via IntegrityError + SHA256 hash
│   │   ├── outbox_repository.py         append / fetch_batch / mark_published
│   │   ├── appointment_state_repository.py  get_for_update (SELECT FOR UPDATE)
│   │   ├── appointment_repository.py    Optimistic concurrency (WHERE version=)
│   │   ├── visit_repository.py          Visit state transitions
│   │   ├── alert_repository.py          Alert persistence
│   │   ├── driver_repository.py         Driver persistence
│   │   └── worker_repository.py         Worker persistence
│   └── messaging/
│       └── kafka_decision_consumer.py   Async consumer + DecisionCorrelator
│
├── routes/                          # HTTP Endpoints (FastAPI routers)
│   ├── arrivals.py                      Appointment CRUD + CQRS reads
│   ├── decisions.py                     Decision Engine integration
│   ├── driver.py                        Driver auth + claim + history
│   ├── worker.py                        Operator/Manager auth
│   ├── alerts.py                        Alert management
│   ├── statistics.py                    Dashboard + real-time metrics
│   ├── notifications.py                 Notification management
│   └── events.py                        Legacy events endpoint
│
├── scripts/                         # Operations
│   ├── simple_outbox_worker.py          Outbox relay: poll → project (Mongo+Redis)
│   │                                    Retry: exp. backoff + jitter, DEAD_LETTER
│   ├── migrationDBv2.sql               Schema migration (inbox, outbox, triggers, indexes)
│   ├── triggers.sql                     PostgreSQL triggers (10 total)
│   ├── indexes.sql                      PostgreSQL indexes (26+ total)
│   ├── data_init_demo.py               PEI 2025 video demo data
│   └── data_init_realistic.py          Realistic Aveiro port data (rich metrics)
│
├── utils/                           # Utilities
│   ├── hashing_pass.py                  bcrypt password hashing
│   ├── rate_limit.py                    Rate limiting
│   └── shift_utils.py                  Shift schedule parsing
│
└── tests/                           # Test Suite (101 tests)
    ├── conftest.py                      Shared fixtures
    ├── test_appointment_commands_uow.py UoW + Outbox integration (20 tests)
    ├── test_appointment_optimistic_concurrency.py Version checks (8 tests)
    ├── test_arrival_id_no_orm_listener.py SQL sequence only (3 tests)
    ├── test_event_dedup_a3.py           event_id dedup (22 tests)
    ├── test_outbox_worker_b1.py         Retry + backoff + DEAD_LETTER (28 tests)
    ├── test_manager_statistics_endpoints.py Dashboard contracts (16 tests)
    ├── test_dashboard_endpoints.py      Dashboard route validation (4 tests)
    └── test_integration.py              Full integration (requires running DBs)
```

---

## Data Flow: ContainerMoved (Event-Driven Pipeline)

The primary write path uses the full Inbox → Command → Outbox → Projection pipeline:

```
Kafka (agent-decision-{gate_id})
  │
  ▼
KafkaDecisionConsumer._dispatch_container_moved()
  │  builds EventEnvelope (UUIDv7 event_id, 11 fields)
  │
  ▼
ContainerMovedHandler.handle(envelope, context)
  ├─ 1. Inbox INSERT (idempotency gate — UNIQUE event_id)
  ├─ 2. Inbox mark PROCESSING
  ├─ 3. Acquire aggregate lock (SELECT ... FOR UPDATE)
  ├─ 4. Execute state transition + business rules
  ├─ 5. Outbox APPEND (same PG transaction)
  ├─ 6. Inbox mark PROCESSED
  ├─ 7. UoW COMMIT (single atomic transaction)
  └─ 8. Kafka offset commit (only after PG commit)
          │
          ▼
    [Outbox Worker — background process]
      ├─ Poll outbox_events WHERE status = 'PENDING'
      ├─ project_to_mongo()  → upsert to appointments_read
      ├─ project_to_redis()  → invalidate + snapshot + counter
      ├─ Mark PUBLISHED (+ published_at timestamp)
      ├─ On failure: retry with exponential backoff + jitter
      └─ After MAX_RETRIES (5): mark DEAD_LETTER
```

---

## Databases

### PostgreSQL — Source of Truth (ACID)

Core entities with referential integrity, triggers, and indexes.

| Entity | Description |
|--------|-------------|
| `Appointment` | Scheduled arrivals — core aggregate with `version` (optimistic concurrency) and `arrival_id` (PRT-XXXX via SQL sequence) |
| `Visit` | Actual gate visits with entry/exit timestamps |
| `Driver` | Truck drivers with session-based auth |
| `Worker` | Port staff — base for Manager and Operator roles |
| `Company` | Transport companies (NIF) |
| `Booking` / `Cargo` | Reservations with hazmat flags |
| `Terminal` / `Gate` / `Dock` | Port infrastructure |
| `Shift` | Work shifts per gate |
| `Alert` | Safety and operational alerts |
| `InboxEvent` | Idempotent Kafka consumer inbox (state machine: RECEIVED → PROCESSING → PROCESSED/FAILED/DEAD_LETTER) |
| `OutboxEvent` | Transactional outbox with retry (state machine: PENDING → PUBLISHED/FAILED/DEAD_LETTER) |

**Triggers (10):** arrival_id sequence, status transition validation, visit auto-completion, entry_time auto-set, alert timestamp, shift_alert_history linking, created_at for booking/worker/driver.

**Migration:** `scripts/migrationDBv2.sql` — safe to re-run (IF NOT EXISTS, OR REPLACE).

### MongoDB — Event Store + CQRS Read Models

| Collection | Purpose |
|------------|---------|
| `agent_detections` | Per-agent detection events (AgentA/B/C) |
| `decision_events` | Full decision journey documents |
| `appointments_read` | CQRS read model (projected by outbox worker) |
| `alerts_read` | Alert read model |
| `drivers_read` / `workers_read` | Reference data projections |
| `statistics_hourly` | Pre-aggregated metrics |
| `notifications` | Operator notifications |

### Redis — Cache + Counters + Dedup

| Key Pattern | TTL | Purpose |
|-------------|-----|---------|
| `dedup:event:{event_id}` | 5min | Idempotent event processing |
| `dedup:plate:{lp}:gate:{id}:tb:{ts}` | 5min | Detection deduplication |
| `decision:plate:{lp}:gate:{id}:...` | 1h | Decision result cache |
| `appointment:{id}:details` | 30min | Hot appointment cache |
| `lp_lookup:{plate}:appointments` | 10min | License plate → appointment |
| `counter:gate:{id}:hour:{h}:*` | 2h | Real-time gate counters |
| `pending_review:{truck_id}` | 30min | Operator decision correlation |

---

## API Endpoints

**Base URL:** `http://localhost:8080/api/v1`
**Swagger UI:** `http://localhost:8080/docs`

### Health & Monitoring

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Service health (PG + Mongo + Redis) |

### Arrivals (Appointments)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/arrivals` | List appointments (paginated) |
| GET | `/arrivals/{id}` | Get by ID (Redis → PG fallback) |
| GET | `/arrivals/pin/{pin}` | Get by access PIN |
| GET | `/arrivals/stats` | Gate statistics (includes infractions) |
| GET | `/arrivals/next/{gate_id}` | Next arrivals for gate |
| GET | `/arrivals/query/license-plate/{plate}` | Query by license plate |
| POST | `/arrivals/{id}/decision` | Process operator decision |
| PATCH | `/arrivals/{id}/highway-infraction` | Flag highway infraction |

### Decisions (Decision Engine Integration)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/decisions/process` | Receive decision from DE |
| POST | `/decisions/query-appointments` | Query candidate appointments |
| POST | `/decisions/detection-event` | Register detection event |

### Drivers (Mobile App)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/drivers/login` | Validate credentials |
| POST | `/drivers/claim` | Claim delivery via PIN |
| GET | `/drivers/me/active` | Active appointment |
| GET | `/drivers/me/today` | Today's deliveries |
| GET | `/drivers/me/history` | Delivery history |
| GET | `/drivers` | List all (backoffice) |

### Workers (Operator/Manager)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/workers/login` | Authentication |
| GET | `/workers/me` | Current worker info |
| GET | `/workers/shifts` | Shift listing |

### Alerts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/alerts` | List alerts |
| GET | `/alerts/active` | Active alerts |
| POST | `/alerts` | Create alert |
| POST | `/alerts/hazmat` | Create hazmat alert (UN/Kemler codes) |
| GET | `/alerts/reference/adr-codes` | ADR code reference |

### Statistics (Manager Dashboard)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/statistics/summary` | Dashboard summary |
| GET | `/statistics/by-company` | Stats by transport company |
| GET | `/statistics/volume` | Volume over time |
| GET | `/statistics/alerts` | Alert breakdown |

### Notifications & Events

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/notifications` | List notifications |
| POST | `/notifications` | Create notification |
| GET | `/events` | Legacy events |

---

## Running

### Docker (Recommended)

```bash
cd src/V_APP
docker-compose up -d

# Verify health
curl http://localhost:8080/api/v1/health
# Expected: {"status": "ok", "components": {"postgres": true, "mongo": true, "redis": true}}

# Seed demo data
docker-compose exec data-module python scripts/data_init_demo.py

# Start outbox worker (separate process)
docker-compose exec data-module python scripts/simple_outbox_worker.py
```

### Local Development

```bash
cd src/V_APP/Data_Module

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure (or use .env file)
export POSTGRES_HOST=localhost POSTGRES_PORT=5432
export POSTGRES_USER=porto POSTGRES_PASSWORD=porto_password POSTGRES_DB=porto_logistica
export MONGO_URL=mongodb://admin:admin123@localhost:27017
export REDIS_HOST=localhost REDIS_PORT=6379
export DECISION_ENGINE_URL=http://localhost:8001

uvicorn main:app --reload --port 8080
```

### Run Tests

```bash
cd src/V_APP/Data_Module

# All tests (101 unit tests — no running DBs required)
PYTHONPATH=. tests/.venv/bin/python -m pytest tests/ \
  --ignore=tests/kafka_decision_consumer_unit_test.py \
  --ignore=tests/test_integration.py -v

# Integration tests (requires running PG, Mongo, Redis)
PYTHONPATH=. tests/.venv/bin/python -m pytest tests/test_integration.py -v
```

### Database Migration

```bash
# Apply schema v2 (safe to re-run)
psql -U porto -d porto_logistica -f scripts/migrationDBv2.sql
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_HOST` | `postgres` | PostgreSQL hostname |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_USER` | `porto` | Database user |
| `POSTGRES_PASSWORD` | `porto_password` | Database password |
| `POSTGRES_DB` | `porto_logistica` | Database name |
| `MONGO_URL` | `mongodb://admin:admin123@mongo:27017` | MongoDB connection string |
| `REDIS_HOST` | `redis` | Redis hostname |
| `REDIS_PORT` | `6379` | Redis port |
| `DECISION_ENGINE_URL` | `http://decision-engine:8001` | Decision Engine endpoint |
| `DEBUG_MODE` | `false` | Bypass sequential delivery validation |
| `TOKEN_EXPIRY_HOURS` | `24` | Driver session token expiry |

---

## Inter-Service Communication

### Decision Engine → Data Module

| Endpoint | Purpose |
|----------|---------|
| `POST /decisions/query-appointments` | Query candidates by gate + time window |
| `POST /decisions/process` | Send final decision (ACCEPTED/REJECTED/MANUAL_REVIEW) |
| `POST /alerts/hazmat` | Create hazmat alerts (UN/Kemler codes) |
| `GET /arrivals/query/license-plate/*` | Lookup appointments by detected plate |

### Kafka Topics Consumed

| Topic | Handler | Pattern |
|-------|---------|---------|
| `agent-decision-{gate_id}` | `ContainerMovedHandler` | Inbox → UoW → Outbox |
| `operator-decision-{gate_id}` | `DecisionCorrelator` | Redis correlation + process |
| `infraction-decision-{gate_id}` | `_store_infraction_decision` | Legacy path |

### API Gateway → Data Module

| Route Prefix | Frontend Consumer |
|--------------|-------------------|
| `/arrivals/*` | Operator Dashboard (React) |
| `/drivers/*` | Driver Mobile App (React Native) |
| `/workers/*` | Operator/Manager Login |
| `/alerts/*` | Operator Dashboard |
| `/statistics/*` | Manager Dashboard |
