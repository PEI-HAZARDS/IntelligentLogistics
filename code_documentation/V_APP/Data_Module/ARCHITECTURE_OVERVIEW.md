# ARCHITECTURE OVERVIEW — Data Module

> Polyglot persistence layer implementing CQRS, Transactional Outbox, and Idempotent Inbox for the IntelligentLogistics V_APP.

---

## Why Three Stores

The Data Module uses three databases with distinct responsibilities, chosen to match each store's strengths to the data's access pattern and consistency requirements.

```
┌──────────────────────────────────────────────────────────────────┐
│  WRITE PATH (commands)                                           │
│                                                                  │
│  API / Kafka ──► SqlAlchemyUnitOfWork ──► PostgreSQL (primary)  │
│                          │                    + outbox_events    │
│                          │                    + inbox_events     │
│                          ▼                                       │
│                  simple_outbox_worker ──► MongoDB (projections)  │
│                                     └──► Redis   (cache/TTL)    │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  READ PATH (queries)                                             │
│                                                                  │
│  GET /arrivals/{id}  ──► Redis hot cache                        │
│                              │ miss                             │
│                              ▼                                   │
│                         PostgreSQL                               │
│                              └──► warm Redis for next read      │
│                                                                  │
│  GET /decisions/*    ──► MongoDB (event log)                    │
│  GET /statistics/*   ──► MongoDB (rollups) + Redis (counters)   │
└──────────────────────────────────────────────────────────────────┘
```

### PostgreSQL — ACID source of truth

Owns every entity that participates in atomic transactions: `appointment`, `visit`, `driver`, `worker`, `truck`, `company`, `booking`, `cargo`, `gate`, `shift`, `alert`, `inbox_events`, `outbox_events`. Any mutation that must be durable and consistent goes through `SqlAlchemyUnitOfWork`, which commits exactly one PG transaction per command.

### MongoDB — event log and CQRS read models

Owns variable-shape, append-only records: `agent_detections`, `decision_events`, `notifications`, `statistics_hourly`, `statistics_daily`, `operator_performance`, `company_metrics`, `appointments_read`, `alerts_read`.

**Write paths (two, both valid):**
- `simple_outbox_worker` — projects domain events from `outbox_events` to event-log collections (`agent_detections`, `decision_events`, `notifications`). The sole write path for command-driven mutations.
- `scripts/statistics_aggregator.py` — scheduled background process that writes pre-computed rollups directly to `statistics_hourly`, `statistics_daily`, `operator_performance`, `company_metrics`. This is not a command handler and is exempt from the outbox guardrail (BR-29).

Direct-write violations DW-01 through DW-10 are fully resolved: deprecated functions deleted, `notification_queries.py` removed. Queries against these collections never touch PG.

### Redis — cache, counters, TTL-bound state

Owns derived or ephemeral state that can be rebuilt from PG/Mongo: appointment hot-cache (1800s), license-plate lookup (600s), decision cache (3600s), dedup keys (300s), real-time counters (7200s), rate-limit windows (60s), operator sessions (3600s), pending-review correlation (1800s).

---

## Boundary Rules (Architectural Guardrails)

These rules are enforced in `IntelligentLogistics/CLAUDE.md` and the refactor plan.

| # | Rule | Enforcement point |
|---|------|------------------|
| 1 | No distributed transactions (2PC). Use Outbox instead. | `SqlAlchemyUnitOfWork` |
| 2 | New command handlers must use `SqlAlchemyUnitOfWork`. Never write directly to Mongo/Redis from write-side. | Code review + `KNOWN_DEVIATIONS.md` |
| 3 | Kafka offset committed only after PG UoW commit. | `kafka_decision_consumer._dispatch_container_moved` |
| 4 | Backward-compatible API changes only. | Frontend service contracts in `IntelligentLogistics_APP` |
| 5 | All domain events use `EventEnvelope` (11 required fields, UUIDv7 `event_id`). | `domain/events.py::new_event_id()` — pure-stdlib UUIDv7 generator; all handlers migrated in Phase 8 |
| 6 | Optimistic concurrency on `Appointment`: `WHERE version = <read_version>`. Never bypass. | `appointment_state_repository.py` |

---

## CQRS Split

**Write side** — `application/use_cases/`: command handlers (`cmd_*` functions, `ContainerMovedHandler`). These call `IUnitOfWork` repositories only. No direct SQL, no Mongo, no Redis.

**Read side** — `application/queries/`: query functions (`get_*`, `count_*`). These receive an injected SQLAlchemy `Session` (for PG reads), call Mongo collections directly (event log reads), or call Redis helpers (cache reads). They do not commit.

---

## UoW + Outbox + Inbox Pattern

