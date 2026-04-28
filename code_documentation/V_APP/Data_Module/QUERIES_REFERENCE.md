# Queries Reference

> Read-side query functions — PostgreSQL, MongoDB, and Redis. No writes here; all mutations go through command handlers in `USE_CASES_REFERENCE.md`.

**Location:** `src/V_APP/Data_Module/application/queries/`

---

## `alert_queries.py`

Read-only queries for `Alert` records from PostgreSQL.

| Function | Returns | Notes |
|----------|---------|-------|
| `get_alerts(*, skip, limit, alert_type, visit_id)` | `List[Dict]` | Ordered `timestamp DESC` |
| `get_alert_by_id(alert_id)` | `Optional[Dict]` | PK lookup |
| `get_active_alerts(limit)` | `List[Dict]` | Alerts from last 24 hours |
| `get_alerts_count_by_type(*, from_date, to_date)` | `Dict[str, int]` | Defaults to last 24 h |
| `get_alerts_for_visit(visit_id)` | `List[Dict]` | Ordered `timestamp DESC` |

**Known Issues:** MongoDB CQRS read projections not yet implemented; all reads fall back to PostgreSQL.

---

## `arrival_queries.py`

Primary read-side for `Appointment` and `Visit` data. Filtering, pagination, detail expansion, license-plate lookups, and statistical aggregations.

Several legacy write functions remain but are **deprecated** — they bypass UoW + Outbox and do not propagate changes to MongoDB or Redis. Each emits a `DeprecationWarning` pointing to the corresponding `appointment_commands` handler.

| Function | Returns | Notes |
|----------|---------|-------|
| `get_all_appointments(db, ...)` | `List[Appointment]` | Ordered `scheduled_start_time ASC` |
| `count_all_appointments(db, ...)` | `int` | Same filters; used for pagination |
| `get_appointment_by_id(db, id)` | `Optional[Appointment]` | PK lookup |
| `get_appointment_detail(db, id)` | `Optional[Dict]` | Expanded with driver, truck, booking, cargo, gate, terminal, visit |
| `get_appointment_by_arrival_id(db, arrival_id)` | `Optional[Appointment]` | PIN-style lookup |
| `get_appointments_by_license_plate(db, lp, ...)` | `List[Appointment]` | Today or date-filtered |
| `get_appointments_for_decision(db, gate_id)` | `List[Dict]` | `in_transit`/`delayed` today for Decision Engine |
| `get_appointments_count_by_status(db, gate_id, date)` | `Dict[str, int]` | Keys: scheduled, in_transit, in_process, unloading, delayed, canceled, completed, total, infractions |
| `get_next_appointments(db, gate_id, limit, status)` | `List[Appointment]` | `delayed` prioritised over `in_transit` |
| `get_transport_stats_by_company(db, target_date, days)` | `List[Dict]` | Per-company KPIs; joins on `Driver.company_nif` |
| `get_avg_permanence_minutes(db, target_date)` | `float` | Avg port dwell time in minutes |

**Deprecated (use `appointment_commands` instead):** `update_appointment_status`, `create_visit_for_appointment`, `update_visit_status`, `update_appointment_from_decision`, `flag_appointment_highway_infraction`.

**Known Issues:** Deprecated write functions do not propagate to MongoDB or Redis. `get_transport_stats_by_company` joins on `Driver.company_nif`; `manager_statistics_queries.get_transport_stats` joins on `Truck.company_nif` — may return different company sets.

---

## `cache_queries.py`

Thin Redis cache utilities: generic read-through and detection-specific helpers.

| Function | Returns | Notes |
|----------|---------|-------|
| `get_or_cache(key, ttl, fallback)` | `Optional[Any]` | JSON decode failures return `None` — fallback is NOT re-called on decode error |
| `cache_detection(detection_id, data, ttl=300)` | `None` | Stores at `detection:{detection_id}` |
| `get_cached_detection(detection_id)` | `Optional[dict]` | Retrieves cached detection dict |

