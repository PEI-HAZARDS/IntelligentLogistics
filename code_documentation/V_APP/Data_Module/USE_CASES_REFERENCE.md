# Use Cases Reference

> Command handlers — all writes go through `SqlAlchemyUnitOfWork` with Outbox appending (Guardrail 3). No direct MongoDB or Redis writes inside UoW.

**Location:** `src/V_APP/Data_Module/application/use_cases/`

---

## `alert_handlers.py`

Write-side command handlers for the `Alert` aggregate. Hosts ADR/Kemler reference dictionaries (`ADR_CODES`, `KEMLER_CODES`) consumed by `routes/alerts.py`.

```
create_alert / create_hazmat_alert / create_alerts_for_appointment
    ├─ uow.alerts.add()       → INSERT INTO alerts (PostgreSQL)
    ├─ _append_outbox()       → INSERT INTO outbox_events (PostgreSQL)
    └─ uow.commit()           → single ACID commit → outbox_worker → MongoDB + Redis
```

| Function | Returns | Notes |
|----------|---------|-------|
| `create_alert(uow_factory, *, visit_id, alert_type, description, image_url)` | `dict` | Types: generic, safety, problem, operational. Emits `AlertCreated`. |
| `create_hazmat_alert(uow_factory, *, appointment_id, un_code, kemler_code, detected_hazmat)` | `Optional[dict]` | Enriches with ADR/Kemler. Emits `HazmatAlertCreated`. |
| `create_alerts_for_appointment(uow_factory, *, appointment_id, alerts_payload)` | `list[dict]` | Bulk-creates multiple alerts in one UoW transaction. |

**Known Issues:** `_append_outbox` uses `new_event_id()` (UUIDv7) since Phase 8.

---

## `appointment_commands.py`

Five command functions for the appointment write path. Each opens a `IUnitOfWork`, mutates the domain aggregate, appends an outbox event, commits, then invalidates Redis stats keys post-commit.

```
cmd_*(uow_factory, appointment_id, ...)
    └── with uow_factory() as uow:
          ├── uow.appointment_state.get_for_update(id)
          ├── domain mutation
          ├── uow.outbox.append(_outbox_event(...))
          └── uow.commit()
    └── _invalidate_stats_cache(gate_in_id)   [post-commit, Redis, best-effort]
```

| Function | Outbox event | Notes |
|----------|-------------|-------|
| `cmd_update_status(uow_factory, id, new_status, notes)` | `AppointmentStatusUpdated` | — |
| `cmd_process_decision(uow_factory, id, decision_payload)` | `DecisionProcessed` | Creates alert rows from `payload["alerts"]` |
| `cmd_flag_highway_infraction(uow_factory, id)` | `AppointmentHighwayInfractionFlagged` | Sets `highway_infraction=True` |
| `cmd_create_visit(uow_factory, id, shift_gate_id, shift_type, shift_date, entry_time)` | `VisitCreated` | — |
| `cmd_update_visit_state(uow_factory, id, new_state, out_time)` | `VisitStateUpdated` | — |

All commands return `None` when target not found → route returns HTTP 404.

---

## `container_moved_handler.py`

**Reference implementation** of the Inbox → UoW → Outbox pattern. The canonical example for all Kafka-sourced event handlers.

```
KafkaDecisionConsumer._dispatch_container_moved
  └── ContainerMovedHandler.handle(event, ctx)
        ├─ uow.inbox.try_insert_received(event, ctx)   ← duplicate? → ACK + NOOP
        ├─ uow.inbox.mark_processing(event_id)
        ├─ uow.appointment_state.get_for_update(id)    ← not found? → mark_failed + return
        ├─ uow.appointment_state.save_state_transition(id, new_state, metadata)
        │     new_state == "in_process"? → _auto_create_visit(uow, ...)
        ├─ uow.outbox.append(AppointmentStateChanged, topic=...)
        ├─ uow.inbox.mark_processed(event_id)
        ├─ uow.commit()                                ← single PG transaction
        ├─ post-commit: _invalidate_stats_cache()      [best-effort]
        └─ post-commit: _create_accept_notifications() [best-effort, Mongo]
```

| Scenario | Behaviour |
|----------|-----------|
| Duplicate `event_id` | ACK + NOOP |
| Appointment not found | Inbox marked FAILED, UoW committed |
| Exception inside UoW | Auto-rollback, exception propagates |
| Post-commit failure | Caught, logged, no rollback |

