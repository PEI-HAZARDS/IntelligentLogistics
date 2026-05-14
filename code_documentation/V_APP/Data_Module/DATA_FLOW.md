# DATA FLOW — Data Module

> Sequence diagrams and prose for each major data path through the system.

---

## 1. Write Path — Command via HTTP

```
Client
  │  POST /arrivals/{id}/decision
  ▼
routes/arrivals.py:process_decision
  │  cmd_process_decision(_uow_factory, appointment_id, payload)
  ▼
appointment_commands.cmd_process_decision
  │  with SqlAlchemyUnitOfWork() as uow:
  │    aggregate = uow.appointment_state.get_for_update(id)   ← SELECT FOR UPDATE
  │    uow.appointment_state.save_state_transition(id, status, meta)
  │    uow.alerts.add(...)   [if alerts in payload]
  │    uow.outbox.append(DecisionProcessed, topic, key)
  │    uow.commit()           ← single PG transaction
  ▼
simple_outbox_worker (background)
  │  polls outbox_events WHERE status='PENDING'
  │  publishes DecisionProcessed to Kafka
  │  updates decision_events in MongoDB
  │  invalidates Redis appointment cache
  ▼
Redis / MongoDB updated (eventual consistency)
```

---

## 2. Write Path — Kafka ContainerMoved (reference implementation)

```
Decision Engine
  │  publishes ContainerMoved to Kafka topic
  ▼
KafkaDecisionConsumer._consume_loop
  │  final_decision = correlator.process_agent_decision(truck_id, payload)
  │  if final_decision:          ← None for MANUAL_REVIEW
  │    await _dispatch_container_moved(final_decision)
  ▼
_dispatch_container_moved
  │  handler = ContainerMovedHandler(uow_factory)
  │  handler.handle(event, ctx)
  │    ┌── inbox.try_insert_received(event, ctx)      ← UNIQUE(event_id) gate
  │    ├── appointment_state.get_for_update(id)        ← SELECT FOR UPDATE
  │    ├── appointment_state.save_state_transition(id, new_state, meta)
  │    ├── visits.create(...)    [if new_state == in_process]
  │    ├── outbox.append(AppointmentStateChanged)
  │    ├── inbox.mark_processed(event_id)
  │    └── uow.commit()          ← PG commit; raises on failure
  │  consumer.commit()            ← Kafka offset ONLY after PG commit
```

**Key invariant**: if `uow.commit()` raises, the exception propagates out of `handler.handle()`, the Kafka offset is never committed, and the message is redelivered.

---

## 3. Manual Review Flow (MANUAL_REVIEW → operator → resolution)

```
Agent Decision (MANUAL_REVIEW)
  │
  ▼
KafkaDecisionConsumer._handle_manual_review
  │  cmd_store_pending_review(uow_factory, event_id, truck_id, gate_id, plate, payload)
  │    ┌── pending_reviews PG row (status=PENDING)        ← durable
  │    └── outbox.append(PendingReviewCreated)
  │    uow.commit()
  ▼
simple_outbox_worker projects PendingReviewCreated
  │  redis.setex("pending_review:{event_id}", 1800s, payload)  ← fast-path cache
  ▼
[operator sees MANUAL_REVIEW alert in dashboard]
  │
Operator Decision (APPROVED / REJECTED)
  │  POST /decisions/{event_id}/resolve
  ▼
cmd_resolve_pending_review(uow_factory, event_id, resolution, operator_num_worker)
  │  pending_review = SELECT … FOR UPDATE WHERE event_id = ?
  │  pending_review.status = APPROVED|REJECTED
  │  pending_review.resolved_at = now()
  │  outbox.append(PendingReviewResolved)
  │  uow.commit()
  ▼
simple_outbox_worker projects PendingReviewResolved
  │  redis.delete("pending_review:{event_id}")
  │  merge final decision → _dispatch_container_moved(final)
  └── (same flow as §2 above)
```

**Resilience**: Redis flush does not lose state — `pending_reviews` PG table is the source of truth. The Redis key is a TTL-bounded projection cache rebuilt on demand.

---

## 4. Read Path — GET /arrivals/{id} (two-tier fallback)

```
Client
  │  GET /arrivals/{appointment_id}
  ▼
routes/arrivals.get_arrival
  │  cached = get_cached_appointment(id)  ← Redis "appointment:{id}:details"
  │  if cached: return cached              ← HIT: no PG query
  │
  │  [MISS]
  │  appointment = get_appointment_by_id(db, id)   ← PG query
  │  cache_appointment(id, result)                  ← warm Redis (TTL 1800s)
  │  return result
```

> **BR-29 gap**: The spec requires Redis → Mongo → PG (three-tier). The Mongo tier is not yet implemented. See `KNOWN_DEVIATIONS.md`.

---

## 5. Read Path — GET /statistics/* (Mongo + Redis)

```
GET /statistics/summary (via API Gateway)
  │
  ▼
routes/statistics / manager_statistics_queries
  │  Redis: get_or_cache("stats:gate:{id}:{date}", ttl=30s, fallback=_compute)
  │  fallback → MongoDB: statistics_hourly.find({gate_id, hour_bucket})
  │          → MongoDB: decision_events aggregation
  │          → PostgreSQL: appointment counts
  │  return merged result
```

---

## 6. Outbox Worker Projection Loop

```
simple_outbox_worker (every 2s poll)
  │
  ▼
outbox_repository.fetch_batch(50)      ← batch_size=50 rows WHERE status=PENDING
  │
  for each event:
    │  project_to_mongo(event)         ← decision_events, notifications, appointments_read, alerts_read
    │  project_to_redis(event)         ← cache warm / invalidate / session / pending_review
    │  mark_published(outbox_id)       ← PG UPDATE status=PUBLISHED
    │
    │  on failure:
    │    retry with 2^n backoff ≤ 60s, max 5 retries
    │    mark_publish_failed(outbox_id)
    │    after 5 failures → DEAD_LETTER
    │      _forward_to_dlq(row)        ← confluent_kafka.Producer → Kafka "data.dlq" topic
```

**UoW commit resilience** (Phase 10): `SqlAlchemyUnitOfWork.commit()` retries up to 3× on `OperationalError` / PostgreSQL deadlock, with exponential backoff (0.1s, 0.2s, 0.4s), before propagating the exception.

---

## 7. Inbox State Machine

```
RECEIVED ──► PROCESSING ──► PROCESSED
                │
                └──► FAILED (retryable=True)  → retry consumer
                └──► DEAD_LETTER (retryable=False)
```

Transitions enforced by `SqlAlchemyInboxRepository`. The `UNIQUE(event_id)` constraint on `inbox_events` prevents concurrent double-processing.

---

## Related Docs

- [`ARCHITECTURE_OVERVIEW.md`](ARCHITECTURE_OVERVIEW.md)
- [`SCHEMA_REFERENCE.md`](SCHEMA_REFERENCE.md)
- [`application/use_cases/container_moved_handler.md`](application/use_cases/container_moved_handler.md)
- [`infrastructure/messaging/kafka_decision_consumer.md`](infrastructure/messaging/kafka_decision_consumer.md)
- [`scripts/simple_outbox_worker.md`](scripts/simple_outbox_worker.md)