**Known Issues:** `cache_detection`/`get_cached_detection` have no active callers — may be dead code.

---

## `decision_queries.py`

Orchestrates the full decision processing pipeline: Redis deduplication, cache checks, PostgreSQL writes via UoW + Outbox, and MongoDB writes for audit events.

```
process_incoming_decision()
    ├─ is_duplicate_and_mark()        → Redis SETNX dedup
    ├─ get_cached_decision()          → Redis GET
    ├─ cmd_process_decision()         → PostgreSQL via UoW + Outbox
    ├─ persist_decision_event()       → MongoDB direct write (tracked deviation)
    ├─ cache_decision_result()        → Redis SET
    ├─ invalidate_appointment_cache() → Redis DEL
    └─ create_notification()          → MongoDB direct write (tracked deviation)
```

| Function | Returns | Notes |
|----------|---------|-------|
| `is_duplicate_and_mark(lp, gate_id, ts, *, event_id)` | `bool` | Prefers `event_id`-based dedup; falls back to time-window |
| `get_cached_decision(lp, gate_id, ts)` | `Optional[dict]` | Redis GET |
| `cache_decision_result(lp, gate_id, ts, decision)` | `None` | Redis SET; TTL 3600 s |
| `persist_detection_event(event_data)` | `str` | MongoDB `agent_detections`; fallback to `detections` |
| `persist_decision_event(lp, gate_id, appointment_id, decision, data)` | `Optional[str]` | MongoDB `decision_events`; fallback to `events` |
| `get_detection_events(lp, gate_id, event_type, limit)` | `List[Dict]` | Reads `agent_detections` with fallback |
| `get_decision_events(lp, gate_id, decision, limit)` | `List[Dict]` | Reads `decision_events` with fallback |
| `process_incoming_decision(lp, gate_id, appointment_id, decision, ...)` | `Dict` | Main orchestration |
| `query_appointments_for_decision(gate_id)` | `Dict` | Candidates for Decision Engine |
| `update_appointment_after_infraction(lp, infraction)` | `Optional[Dict]` | UoW + Outbox if flag changes |

**Constants:** `DEDUP_TTL=300`, `BUCKET_SECONDS=30`, `DECISION_CACHE_TTL=3600`.

**Known Issues:** `persist_detection_event`, `persist_decision_event`, and `create_notification` are direct MongoDB writes, not outbox-driven (KNOWN_DEVIATIONS.md). `_store_infraction_decision()` has no inbox dedup.

---

## `driver_queries.py`

Read-only queries for `Driver` and driver-related `Appointment` data from PostgreSQL.

| Function | Returns | Notes |
|----------|---------|-------|
| `get_drivers(*, skip, limit, only_active)` | `List[Dict]` | Optional active filter |
| `get_driver_by_license(drivers_license)` | `Optional[Dict]` | Single driver lookup |
| `get_driver_active_appointment(drivers_license)` | `Optional[Dict]` | First `in_process`/`unloading` appointment |
| `get_driver_today_appointments(drivers_license)` | `List[Dict]` | Today, ordered by scheduled time |
| `get_driver_appointments(drivers_license, *, limit)` | `List[Dict]` | Full history, most recent first |

---

## `event_queries.py`

Read-side for the legacy MongoDB `events` collection. New code should prefer `/decisions/events/detections` and `/decisions/events/decisions`.

| Function | Returns | Notes |
|----------|---------|-------|
| `get_events(type, limit)` | `List[Dict]` | Sorted `timestamp DESC` |
| `get_event_by_id(event_id)` | `Optional[Dict]` | Returns `None` for invalid ObjectId |

---

## `manager_statistics_queries.py`

Five query functions for the frontend `statistics.ts` service contract. PostgreSQL-backed with one MongoDB query for decision analytics.

