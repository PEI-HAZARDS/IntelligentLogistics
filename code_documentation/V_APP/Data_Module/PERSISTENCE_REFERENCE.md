# Persistence Reference

> Domain models, interfaces, infrastructure implementations (PostgreSQL, MongoDB, Redis, Kafka), utilities, scripts, and bootstrap.

---

## Domain Layer

### `domain/events.py`

Two frozen dataclasses with no infrastructure dependency — usable in unit tests without any DB or Kafka setup.

**`EventEnvelope`** (11 required fields, `frozen=True`):

| Field | Type | Notes |
|-------|------|-------|
| `event_id` | `str` | UUIDv7 via `new_event_id()`; idempotency key in Inbox |
| `correlation_id` | `str` | Business transaction trace |
| `causation_id` | `str \| None` | Causing event ID; `None` for originating events |
| `aggregate_type` | `str` | e.g. `"appointment"` |
| `aggregate_id` | `str` | e.g. appointment ID |
| `event_type` | `str` | e.g. `"ContainerMoved"`, `"AppointmentStateChanged"` |
| `event_version` | `int` | Schema version |
| `occurred_at` | `datetime` | UTC timestamp |
| `producer` | `str` | e.g. `"data-module"` |
| `partition_key` | `str` | Kafka routing key |
| `payload` | `dict[str, Any]` | Event-specific data |

**`ConsumeContext`:** `topic`, `partition`, `offset`, `key`, `headers` — Kafka record metadata stored with the inbox row.

**UUIDv7 utilities (Phase 8):**
- `UUIDv7Str` — `NewType` alias for static analysis
- `is_valid_uuidv7(value) -> bool` — validates format
- `new_event_id() -> UUIDv7Str` — pure-stdlib generator; used by all `_append_outbox` helpers

---

### `domain/interfaces.py`

Abstract port layer. Use-cases import only from here; concrete implementations live in `infrastructure/persistence/` and are wired by `SqlAlchemyUnitOfWork.__enter__`.

**`IUnitOfWork`** — context manager grouping all repository mutations in a single PG transaction.
- Methods: `commit()`, `rollback()`, `__enter__()`, `__exit__()`
- Repos: `appointment_state`, `appointments`, `alerts`, `drivers`, `workers`, `visits`, `inbox`, `outbox`

**`IAppointmentStateRepository`** — row-level locking for aggregate transitions:
- `get_for_update(id)` → `SELECT … FOR UPDATE`; returns `dict | None`
- `save_state_transition(id, new_state, metadata)` — persists status + optional fields

**`IAppointmentRepository`** — optimistic-concurrency updates:
- `get_by_arrival_id(arrival_id)` → `dict | None`
- `update_status(id, status, *, version)` → rows affected; `0` = concurrency conflict

**`IInboxRepository`** — idempotency gate (Guardrails 1, 4):
- `try_insert_received(event, ctx)` → `True` = new, `False` = duplicate
- `mark_processing(event_id)`, `mark_processed(event_id)`, `mark_failed(event_id, error, retryable)`

**`IOutboxRepository`** — transactional outbox (Guardrail 3):
- `append(event, *, topic, key)` — writes `EventEnvelope` row within current transaction
- `fetch_batch(batch_size)`, `mark_published(outbox_id)`, `mark_publish_failed(outbox_id, error)`

**`IAlertRepository`:** `add(*, visit_id, alert_type, description, image_url, appointment_id)`, `get_appointment_visit_id(appointment_id)`

**`IDriverRepository`:** `get_by_license(lic)`, `get_appointment_for_claim(arrival_id)`, `get_next_active_appointment_id(lic)`

**`IWorkerRepository`:** `get_by_email_active`, `get_by_num_worker`, `add_worker`, `add_role`, `remove_role`, `update_fields`, `email_exists`, `num_worker_exists`, `has_role`

**`IVisitRepository`:** `create(appointment_id, ...)`, `update_state(appointment_id, new_state, out_time)`, `get_by_appointment(appointment_id)`

---

## PostgreSQL Layer

### `infrastructure/persistence/sql_models.py`

SQLAlchemy declarative schema: enums, all ORM models, relationships. No query logic — that lives in repository modules. `arrival_id` PIN is populated by a PostgreSQL trigger (`trg_generate_arrival_id`), not by any ORM hook.

**Enums:**

