# Data Module Refactor Plan (EDA + Polyglot Resilience)

> **Last updated:** 2026-03-20
> **Status legend:** DONE | PARTIAL | TODO | BLOCKED
>
> **Priority override (2026-03-20):** Demo deadline Tuesday morning.
> Execution order: Step 0 (assess endpoints) → Step 1 (fix STUB/BROKEN) → Step 2 (A1-B1 refactor).
> Deferred to after Tuesday: B2, C1, C2, D1.

## Scope and constraints

- Runtime: Python 3.12 / FastAPI (uvicorn).
- Persistence: PostgreSQL (source of truth), MongoDB (event/audit + analytics timeline + CQRS read models), Redis (hot cache + dedup + sessions + counters).
- Broker: Apache Kafka (KRaft mode, single broker in V_APP docker-compose).
- Frontends:
  - Gate Operator and Logistics Manager (React + Vite — dual-mode SPA)
  - Driver (React Native + Expo)
- Mandatory patterns:
  - Idempotency Pattern
  - Transactional Outbox/Inbox
  - CQRS
  - Repository + Unit of Work

---

## 1) Risk Analysis (current state)

### 1.1 Consistency and atomicity risks

1. **Non-atomic polyglot writes in command path.** — PARTIAL mitigation (improved 2026-03-20)
- The clean path (`ContainerMovedHandler`) writes only to PostgreSQL (state + outbox + inbox) in a single UoW transaction. Mongo/Redis are updated asynchronously by the outbox worker.
- ~~**Still violated in:** `decision_queries.py` (direct PG+Mongo+Redis writes), `arrival_queries.py` (PG+alert in separate transaction).~~ **Fixed (2026-03-20):** PG writes in `decision_queries.py` and `arrival_queries.py` now go through `appointment_commands.py` command handlers via UoW+Outbox. Mongo/Redis writes remain as async projections (acceptable — will become outbox-driven when outbox worker publishes to Kafka).
- **Still violated in:** `notifications.py` route (direct Mongo writes).
- **Files involved:** `routes/notifications.py`.

2. **No transactional coupling between DB write and event publication.** — PARTIAL mitigation (improved 2026-03-20)
- The ContainerMoved flow uses Inbox+Outbox+UoW correctly.
- ~~Legacy decision and infraction paths still write to Mongo directly from route handlers.~~ **Fixed (2026-03-20):** All demo-critical PG writes now produce outbox events in the same transaction.
- **Still exposed:** `_store_infraction_decision()` in Kafka consumer does direct Mongo writes without inbox dedup.

3. **Offset-commit safety gap.** — DONE for ContainerMoved
- `KafkaDecisionConsumer._dispatch_container_moved()` commits Kafka offset ONLY after `ContainerMovedHandler` returns successfully.
- **Still exposed:** `_store_infraction_decision()` does not use inbox/outbox, no offset safety.

### 1.2 Idempotency and duplication risks

4. **Event-id based dedup for decision pipeline.** — DONE
- `redis.py:is_duplicate_event(event_id)` provides atomic SET NX with key `dedup:event:{event_id}`.
- `decision_queries.is_duplicate_and_mark()` prefers `event_id` when provided; falls back to legacy time-window with deprecation warning.
- `DecisionIncomingRequest` schema accepts optional `event_id` from Decision Engine.
- `process_incoming_decision()` passes `event_id` through to dedup.
- ContainerMoved path still uses Inbox `UNIQUE(event_id)` for true idempotency.

5. **Missing immutable event identity contract.** — DONE
- `EventEnvelope` dataclass in `domain/events.py` enforces all 11 required fields including UUIDv7 `event_id`.
- Used by `ContainerMovedHandler` and `KafkaDecisionConsumer._dispatch_container_moved()`.

### 1.3 Concurrency and race-condition risks

6. **arrival_id generation race.** — DONE (2026-03-20)
- ~~ORM `before_insert` listener in `sql_models.py` did `max(arrival_id)+1` — race-prone under concurrent inserts.~~ **Removed.**
- SQL trigger (`triggers.sql:156`) uses `appointment_arrival_seq` sequence — concurrency-safe. **Now the only generation path.**
- Unused imports (`event`, `select`, `object_session`) cleaned from `sql_models.py`.
- Test: `tests/test_arrival_id_no_orm_listener.py` — 3 unit tests verify no ORM listener remains.

7. **Redis pending review correlation key can overwrite by truck_id collisions.** — TODO
- `DecisionCorrelator` in `kafka_decision_consumer.py` uses `pending_review:{truck_id}` with 30min TTL.
- If truck_id is reused or delayed messages arrive out-of-order, wrong operator decision can be merged.