```
1. Kafka consumer receives ContainerMoved
2. ContainerMovedHandler opens SqlAlchemyUnitOfWork
3. inbox.try_insert_received(event, ctx) — UNIQUE(event_id) gate
   └── duplicate? → ACK + return (idempotent)
4. appointment_state.get_for_update(id) — SELECT FOR UPDATE
5. appointment_state.save_state_transition(id, new_state, meta)
6. outbox.append(AppointmentStateChanged, topic, key)
7. inbox.mark_processed(event_id)
8. uow.commit() — single PG transaction covers steps 3–7
9. consumer.commit() — Kafka offset committed AFTER PG commit
10. simple_outbox_worker polls outbox_events, publishes to Kafka/Mongo/Redis
```

---

## External Boundaries

```
Kafka (KRaft :9092)
  ├── INBOUND  agent-decisions → KafkaDecisionConsumer
  │            operator-decisions → KafkaDecisionConsumer
  │            ContainerMoved → ContainerMovedHandler
  └── OUTBOUND appointment.state.changed
               appointment.visit.changed
               worker.changed

HTTP (:8080)
  ├── /arrivals/*   → routes/arrivals.py
  ├── /drivers/*    → routes/driver.py
  ├── /workers/*    → routes/worker.py
  ├── /alerts/*     → routes/alerts.py
  ├── /decisions/*  → routes/decisions.py
  ├── /statistics/* → routes/statistics.py
  ├── /events/*     → routes/events.py
  └── /notifications/* → routes/notifications.py

PostgreSQL (:5432) — primary store
MongoDB    (:27017) — event log + read models
Redis      (:6379)  — cache + counters
MinIO      (:9000)  — image blob storage (detection crops)
Tempo      (:4317)  — OTLP gRPC trace ingest (observability VM, optional)
```

---

## Observability

### Distributed Tracing (OpenTelemetry)

`main.py` configures `TracerProvider` + `BatchSpanProcessor` + `OTLPSpanExporter` at module load time. `FastAPIInstrumentor` adds a span per HTTP request automatically.

**Startup probe** — `_probe_otlp_endpoint(endpoint, timeout=2s)` does a TCP connect to the OTLP endpoint before attaching the `BatchSpanProcessor`. Logs `INFO` if reachable, `WARNING` if not. The processor is attached regardless — `BatchSpanProcessor` reconnects automatically when Tempo comes back online without a restart.

**Rate-limit filter** — `_OtelRateLimitFilter(interval_s=300)` is added to both OTel loggers (`opentelemetry.exporter.otlp.proto.grpc.exporter` and `opentelemetry.sdk.trace.export`). When Tempo is unreachable the processor retries every 3 s; the filter suppresses duplicate error lines to at most one per 5 minutes, keeping logs readable without hiding real failures.

**Health endpoint** — `GET /api/v1/health` includes a `tracing` object:
```json
{
  "tracing": {
    "enabled": true,
    "endpoint": "http://10.255.32.132:4317",
    "reachable": true
  }
}
```

**Configuration** — controlled by two env vars:

| Var | Default | Effect |
|-----|---------|--------|
| `OTEL_ENABLED` | `true` | Set to `false` to disable tracing entirely |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://tempo:4317` | OTLP gRPC endpoint (in-cluster or external) |

### Observability Stack Deployment

The full stack (Prometheus, Grafana, Loki, Tempo, Alertmanager, Promtail, node-exporter) lives in `src/devops/observability/`. It runs on the Jenkins VM (`10.255.32.132`) via remote Docker context. Deploy command:

```bash
# Copy config files to VM (only needed when config changes)
scp -r src/devops/observability pei_user@10.255.32.132:~/

# Start / update stack
docker --context jenkins-vm compose \
  -f src/devops/observability/docker-compose.yml \
  --project-directory /home/pei_user/observability \
  --env-file src/devops/observability/.env \
  up -d
```

**Known config notes:**
- `tempo-config.yml` does not include a `compactor` block — removed in Tempo latest (field no longer valid at top-level).
- `alertmanager/entrypoint.sh` falls back to a null receiver when `ALERT_EMAIL_TO` is unset, so the container starts cleanly without SMTP credentials.

---

## Related Docs

- [`DATA_FLOW.md`](DATA_FLOW.md)
- [`SCHEMA_REFERENCE.md`](SCHEMA_REFERENCE.md)
- [`KNOWN_DEVIATIONS.md`](KNOWN_DEVIATIONS.md)
- [`TEST_COVERAGE_MAP.md`](TEST_COVERAGE_MAP.md)
- [`infrastructure/persistence/unit_of_work.md`](infrastructure/persistence/unit_of_work.md)
- [`infrastructure/messaging/kafka_decision_consumer.md`](infrastructure/messaging/kafka_decision_consumer.md)