| Python enum | PG type | Values |
|-------------|---------|--------|
| `ShiftType` | — | `MORNING` / `AFTERNOON` / `NIGHT`; `get_hours()` returns `(start_time, end_time)` |
| `appointment_status_enum` | PG ENUM | scheduled, in_transit, in_process, unloading, canceled, delayed, completed |
| `delivery_status_enum` | PG ENUM | not_started, unloading, completed |
| `operational_status_enum` | PG ENUM | maintenance, operational, closed |
| `access_level_enum` | PG ENUM | admin, basic |
| `type_alert_enum` | PG ENUM | generic, safety, problem, operational |

**Models:**

| Model | Key Details |
|-------|-------------|
| `Terminal` | `hazmat_approved` flag; back-refs to `docks`, `appointments` |
| `Dock` | Composite PK `(terminal_id, bay_number)`; `current_usage` is `operational_status_enum` |
| `Gate` | Entry/exit point; `estado` column added Phase 3 (BR-14) |
| `Company` | PK `nif`; parent of `Driver` and `Truck` |
| `Driver` | PK `drivers_license`; bcrypt `password_hash`; `current_appointment_id` tracks sequential deliveries |
| `Truck` | PK `license_plate`; FK `company_nif` |
| `Worker` | PK `num_worker`; `email` UNIQUE; disjoint Manager/Operator specialisation |
| `Manager` / `Operator` | PK+FK `num_worker`; `access_level` on Manager |
| `Shift` | Composite PK `(gate_id, shift_type, date)`; computed `start_time`/`end_time` from `ShiftType.get_hours()` |
| `Booking` | PK `reference`; `direction` enum |
| `Cargo` | FK `booking_reference`; `state` is `physical_state_enum` |
| `Appointment` | Central aggregate. `arrival_id` (trigger PIN), `status`, `version` (optimistic concurrency), `highway_infraction`. Computed: `computed_status`, `is_delayed`, `delay_minutes` |
| `Visit` | PK+FK `appointment_id` (1:1); composite FK to `Shift`; `entry_time`/`out_time`; `state` is `delivery_status_enum` |
| `Alert` | Nullable `visit_id` for pre-visit alerts; `type` is `type_alert_enum`; `severity` SMALLINT added Phase 3 (BR-11) |
| `DriverVehicle` | Added Phase 3 (BR-52). `(driver_license, truck_license_plate, start_date, end_date NULL)` — temporal history |
| `PendingReview` | Added Phase 3 (PD-01). Durable operator review queue |
| `ShiftAlertHistory` | Junction between `Shift` and `Alert`; auto-populated by trigger |

**Known Issues:** `computed_status` uses `datetime.now()` (local time) — should be UTC.

---

### `infrastructure/persistence/unit_of_work.py`

`SqlAlchemyUnitOfWork` opens a SQLAlchemy `Session` on `__enter__`, instantiates all repository implementations bound to that session, and auto-rolls-back on any unhandled exception. All repos share one `Session` — inbox insert + domain write + outbox append committed atomically.

| Attribute | Interface |
|-----------|-----------|
| `appointment_state` | `IAppointmentStateRepository` |
| `appointments` | `IAppointmentRepository` |
| `alerts` | `IAlertRepository` |
| `drivers` | `IDriverRepository` |
| `workers` | `IWorkerRepository` |
| `visits` | `IVisitRepository` |
| `inbox` | `IInboxRepository` |
| `outbox` | `IOutboxRepository` |

**Known Issues:** No retry policy on transient DB errors during `commit()`.

---

### `infrastructure/persistence/appointment_repository.py`

Concrete `IAppointmentRepository`. `update_status` returns rows affected — `0` means optimistic concurrency conflict; caller must handle (retry or raise `409`).

| Method | Returns |
|--------|---------|
| `get_by_arrival_id(arrival_id)` | `Optional[dict]` |
| `update_status(id, status, *, version)` | `int` — 0 = conflict |

---

### `infrastructure/persistence/appointment_state_repository.py`

Pessimistic row locking via `SELECT … FOR UPDATE`. Used when the handler needs to hold a lock while computing next state.

| Method | Returns |
|--------|---------|
| `get_for_update(id)` | `Optional[dict]` — lock held until commit |
| `save_state_transition(id, new_state, metadata)` | `None` — raises `NoResultFound` if missing |

`metadata` accepted keys: `gate_in_id`, `gate_out_id`, `notes`, `highway_infraction`.

**Known Issues:** `version` defaults to `1` when column is `NULL` — may hide data integrity issues.

---

### `infrastructure/persistence/inbox_repository.py`

Transactional Inbox (Guardrails 1, 4). `UNIQUE(event_id)` constraint catches duplicates at DB level.

Status lifecycle: `RECEIVED → PROCESSING → PROCESSED | FAILED | DEAD_LETTER`