8. **Shift and status mutation races.** — DONE (2026-03-20)
- Status can be updated by: scheduler (`main.py` background task), manual operator actions (routes), decision consumer (`ContainerMovedHandler`), visit completion trigger (`triggers.sql:69`).
- ~~`AppointmentRepository.update_status()` ignored version parameter.~~ **Fixed:** now includes `WHERE version = <read_version>` and increments version on success.
- ~~Appointment ORM had no `version` column.~~ **Fixed:** `version INTEGER NOT NULL DEFAULT 1` added.
- `ContainerRepository.get_for_update()` now returns `version` in the dict; `save_state_transition()` increments it.
- Migration: `scripts/migration_appointment_version.sql` (reversible).
- Test: `tests/test_appointment_optimistic_concurrency.py` — 8 unit tests.
- **Still exposed:** Legacy paths (`arrival_queries.update_appointment_status`, scheduler) do not use optimistic concurrency yet — they need migration to UoW+repository in future iterations.

### 1.4 Query/API contract risks

9. **Frontend/backend endpoint drift.** — PARTIAL (improved 2026-03-20)
- ~~Statistics routes had 4 missing endpoints for manager dashboard.~~ **Fixed (2026-03-20):** Added `/statistics/summary`, `/statistics/by-company`, `/statistics/volume`, `/statistics/alerts` with real PostgreSQL queries matching frontend `statistics.ts` contract.
- Driver app uses `session_token` from login response but backend generates simple tokens, no JWT, no middleware validation.
- **Files:** `application/queries/dashboard_queries.py` (NEW), `routes/statistics.py` (updated), `application/use_cases/driver_handlers.py`, `routes/driver.py`.

10. **Read pressure on Postgres due to polling and insufficient Redis read model contract.** — PARTIAL mitigation
- `arrivals.py` route has CQRS: Redis → PG fallback for single appointment, MongoDB → PG fallback for lists.
- `driver.py`, `alerts.py` routes still read directly from PostgreSQL with no Redis projection.
- Dashboard summary (`statistics.py:dashboard_summary`) calls 6 queries without caching.

### 1.5 Schema/model quality risks

11. **Domain overlap and ambiguity.** — TODO
- Company/Driver/Truck/Appointment relation exists, but scheduling and shift assignment logic has mixed responsibilities and inconsistent ownership.

12. **Trigger + app logic duplication.** — PARTIAL
- Delayed status: computed in app (`Appointment.computed_status` property), optional SQL function (`fn_sync_delayed_appointments`), and scheduler update (`main.py` background task). Three sources for the same concept.
- Visit completion: SQL trigger (`fn_check_visit_completion`) auto-updates appointment status — app layer may not be aware of this side-channel mutation.

---

## 2) New Data Flow (ContainerMoved step-by-step)

### Event envelope contract — DONE

Implemented in `domain/events.py` as frozen dataclass `EventEnvelope`:

- event_id (UUIDv7) — `str`
- correlation_id — `str`
- causation_id — `Optional[str]`
- aggregate_type — `str` (e.g. `”appointment”`)
- aggregate_id — `str`
- event_type — `str` (e.g. `”ContainerMoved”`)
- event_version — `int`
- occurred_at — `datetime` (UTC)
- producer — `str`
- partition_key — `str`
- payload — `dict[str, Any]`

### Step-by-step flow — implementation status

| Step | Description | Status | File(s) |
|------|-------------|--------|---------|
| 1 | Producer publishes ContainerMoved | DONE | `kafka_decision_consumer.py:241-253` builds envelope |
| 2 | Consumer receives Kafka record | DONE | `kafka_decision_consumer.py:178-223` consume loop |
| 3 | Inbox insert (idempotency gate) | DONE | `container_moved_handler.py:57-63`, `inbox_repository.py` |
| 4 | Acquire aggregate lock (FOR UPDATE) | DONE | `container_moved_handler.py:68-75`, `appointment_state_repository.py:get_for_update()` |
| 5 | Execute command + Outbox append | DONE | `container_moved_handler.py:78-108` |
| 6 | Commit UnitOfWork | DONE | `container_moved_handler.py:114` |
| 7 | Commit Kafka offset after success | DONE | `kafka_decision_consumer.py:273-276` |
| 8 | Outbox relay publishes to Kafka | **TODO** | `simple_outbox_worker.py` projects to Mongo/Redis directly, does NOT publish to Kafka |
| 9 | Projection workers with checkpoint | **PARTIAL** | Outbox worker projects to Mongo+Redis with retry+backoff+DEAD_LETTER. No `projection_checkpoint` yet. |
| 10 | Frontend delivery (WS + REST) | **PARTIAL** | `arrivals.py` has CQRS reads; WebSocket exists in `api_gateway` but not projection-triggered |
| 11 | Observability and SLO checks | **TODO** | Prometheus `/metrics` endpoint exists but no inbox/outbox/projection-specific metrics |