| Function | Returns | Notes |
|----------|---------|-------|
| `get_dashboard_summary(target_date)` | `Dict` | Keys: trucksInPort, trucksInTransit, scheduledCount, completedCount, entriesCount, exitsCount, avgPermanenceMinutes, avgWaitingMinutes, delayRate, slaCompliance, infractionCount, peakHour, portCapacity, congestionRate, vehiclesPerHour |
| `get_transport_stats(from_date, to_date)` | `List[Dict]` | Per-company KPIs via `Truck.company_nif` |
| `get_volume_data(from_date, to_date, interval)` | `List[Dict]` | Time-series `{timestamp, entries, exits}`; interval: hour/day/week |
| `get_alerts_breakdown(from_date, to_date)` | `List[Dict]` | `{type, count, percentage}` |
| `get_decision_analytics(target_date)` | `Dict` | From MongoDB `decision_events` aggregation |

**Known Issues:** `get_transport_stats` joins via `Truck.company_nif`; `arrival_queries.get_transport_stats_by_company` joins via `Driver.company_nif` — may return different company sets.

---

## `notification_queries.py`

Single write helper — inserts a notification document directly into MongoDB `notifications`. This is a **direct MongoDB write** (tracked deviation in KNOWN_DEVIATIONS.md). Used by `decision_queries.process_incoming_decision`.

```python
create_notification(gate_id, title, message, notification_type="info",
                    appointment_id=None, license_plate=None, extra=None) -> str
```

---

## `statistics_queries.py`

Read-side operational statistics from MongoDB (`agent_detections`, `decision_events`) and Redis counters.

`compute_hourly_statistics` writes aggregate snapshots directly to `statistics_hourly` (not outbox-driven).

| Function | Returns | Notes |
|----------|---------|-------|
| `get_real_time_metrics(gate_id)` | `Dict` | Current-hour Redis counters |
| `get_hourly_trend(gate_id, metric, hours)` | `Dict[str, int]` | Per-hour counter values |
| `get_detection_success_rate(gate_id, hours_ago)` | `List[Dict]` | Per-agent, per-hour |
| `get_decision_pipeline_performance(gate_id, hours_ago)` | `Dict` | Counts, acceptance rate, latency percentiles |
| `get_agent_performance(agent_type, gate_id, hours_ago)` | `Dict` | Per-agent detection + confidence stats |
| `get_complete_truck_journey(truck_id)` | `Dict` | Full detection-to-decision timeline |
| `get_operator_performance(hours_ago)` | `List[Dict]` | Manual-review times and override rates |
| `compute_hourly_statistics(gate_id, hour_timestamp)` | `Optional[dict]` | Upserts hourly snapshot to MongoDB |

All functions catch exceptions internally and return empty dicts/lists on error.

**Known Issues:** MongoDB `$percentile` requires MongoDB 7.0+; older versions fail silently.

---

## `worker_queries.py`

Read-only queries for `Worker`, `Operator`, and `Manager` data from PostgreSQL, with Redis counters for dashboards.

| Function | Returns | Notes |
|----------|---------|-------|
| `get_all_workers(*, skip, limit, only_active)` | `List[Dict]` | — |
| `get_operators(*, skip, limit)` | `List[Dict]` | Inner joins on `Operator` table |
| `get_managers(*, skip, limit)` | `List[Dict]` | Inner joins on `Manager` table |
| `get_worker_by_num(num_worker)` | `Optional[Dict]` | — |
| `get_operator_info(num_worker)` | `Optional[Dict]` | Joined with `Operator` |
| `get_manager_info(num_worker)` | `Optional[Dict]` | Joined with `Manager` |
| `get_operator_gate_dashboard(num_worker, gate_id)` | `Dict` | Next 10 arrivals + status counts |
| `get_manager_overview(num_worker)` | `Dict` | Port-wide KPIs: active gates, shifts, alerts, statistics |

---

## Related Docs

- [USE_CASES_REFERENCE.md](USE_CASES_REFERENCE.md)
- [ROUTES_REFERENCE.md](ROUTES_REFERENCE.md)
- [PERSISTENCE_REFERENCE.md](PERSISTENCE_REFERENCE.md)
- [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md)
- [KNOWN_DEVIATIONS.md](KNOWN_DEVIATIONS.md)