| Method | Returns |
|--------|---------|
| `try_insert_received(event, ctx)` | `True` = new; `False` = duplicate (rolls back session) |
| `mark_processing(event_id)` | `None` |
| `mark_processed(event_id)` | `None` |
| `mark_failed(event_id, error, retryable)` | `None` — increments `retry_count` |

---

### `infrastructure/persistence/outbox_repository.py`

Transactional Outbox (Guardrail 3). Command handlers call `append` inside the UoW; the outbox worker polls `PENDING` rows and projects them.

Status lifecycle: `PENDING → PUBLISHED` on success; `PENDING → FAILED → DEAD_LETTER` after `MAX_RETRIES`.

| Method | Returns |
|--------|---------|
| `append(event, *, topic, key)` | `None` — called before `uow.commit()` |
| `fetch_batch(batch_size)` | `list[dict]` — FIFO PENDING rows |
| `mark_published(outbox_id)` | `None` |
| `mark_publish_failed(outbox_id, error)` | `None` |

---

### `infrastructure/persistence/visit_repository.py`

Manages `Visit` aggregate persistence. Auto-creates missing `Shift` rows to prevent FK violations.

| Method | Returns |
|--------|---------|
| `create(appointment_id, shift_gate_id, shift_type, shift_date, entry_time)` | `Optional[dict]` — idempotent |
| `update_state(appointment_id, new_state, out_time)` | `Optional[dict]` — sets `out_time = now()` when completed |
| `get_by_appointment(appointment_id)` | `Optional[dict]` |

**Known Issues:** `_ensure_shift_exists` has a race condition in high-concurrency scenarios. `datetime.now()` (no timezone) used for timestamps — should be UTC.

---

## MongoDB Layer

### `infrastructure/persistence/mongo.py`

Module-level `MongoClient`; `create_indexes()` called at import time (idempotent).

**Collections:**

| Variable | Collection | Purpose |
|----------|------------|---------|
| `agent_detections_collection` | `agent_detections` | Per-agent detection events (TTL 30d) |
| `decision_events_collection` | `decision_events` | Complete decision journey (outbox projected, TTL 90d) |
| `statistics_hourly_collection` | `statistics_hourly` | Pre-aggregated hourly stats |
| `notifications_collection` | `notifications` | Operator/driver UI notifications (TTL 30d) |
| legacy (`detections`, `events`, etc.) | — | Backward compatibility only |

**Key indexes:** `agent_detections.detection_id` (UNIQUE), `decision_events.decision_id` (UNIQUE, partial), `decision_events.appointment_id` (UNIQUE, partial — BR-37), `statistics_hourly.(gate_id, hour_bucket)` (UNIQUE).

**Query helpers:** `get_agent_detections_for_truck`, `get_unprocessed_detections`, `get_decision_by_truck`, `get_decision_by_appointment`, `get_pending_manual_reviews`, `get_hourly_statistics`, `validate_agent_detection_schema`, `validate_decision_event_schema`.

**Known Issues:** No TTL index on `notifications_collection`. `idx_truck_created` on `decision_events` is non-unique (BR-37 gap).

---

## Redis Layer

### `infrastructure/persistence/redis.py`

Module-level `redis.Redis` client. All errors caught and logged — functions degrade gracefully (cache miss / allowed). No business logic here.

**TTL Constants & Key Patterns:**

| Constant | TTL (s) | Key pattern | Purpose |
|----------|---------|-------------|---------|
| `TTL_DEDUP` | 300 | `dedup:event:{event_id}` | Event-id idempotency (BR-30) |
| — | 300 | `plate:{lp}:gate:{gid}:tb:{tb}` | Legacy time-window dedup (BR-31) |
| `TTL_DECISION_CACHE` | 3600 | `decision:plate:{lp}:gate:{gid}:tb:{tb}` | Decision result (BR-32) |
| `TTL_APPOINTMENT_HOT` | 1800 | `appointment:{id}:details` | Hot appointment data (BR-33) |
| `TTL_LICENSE_PLATE_LOOKUP` | 600 | `lp_lookup:{lp}:appointments` | Plate → appointment IDs (BR-34) |
| `TTL_COUNTER_REALTIME` | 7200 | `counter:gate:{gid}:hour:{ts}:{metric}` | Hourly counters (BR-35) |
| `TTL_RATE_LIMIT` | 60 | `ratelimit:api:{endpoint}:{client_id}` | Rate limiting |
| `TTL_OPERATOR_SESSION` | 3600 | `operator:{id}:session` | Operator session |