### Current outbox worker state (`scripts/simple_outbox_worker.py`)

**What works:**
- Polls `outbox_events` table for `status = 'PENDING'` and retryable `FAILED` rows (batch of 50, 2s interval)
- Projects `AppointmentStateChanged` events to MongoDB (`appointments_read` collection — upsert by id)
- Projects to Redis (invalidate stale cache → full snapshot → increment counter)
- Marks rows as `PUBLISHED` after successful projection
- Per-event error handling (marks `FAILED`, continues batch)
- **Retry with exponential backoff + jitter** (2^n seconds, capped at 60s, +0-2s jitter) — DONE (2026-03-20)
- **DEAD_LETTER** after MAX_RETRIES (5) or permanent errors (KeyError, ValueError, TypeError) — DONE (2026-03-20)
- **Graceful shutdown** via SIGTERM/SIGINT signal handling — DONE (2026-03-20)
- `OutboxEvent` model extended with `retry_count` (default 0) and `next_retry_at` columns — DONE (2026-03-20)
- Error classification: permanent (contract/domain) → immediate DEAD_LETTER, transient → retry with backoff

**What's missing:**
- ~~Not containerized~~ — **DONE** (2026-03-20): `outbox-worker` service in `docker-compose.yml`
- No `projection_checkpoint` table — on restart, re-scans all PENDING (safe but wasteful)
- No Kafka publish step — projects directly instead of publishing to Kafka for separate projectors
- No Prometheus metrics (outbox lag, projection lag, failure rate)

---

## 3) Contract Design (interfaces)

### Planned vs. implemented