**Known Issues:** `_auto_create_visit` uses `datetime.now()` (local time) for shift boundary comparisons — should use UTC. Post-commit Mongo notifications bypass Outbox.

---

## `driver_handlers.py`

Credential validation (login) and appointment claiming via arrival PIN. Both handlers open a `SqlAlchemyUnitOfWork` to read from PostgreSQL — no aggregate mutations, no outbox events.

| Function | Returns | Notes |
|----------|---------|-------|
| `authenticate_driver(uow_factory, *, drivers_license, password)` | `Optional[dict]` | Returns driver dict with company info on success |
| `claim_appointment_by_pin(uow_factory, *, drivers_license, arrival_id, debug_mode)` | `Tuple[Optional[dict], str]` | `(appt_dict, "")` on success; `(None, error_msg)` on failure |

Failure reasons for `claim_appointment_by_pin`: PIN not found, driver not authorised, non-claimable status, earlier appointment not yet completed (skipped in debug mode).

---

## `notification_handlers.py`

Added Phase 5 (DW-01). Replaces the direct `notifications_collection.insert_one(...)` call with a proper UoW + Outbox write path.

### `cmd_send_notification(uow_factory, gate_id, title, message, type, appointment_id, license_plate) -> dict`

Appends a `NotificationCreated` outbox event. The outbox worker then projects to `notifications_collection` in MongoDB.

| Event type | Outbox worker action |
|------------|---------------------|
| `NotificationCreated` | `notifications_collection.insert_one(payload)` |
| `NotificationRead` | `notifications_collection.update_one({$set: {read: true}})` |

---

## `pending_review_handlers.py`

Added Phase 4 (PD-01). Replaces `redis.setex("pending_review:{truck_id}", ...)` direct write that had no PG backing. Every `MANUAL_REVIEW` decision is now written to PG and projected to Redis by the outbox worker.

### `cmd_store_pending_review(uow_factory, event_id, truck_id, gate_id, license_plate, payload) -> dict`

Writes one `PendingReview` row (status=PENDING), appends `PendingReviewCreated` outbox event, commits.

**Called by:** `kafka_decision_consumer._handle_manual_review`

### `cmd_resolve_pending_review(uow_factory, event_id, resolution, resolved_by) -> dict | None`

`SELECT … FOR UPDATE` on `pending_reviews` row; sets `status = APPROVED | REJECTED`. Returns `None` if event_id does not exist.

**Called by:** `routes/decisions.py POST /decisions/{event_id}/resolve`

| Event type | Outbox worker action |
|------------|---------------------|
| `PendingReviewCreated` | `redis.setex("pending_review:{event_id}", 1800s, payload)` |
| `PendingReviewResolved` | `redis.delete("pending_review:{event_id}")` + dispatch merged decision |

---

## `worker_handlers.py`

Write-side handlers for the `Worker` aggregate. Every mutating handler follows Guardrail 3. Password hashes are stripped from outbox payloads before publication.

| Function | Returns | Notes |
|----------|---------|-------|
| `authenticate_worker(uow_factory, *, email, password)` | `Optional[dict]` | Returns worker dict + `token`. `None` on failure. Read-only; no outbox event. |
| `create_worker(uow_factory, *, num_worker, name, email, password, role, access_level, phone)` | `Optional[dict]` | Hashes password; emits `WorkerCreated`. |
| `update_worker_password(uow_factory, *, num_worker, current_password, new_password)` | `tuple[bool, str]` | Emits `WorkerPasswordChanged`. |
| `update_worker_email(uow_factory, *, num_worker, new_email)` | `tuple[bool, str]` | Checks uniqueness; emits `WorkerEmailChanged`. |
| `deactivate_worker(uow_factory, *, num_worker)` | `Optional[dict]` | Sets `active=False`; emits `WorkerDeactivated`. |
| `promote_to_manager(uow_factory, *, num_worker, access_level)` | `Optional[dict]` | Removes Operator, adds Manager role; emits `WorkerPromoted`. |

**Known Issues:** `authenticate_worker` generates an in-process random token (MVP). `_append_outbox` uses `new_event_id()` (UUIDv7) since Phase 8.

---

## Related Docs

- [QUERIES_REFERENCE.md](QUERIES_REFERENCE.md)
- [ROUTES_REFERENCE.md](ROUTES_REFERENCE.md)
- [PERSISTENCE_REFERENCE.md](PERSISTENCE_REFERENCE.md)
- [DATA_FLOW.md](DATA_FLOW.md)
- [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md)