**Function groups:** Deduplication, Decision cache, Hot appointment cache, License plate lookup, Real-time counters, Rate limiting, Operator session, Health/stats.

**Known Issues:** `pending_review:{truck_id}` keys have no gate qualifier — collision-prone in multi-gate deployments (PD-01). `is_duplicate_and_mark` is deprecated.

---

## Messaging Layer

### `infrastructure/messaging/kafka_decision_consumer.py`

Two cooperating classes:

**`DecisionCorrelator`** — manages the two-step decision flow: `ACCEPTED` → dispatch immediately (source="agent"); `MANUAL_REVIEW` → park in Redis until operator decision arrives; operator decision → fetch+merge+dispatch (source="operator").

**`KafkaDecisionConsumer`** — async loop subscribing to `agent-decision-{gate_id}`, `operator-decision-{gate_id}`, and `infraction-decision-{gate_id}` topics. Commits Kafka offset **only after** `ContainerMovedHandler` returns (Guardrail 4). Permanent failures go to DLQ via `DLQProducer`.

```
Kafka topics → KafkaDecisionConsumer._consume_loop
    ├─ agent msg    → DecisionCorrelator.process_agent_decision
    │     ACCEPTED  → _dispatch_container_moved → Kafka offset commit
    │     MANUAL_REVIEW → cmd_store_pending_review (UoW)
    ├─ operator msg → DecisionCorrelator.process_operator_decision
    │     fetch+merge Redis pending → _dispatch_container_moved
    └─ infraction msg → _store_infraction_decision
          Mongo audit + PG highway_infraction flag (UoW) + PG alert (UoW) + Mongo notifications
```

**Configuration:** `KAFKA_BOOTSTRAP`, `GATE_ID`, `DECISION_GATE_IDS` (JSON array), `INFRACTION_GATE_IDS` (JSON array).

**Known Issues:** `_store_infraction_decision` has no inbox dedup — replayed messages double-write. `MAX_TRANSIENT_RETRIES = 3` is declared but unused.

---

### `infrastructure/messaging/dlq_producer.py`

Dead Letter Queue producer — routes permanently-failed Kafka messages to `<source-topic>.DLQ`.

**`DLQProducer`:**
- `send_to_dlq(*, source_topic, ..., error, attempt_count)` — builds envelope + publishes. DLQ failures logged at `CRITICAL`.
- `is_permanent_error(error)` → `True` for `JSONDecodeError`, `KeyError`, `TypeError`, `ValueError`, `AttributeError`.

DLQ envelope captures: original topic/partition/offset, key, headers, payload, error class, stack trace hash (MD5), service, attempt count, timestamps.

---

## Scripts

### `scripts/simple_outbox_worker.py`

Standalone outbox relay worker. On startup warms Redis hot cache with all PG appointments. Then polls PENDING outbox rows in batches, projects each to MongoDB + Redis, marks `PUBLISHED`. Failed rows retry with exponential backoff + jitter up to `MAX_RETRIES`, then `DEAD_LETTER`. Graceful shutdown on SIGTERM/SIGINT.

```
startup → warm_up_redis_cache()
poll loop:
  fetch_projectable_rows(session, BATCH_SIZE)
    ├── project_to_mongo(row)    → MongoDB upsert by event_id (idempotent)
    ├── project_to_redis(row)    → invalidate + re-fetch + cache appointment
    └── row.status = PUBLISHED | FAILED | DEAD_LETTER
  session.commit()
  sleep(POLL_INTERVAL_SECONDS)
```

| Constant | Default |
|----------|---------|
| `BATCH_SIZE` | 50 |
| `POLL_INTERVAL_SECONDS` | 2 |
| `MAX_RETRIES` | 5 |
| `BACKOFF_BASE_SECONDS` | 2 |
| `BACKOFF_MAX_SECONDS` | 60 |

**Known Issues:** `project_to_redis` re-fetches full `Appointment` ORM on every event. DEAD_LETTER rows not forwarded to Kafka DLQ topic.

---

### `scripts/data_init_demo.py`

Demo data initialiser for PEI 2025 presentation. Idempotent — skips if any `Worker` row already exists.

Seeds:
- 6 companies (PT, ES, DE, FR), 10 drivers, 14 extra trucks
- 3 Porto de Aveiro terminals (Norte, Granéis Sólidos, Granéis Líquidos — the only HAZMAT-approved)
- 9 docks (3 per terminal), 3 gates
- Today's Video1 plates (scheduled) + Video2 plates (highway_infraction flag)
- 14 bonus today appointments (completed + in_process with visits and alerts)
- 5 historical days (~60 appointments, all completed with visits and ~25% random alerts)