| Interface | Planned | Implemented | File |
|-----------|---------|-------------|------|
| `EventEnvelope` | Yes | DONE | `domain/events.py` |
| `ConsumeContext` | Yes | DONE | `domain/events.py` |
| `IEventConsumer` | Yes | **TODO** — Kafka consumer is concrete, no abstraction | — |
| `IEventPublisher` | Yes | **TODO** — no publisher abstraction exists | — |
| `IInboxRepository` | Yes | DONE | `domain/interfaces.py`, `infrastructure/persistence/inbox_repository.py` |
| `IOutboxRepository` | Yes | DONE | `domain/interfaces.py`, `infrastructure/persistence/outbox_repository.py` |
| `IAppointmentStateRepository` | Yes | DONE | `domain/interfaces.py`, `infrastructure/persistence/appointment_state_repository.py` |
| `IAppointmentRepository` | Yes | DONE (but `update_status` version check is a no-op) | `infrastructure/persistence/appointment_repository.py` |
| `IAlertRepository` | Extended | DONE | `domain/interfaces.py`, `infrastructure/persistence/alert_repository.py` |
| `IDriverRepository` | Extended | DONE | `domain/interfaces.py`, `infrastructure/persistence/driver_repository.py` |
| `IWorkerRepository` | Extended | DONE | `domain/interfaces.py`, `infrastructure/persistence/worker_repository.py` |
| `IMetricEventRepository` | Yes | **TODO** — no implementation | — |
| `ICacheService` | Yes | **TODO** — Redis functions exist but no abstraction layer | — |
| `IUnitOfWork` | Yes | DONE (7 repos, exceeds plan's 4) | `domain/interfaces.py`, `infrastructure/persistence/unit_of_work.py` |
| `IContainerMovedHandler` | Yes | DONE (concrete, not via interface) | `application/use_cases/container_moved_handler.py` |

### Current interface code

The implemented interfaces live in `domain/interfaces.py` and extend the original plan with 3 additional repositories (`IAlertRepository`, `IDriverRepository`, `IWorkerRepository`). The `IUnitOfWork` exposes 7 repositories:

```python
class IUnitOfWork(ABC):
    appointment_state: IAppointmentStateRepository
    appointments: IAppointmentRepository
    alerts: IAlertRepository
    drivers: IDriverRepository
    workers: IWorkerRepository
    inbox: IInboxRepository
    outbox: IOutboxRepository
```

### Notes

- All write-side handlers (`container_moved_handler`, `worker_handlers`, `alert_handlers`, `driver_handlers`) depend only on `IUnitOfWork` — never on SQLAlchemy sessions directly.
- SQLAlchemy implementations stay in `infrastructure/persistence/` adapters.
- Mongo and Redis projectors should be separate consumers of outbox-derived events, but currently the outbox worker projects directly (no Kafka publish step).
- `IEventConsumer`, `IEventPublisher`, `IMetricEventRepository`, `ICacheService` remain unimplemented.

---

## 4) Fallback + DLQ strategy (polyglot) — TODO

> **Status: Not implemented.** The strategy below remains the target design.

### 4.1 Failure classes

1. Transient infrastructure failures.
- Mongo timeout, Redis timeout, Kafka temporary network issues.
- Action: retry with exponential backoff and jitter.

2. Permanent contract/domain failures.
- Invalid schema, unknown event_version, impossible domain transition.
- Action: send to DLQ immediately with reason code.

3. Concurrency conflicts.
- Optimistic version conflict or lock timeout.
- Action: bounded retries; if exhausted, DLQ with conflict diagnostics.

### 4.2 DLQ topic policy

For each command/projection topic create:
- `<topic>.retry.1`
- `<topic>.retry.2`
- `<topic>.retry.3`
- `<topic>.DLQ`

DLQ message payload includes:
- original event envelope
- error_class
- error_message
- stacktrace hash
- service
- attempt_count
- first_seen_at / last_seen_at

### 4.3 Polyglot fallback behavior

- Postgres write fails: do not commit inbox as processed, do not commit Kafka offset.
- Mongo projector fails: keep replayable offset checkpoint pending; command side remains correct.
- Redis projector fails: frontend fallback to Postgres read endpoint with strict rate-limiting and cache-miss telemetry.
- If both Mongo and Redis projectors are degraded: continue command processing, raise degraded mode alert, and replay projections once recovered.

### 4.4 Replay and repair

- Provide replay job by topic+partition+offset range.
- Rebuild Redis materialized views from Mongo/Postgres snapshots + outbox stream.
- Keep repair scripts deterministic and idempotent.

### 4.5 Current state of error handling

| Component | Retry | DLQ | Observability |
|-----------|-------|-----|---------------|
| `ContainerMovedHandler` | No retry — marks inbox FAILED | No DLQ | Logger only |
| `simple_outbox_worker` | Exp. backoff + jitter (5 retries) | DEAD_LETTER after max retries | Logger only |
| `KafkaDecisionConsumer` | Catch-all with `sleep(1)` | No DLQ | Logger only |
| `_store_infraction_decision` | No retry | No DLQ | Logger only |
| Legacy `decision_queries` | No retry — Mongo failure returns `None` + warning (§10) | No DLQ | Logger only |

---

## 5) Domain corrections required (appointments, shifts, metrics, cleanup)

1. **Shifts for demo mode.** — TODO
- Introduce a deterministic “virtual shift calendar” seed for demos.
- Decouple shift assignment from real-time wall-clock during demos with scenario clock.
- Current state: `data_init_demo.py` and `data_init_realistic.py` exist for seeding, but no scenario clock.

2. **Company/driver/appointment consistency.** — PARTIAL
- Aggregate boundaries partially defined:
  - Appointment aggregate owns state transitions (via `ContainerMovedHandler`).
  - Driver and Company are reference aggregates (read-only in driver flows).
- **Still mixed:** Visit completion trigger auto-cascades appointment status outside app layer control.

3. **Metrics for logistics manager.** — PARTIAL
- `statistics_queries.py` computes from MongoDB aggregation + Redis counters.
- Missing: `queue_time`, `gate_cycle_time`, `unloading_time` computed from event timeline.
- KPIs served from MongoDB `statistics_hourly` collection, not from Redis materialized views.
- Dashboard summary has no caching layer.

4. **Trigger/index hardening.** — PARTIAL
- 9 SQL triggers exist in `scripts/triggers.sql`, 26 indexes in `scripts/indexes.sql`.
- ~~Remove duplicated `arrival_id` ORM listener~~ — **DONE** (2026-03-20). Only SQL sequence trigger remains.
- **Still needed:** Add partial indexes for hot query paths (`status IN ('in_transit','delayed')`).
- Existing partial index coverage is unknown — needs audit against `indexes.sql`.

5. **Endpoint discoverability.** — TODO
- FastAPI auto-generates OpenAPI but no per-persona contract splitting.
- No typed API SDK generation for Web or Mobile.

6. **Repository cleanup.** — DONE
- Single Data Module location under `V_APP/Data_Module/`. No duplicate module roots.

---

## 6) Phased rollout — status

### Phase 0 — Event envelope + Inbox/Outbox + UoW — DONE

| Deliverable | Status | Evidence |
|-------------|--------|----------|
| `EventEnvelope` v1 dataclass | DONE | `domain/events.py` — frozen dataclass, 11 fields |
| `ConsumeContext` dataclass | DONE | `domain/events.py` |
| `inbox_events` table | DONE | `infrastructure/persistence/inbox_outbox_models.py` — UNIQUE(event_id), state machine, retry_count, payload JSONB |
| `outbox_events` table | DONE | `infrastructure/persistence/inbox_outbox_models.py` — UNIQUE(event_id), topic, partition_key, payload JSONB |
| `IInboxRepository` + impl | DONE | `domain/interfaces.py`, `inbox_repository.py` — dedup via IntegrityError, SHA256 payload hash |
| `IOutboxRepository` + impl | DONE | `domain/interfaces.py`, `outbox_repository.py` — append/fetch_batch/mark_published |
| `IUnitOfWork` + impl | DONE | `domain/interfaces.py`, `unit_of_work.py` — 7 repositories, context manager |
| Domain repository interfaces | DONE | `IAppointmentStateRepository`, `IAppointmentRepository`, `IAlertRepository`, `IDriverRepository`, `IWorkerRepository` |
| All 7 SQLAlchemy repo impls | DONE | `infrastructure/persistence/` — container, appointment, alert, driver, worker repos |
| No external API changes | DONE | All routes preserved, patterns added underneath |

### Phase 1 — ContainerMoved command flow — PARTIAL

| Deliverable | Status | Evidence |
|-------------|--------|----------|
| `ContainerMovedHandler` (Steps 3-6) | DONE | `application/use_cases/container_moved_handler.py` — exemplary implementation |
| Strangler Fig routing in consumer | DONE | `kafka_decision_consumer.py:_dispatch_container_moved()` — builds envelope, routes through handler |
| Kafka offset commit after success | DONE | `kafka_decision_consumer.py:273-276` |
| Outbox relay worker | **PARTIAL** | `scripts/simple_outbox_worker.py` projects directly (no Kafka publish), no checkpoint. **Retry+backoff+DEAD_LETTER+graceful shutdown DONE (2026-03-20).** |
| Migrate `decision_queries` PG writes to UoW | **DONE** (2026-03-20) | `process_incoming_decision` delegates PG writes to `cmd_process_decision` + `cmd_update_visit_state` via UoW+Outbox. Mongo/Redis stay as async projections. |
| Migrate `arrival_queries` writes to UoW | **DONE** (2026-03-20) | 5 route write endpoints migrated to `appointment_commands.py` command handlers via UoW+Outbox. Legacy functions preserved for backward compat. |
| `IVisitRepository` + `SqlAlchemyVisitRepository` | **DONE** (2026-03-20) | `domain/interfaces.py`, `infrastructure/persistence/visit_repository.py` — registered in UoW as 8th repository. |
| Migrate infraction path to Inbox | **PARTIAL** | `update_appointment_after_infraction` uses `cmd_flag_highway_infraction` via UoW. `_store_infraction_decision()` still does direct Mongo writes (no inbox dedup). |
| Worker/Alert handlers via UoW+Outbox | DONE | `worker_handlers.py`, `alert_handlers.py` — UoW+Outbox+write-through pattern |
| Containerize outbox worker | **DONE** (2026-03-20) | `docker-compose.yml` — `outbox-worker` service added |

### Phase 2 — Redis read projections — PARTIAL

| Deliverable | Status | Evidence |
|-------------|--------|----------|
| Redis key namespaces defined | DONE | `infrastructure/persistence/redis.py` — 7 namespaces with TTLs |
| Appointment hot cache (single entity) | DONE | `cache_appointment()` / `get_cached_appointment()` — 30min TTL |
| License plate lookup cache | DONE | `cache_license_plate_appointments()` — 10min TTL |
| Real-time counters per gate | DONE | `increment_counter()` / `get_counter()` — 2h TTL |
| Arrivals route CQRS (Redis → PG fallback) | DONE | `routes/arrivals.py:get_arrival()` reads Redis first |
| Arrivals list CQRS (Mongo → PG fallback) | DONE | `routes/arrivals.py:list_arrivals()` reads MongoDB first |
| Driver routes Redis projection | **TODO** | `routes/driver.py` reads directly from PostgreSQL |
| Alerts routes Redis projection | **TODO** | `routes/alerts.py` reads directly from PostgreSQL |
| Worker routes Redis projection | **PARTIAL** | `routes/worker.py` — 3 shift endpoints now use PG fallback (Guardrail 5). No Redis projection yet. |
| Redis key constants file (`redis_schema.py`) | **TODO** | Keys are function-generated, no centralized constant registry |
| Redis AOF persistence + volume | **TODO** | `docker-compose.yml` Redis has no volume, no `--appendonly yes` |
| Per-persona materialized views | **TODO** | No dedicated `gate:{gate_id}:arrivals:list`, `manager:dashboard:*`, `driver:*:active_appointment` keys |

### Phase 3 — Mongo timeline + KPI aggregations — PARTIAL

| Deliverable | Status | Evidence |
|-------------|--------|----------|
| MongoDB collections defined | DONE | `infrastructure/persistence/mongo.py` — 12+ collections with indexes |
| CQRS read model collections | DONE | `appointments_read`, `alerts_read`, `drivers_read`, `workers_read` |
| Outbox worker → Mongo projection | DONE | `simple_outbox_worker.py:project_to_mongo()` — upsert by event_id |
| Appointment read model projection | DONE | Outbox worker projects full snapshot + visit data + detail to `appointments_read` |
| Write-through for workers/alerts | DONE | `worker_handlers.py`, `alert_handlers.py` — best-effort async Mongo write after UoW commit |
| `statistics_hourly` aggregation | PARTIAL | `statistics_queries.py:compute_hourly_statistics()` exists, called ad-hoc, not event-driven |
| Event-derived timeline projector | **TODO** | `decision_events` collection exists but populated by legacy path, not by outbox projector |
| KPI materialized views in Redis | **TODO** | Dashboard summary queries MongoDB directly, no Redis cache layer |
| `projection_checkpoint` table | **TODO** | No checkpoint mechanism; outbox worker re-scans PENDING on restart |
| Notification projection via Outbox | **TODO** | `notification_queries.py` writes to MongoDB directly, not via outbox |

### Phase 4 — DLQ + replay + hardening — TODO

| Deliverable | Status |
|-------------|--------|
| DLQ topic policy per topic | **TODO** |
| Retry topics (`<topic>.retry.1/2/3`) | **TODO** |
| Exponential backoff in outbox worker | **DONE** (2026-03-20) |
| `OutboxEvent` model: add `retry_count`, `next_retry_at` | **DONE** (2026-03-20) |
| Replay job by topic+partition+offset range | **TODO** |
| Redis materialized view rebuild from Postgres/Mongo | **TODO** |
| Chaos testing | **TODO** |
| Load testing | **TODO** |
| SLO dashboards (Prometheus/Grafana) | **TODO** |
| Inbox dedup hit rate metric | **TODO** |
| Outbox lag metric | **TODO** |
| Projection lag metric | **TODO** |
| Redis hit ratio metric | **TODO** |
| P95 end-to-end latency metric | **TODO** |

---

## 7) Known guardrail violations (as of 2026-03-19)

| # | Guardrail | Status | Violations |
|---|-----------|--------|------------|
| 1 | Idempotency at Inbox boundary | PARTIAL | `decision_queries.py` now uses event-id dedup when `event_id` provided; legacy time-window fallback with warning. Infraction path has no dedup. ContainerMoved uses Inbox UNIQUE(event_id). |
| 2 | No multi-DB writes in command tx | PARTIAL | `decision_queries.py` writes PG via UoW then Mongo+Redis synchronously (protected by try/except — see §10). `notifications.py` writes Mongo directly. |
| 3 | Transactional Outbox for all side effects | PARTIAL | `ContainerMovedHandler`, `worker_handlers`, `alert_handlers` use Outbox. Legacy `decision_queries` and infraction path publish directly. |
| 4 | Inbox state machine for consumer reliability | PARTIAL | Inbox model has full state machine. Only `ContainerMovedHandler` uses it. |
| 5 | CQRS strict split | PARTIAL | `arrivals.py` has Redis/Mongo-first reads. `driver.py`, `alerts.py`, `worker.py` read from PG directly. |
| 6 | Repository + UoW only in app layer | PARTIAL | `container_moved_handler`, `worker_handlers`, `alert_handlers`, `driver_handlers` use UoW. `decision_queries` uses raw `SessionLocal()`. |
| 7 | Projection workers replayable + deterministic | **TODO** | No `projection_checkpoint`. Outbox worker is idempotent (upsert) but not replayable from checkpoint. |
| 8 | DLQ policy required per topic | PARTIAL | Outbox worker has DEAD_LETTER after MAX_RETRIES + permanent error classification. No Kafka DLQ topics yet. |
| 9 | Event contracts versioned + backward-compatible | PARTIAL | `EventEnvelope` has `event_version` field. No consumer version negotiation or rejection logic. |
| 10 | Operational SLOs measured | **TODO** | Prometheus `/metrics` endpoint exists but no inbox/outbox/projection-specific metrics. |
| 11 | Frontend contract compatibility | PARTIAL | Routes preserved. ~~Statistics gaps for manager~~ fixed (2026-03-20). Driver auth is placeholder. ~~Shift endpoints still STUB~~ — implemented with PG fallback (2026-03-20). |

---

## 8) Acceptance criteria

| Criterion | Status |
|-----------|--------|
| Duplicate Kafka event replay changes no business state | PARTIAL — only for ContainerMoved via Inbox |
| No command path writes directly to Mongo/Redis | **VIOLATED** — `decision_queries.py` (protected by try/except, §10), `notification_queries.py`. Full async migration deferred post-demo. |
| Kafka offset commits only after inbox processed + Postgres commit | PARTIAL — only for ContainerMoved path |
| Frontend dashboards read Redis materialized views with >=90% hit ratio | **NOT MET** — most routes read PG directly |
| DLQ pipeline active with reason codes and replay capability | **NOT MET** |
| P95 end-to-end ContainerMoved → UI update below agreed SLO | **NOT MEASURABLE** — no metrics emitted |

---

## 9) Recommended next iterations (priority order — demo override active)

### Demo deadline iterations (mandatory before Tuesday)

| Priority | Task | Phase | Risk addressed | Status |
|----------|------|-------|----------------|--------|
| ~~P0~~ | ~~Fix `arrival_id` race — remove ORM listener, keep SQL sequence trigger~~ | A1 | ~~Risk #6~~ | **DONE** (2026-03-20) |
| ~~P1~~ | ~~Optimistic concurrency on Appointment — add `version` column, implement WHERE check~~ | A4 | ~~Risk #8~~ | **DONE** (2026-03-20) |
| ~~S1~~ | ~~Fix 4 BROKEN manager dashboard endpoints (`/statistics/summary`, `/by-company`, `/volume`, `/alerts`)~~ | Step 1 | ~~Risk #9 — frontend drift~~ | **DONE** (2026-03-20) |
| ~~S1b~~ | ~~Verify remaining STUB endpoints — 3 shift endpoints implemented with PG fallback~~ | Step 1 | ~~Risk #9~~ | **DONE** (2026-03-20) |
| ~~P2~~ | ~~Migrate demo-critical writes to UoW+Inbox+Outbox (A2)~~ | A2 | ~~Risks #1, #2, #3~~ | **DONE** (2026-03-20) |
| **P3** | Fix event dedup to use event_id (A3) | A3 | Risk #4 | DONE (2026-03-20) |
| **P4** | Outbox worker with retry + exponential backoff (B1) | B1 | Risk #1 — lost events | DONE (2026-03-20) |

### Deferred to after Tuesday

| Priority | Task | Phase | Risk addressed | Effort |
|----------|------|-------|----------------|--------|
| P5 | Add `projection_checkpoint` table + use in outbox worker | B2 | Risk #7 | 3 files, 1 migration |
| P6 | Redis AOF + volume in docker-compose | C1 | State loss on restart | 1 file |
| P7 | Redis key constants (`redis_schema.py`) | C2 | Maintainability | 2+ files |
| P8 | DLQ policy implementation | Phase 4 | Risk #8 | New files |
| P9 | Prometheus metrics for inbox/outbox/projection | Phase 4 | Risk #10 | Multi-file |

---

## 10) ADR — Migração de `persist_decision_event` para Outbox assíncrono

> **Date:** 2026-03-20
> **Status:** DEFERRED (pós-demo) — interim fix deployed (task #4)
> **Context:** Avaliação de migrar a escrita síncrona de decision events no MongoDB para o pipeline assíncrono via Transactional Outbox.

### 10.1 Estado atual (híbrido)

```
HTTP POST /decisions/process
  ├─ cmd_process_decision()     ← PG + Outbox (atómico, UoW) ✓
  ├─ persist_decision_event()   ← MongoDB SÍNCRONO (bloqueante) ✗
  ├─ cache_decision_result()    ← Redis SÍNCRONO
  ├─ cache_appointment()        ← Redis SÍNCRONO
  ├─ create_notification()      ← MongoDB SÍNCRONO
  └─ return result

[Outbox Worker — background]
  ├─ project_to_mongo()   ← upsert do envelope (genérico)
  └─ project_to_redis()   ← só AppointmentStateChanged (decisões NÃO tratadas)
```

**Problema:** Se ambas as escritas MongoDB falharem em `persist_decision_event`, o request devolvia 500 mesmo com o PG já committed. Isto viola Guardrail 2 (no multi-DB writes) e Guardrail 5 (strict CQRS split).

**Fix interim (task #4, 2026-03-20):** `persist_decision_event` já não faz `raise` em caso de double-failure MongoDB — retorna `None` e o request devolve 200 com `"warning": "mongo_write_failed"`. Logs ERROR mantidos para observabilidade.

### 10.2 Abordagem proposta (totalmente assíncrona)

```
HTTP POST /decisions/process
  ├─ cmd_process_decision()  ← PG + Outbox (atómico, já existente)
  └─ return result           ← resposta imediata

[Outbox Worker — background]
  ├─ project_to_mongo()      ← documento completo de decisão (novo handler)
  ├─ project_to_redis()      ← cache de decisão + appointment (novo handler)
  └─ create_notification()   ← notificações (novo handler)
```

### 10.3 Análise comparativa

#### Vantagens da abordagem assíncrona

| Vantagem | Impacto |
|----------|---------|
| **Resiliência** | MongoDB indisponível durante pico de tráfego não afeta API. Camiões continuam a ser processados. Kafka/outbox guarda eventos e MongoDB é atualizado na recuperação — elimina falhas em cascata. |
| **Latência** | Latência HTTP fica limitada a PG write (~5-15ms). Remove 3-4 round-trips síncronos (2x Mongo + 3x Redis) do ciclo de resposta. |
| **Consistência eventual garantida** | Substitui tentativa falhada de "consistência forte" impossível entre PG/Mongo/Redis por consistência eventual matematicamente garantida via outbox+retry+DLQ. |
| **Idempotência nativa** | Replay do outbox produz estado idêntico (Guardrail 7) — `event_id` como chave de upsert. |
| **Auditoria completa** | Pipeline de projeção com retry_count, last_error, DEAD_LETTER — observabilidade total (Guardrail 10). |
| **Conformidade com Guardrails** | Resolve violações dos Guardrails 2, 3 e 5 em `decision_queries.py`. |

#### Desvantagens e riscos

| Desvantagem | Severidade | Mitigação |
|-------------|-----------|-----------|
| **Payload do outbox event incompleto** | Alta | `DecisionProcessed` atual só tem `appointment_id, status, alerts_created` — falta detalhe completo (agent detections, timing, operator decision). Requer expansão do payload ou novo event type `DecisionEventRecorded`. |
| **Delay na visualização (2-5s)** | Média | Dashboard MongoDB/Redis mostra dados com atraso do poll interval (2s). Para demos pode parecer bug. Mitigação: reduzir poll interval ou trigger manual de projeção. |
| **Scope de alteração grande** | Alta | 5 alterações interligadas: (1) expandir payload do outbox event, (2) handler `DecisionProcessed` no `project_to_redis`, (3) mapear payload → documento Mongo completo, (4) mover notificações para async, (5) tratar path de infração Kafka. |
| **Unmatched trucks sem outbox** | Média | Quando `appointment_id is None`, não há `cmd_process_decision()` → não há outbox event. Requer command dedicado ou escrita direta do outbox row para estes casos. |
| **Validação end-to-end** | Média | Testes de source-inspection passam, mas comportamento end-to-end muda. Requer validação de que o frontend não assume escrita MongoDB imediata. |

### 10.4 Alterações necessárias para migração completa

| # | Alteração | Ficheiro(s) | Esforço |
|---|-----------|-------------|---------|
| 1 | Criar event type `DecisionEventRecorded` com payload completo (agent detections, timing, operator decision) ou expandir `DecisionProcessed` | `application/use_cases/appointment_commands.py`, `domain/events.py` | Médio |
| 2 | Adicionar handler para `DecisionEventRecorded` / `DecisionProcessed` no `project_to_mongo()` — mapear payload → documento `decision_events_collection` | `scripts/simple_outbox_worker.py` | Médio |
| 3 | Adicionar handler para decisões no `project_to_redis()` — cache de resultado de decisão | `scripts/simple_outbox_worker.py` | Baixo |
| 4 | Criar command para unmatched trucks (`appointment_id is None`) que escreve outbox event sem mutação de appointment | `application/use_cases/appointment_commands.py` | Médio |
| 5 | Mover `create_notification()` para projeção assíncrona via outbox | `application/queries/notification_queries.py`, `scripts/simple_outbox_worker.py` | Médio |
| 6 | Migrar `persist_infraction_event_from_kafka()` para outbox-based | `application/queries/decision_queries.py`, `infrastructure/messaging/kafka_decision_consumer.py` | Médio |
| 7 | Remover chamadas síncronas de Mongo/Redis em `process_incoming_decision()` | `application/queries/decision_queries.py` | Baixo |
| 8 | Testes end-to-end do novo pipeline | `tests/` | Alto |

### 10.5 Decisão

**Pré-demo (2026-03-24):** Manter o fix interim (task #4). O `try/except` + `return None` + `warning` é defensivo, testado (101 tests pass), e não altera comportamento visível.

**Pós-demo (prioridade P5-P6):** Executar a migração completa para outbox-driven. O scope real envolve ~8 alterações interdependentes — demasiado risco para a véspera da demo.

### 10.6 Referências

- **Guardrail 2:** Never perform multi-database writes in the same command transaction.
- **Guardrail 3:** Use Transactional Outbox for all side effects.
- **Guardrail 5:** CQRS strict split — write to PG, read from projections.
- **Fix interim:** `decision_queries.py` L194 — `return None` em vez de `raise`, callers adicionam `warning: "mongo_write_failed"`.
- **Callers afetados:** L265 (unmatched trucks), L294 (main path), L337 (infraction from Kafka).