**Env-var contract (required by unit tests):** `DEMO_VIDEO1_PLATES`, `DEMO_VIDEO2_PLATES`, `MAX_ARRIVALS`, sliced as `VIDEO1_PLATES[:MAX_ARRIVALS]`.

**Demo credentials:**

| Type | Identifier | Password |
|------|-----------|----------|
| Operator (web) | `worker@porto.pt` | `password123` |
| Manager (web) | `manager@example.pt` | `password123` |
| Driver (mobile) | `PT12345678` | `driver123` |

```bash
# Reset and re-seed
docker compose down -v && docker compose up -d
docker-compose exec data-module python scripts/data_init_demo.py
```

---

## Utils

### `utils/plate_validation.py`

License-plate format validation and agent-detection consensus checks. No infrastructure dependencies.

**Added Phase 13 (2026-04-24) — resolves BR-49 and BR-18.**

| Function | Description |
|----------|-------------|
| `is_valid_plate(plate)` | Strict PT format: `^[A-Z]{2}-\d{2}-[A-Z]{2}$` (case-insensitive) |
| `is_valid_plate_relaxed(plate)` | OCR-normalised: strips hyphens/spaces, matches `^[A-Z0-9]{4,10}$` |
| `normalise_plate(plate)` | Canonical form for DB lookups: strip hyphens/spaces, uppercase |
| `validate_consensus(detection, threshold=0.7)` | Rejects detection if `confidence < threshold` or `origem` absent |

**Wiring:** `routes/decisions.py` Pydantic validator (422), `routes/arrivals.py` path param (400), `mongo.validate_agent_detection_schema`, `decision_queries.validate_consensus`.

---

### `utils/rate_limit.py` — DELETED (Phase 11)

Removed — had no active callers. Canonical rate-limit implementation is `redis.check_rate_limit()` in `infrastructure/persistence/redis.py`, wired into routes directly.

---

## Bootstrap

### `config.py`

`Settings` class (Pydantic `BaseSettings`) reads all configuration from env vars with `.env` fallback. Module-level `settings` singleton imported throughout.

| Key Attribute | Default |
|--------------|---------|
| `postgres_host/port/user/password/db` | `postgres` / `5432` / via env |
| `mongo_host/port` | `mongo` / `27017` |
| `redis_host/port` | `redis` / `6379` |
| `kafka_bootstrap` | `kafka:29092` |
| `jwt_secret` | **DEPRECATED** — weak default; must override in deployment |
| `debug_mode` | `False` — bypasses sequential delivery order check |
| `token_expiry_hours` | `24` |
| `api_prefix` | `"/api/v1"` |

**Property:** `mongo_url` → constructs `mongodb://user:pass@host:port`.

---

### `main.py`

FastAPI entry-point. Configures CORS, registers all routers under `/api/v1`, manages lifespan (startup checks + Kafka consumer + background scheduler + graceful shutdown). OpenTelemetry tracing (OTLP → Tempo) and Prometheus `/metrics` configured here.

**Background task** `update_delayed_appointments()` — runs every 5 min; marks overdue `in_transit` appointments `delayed` via UoW + Outbox. At midnight processes prior day's lingering rows.

```
lifespan startup:
    ├─ Base.metadata.create_all()       → PostgreSQL schema init
    ├─ mongo_client.admin.command("ping")
    ├─ redis_client.ping()
    ├─ asyncio.create_task(update_delayed_appointments())
    └─ KafkaDecisionConsumer().start()

GET /api/v1/health → {status, components: {postgres, mongo, redis}, decision_engine_url}

lifespan shutdown:
    ├─ consumer.stop()
    ├─ scheduler.cancel()
    ├─ mongo_client.close()
    └─ redis_client.close()
```

**Known Issues:** CORS `allow_origins=["*"]` — should be locked to specific origins. `asyncio.CancelledError` is re-raised in shutdown, causing a spurious uvicorn error.

---

## Related Docs

- [QUERIES_REFERENCE.md](QUERIES_REFERENCE.md)
- [USE_CASES_REFERENCE.md](USE_CASES_REFERENCE.md)
- [ROUTES_REFERENCE.md](ROUTES_REFERENCE.md)
- [SCHEMA_REFERENCE.md](SCHEMA_REFERENCE.md)
- [DATA_FLOW.md](DATA_FLOW.md)
- [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md)
- [KNOWN_DEVIATIONS.md](KNOWN_DEVIATIONS.md)
