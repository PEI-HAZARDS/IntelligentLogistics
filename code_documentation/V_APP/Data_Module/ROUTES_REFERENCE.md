# Routes Reference

> FastAPI routers — all mounted under `/api/v1` in `main.py`. GET endpoints read via queries; POST/PATCH/DELETE mutations go through command handlers (UoW + Outbox).

**Location:** `src/V_APP/Data_Module/routes/`

---

## `alerts.py` — `/alerts`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/alerts` | Lists alerts; params: `skip`, `limit` (max 500), `alert_type`, `visit_id` |
| `GET` | `/alerts/active` | Alerts from last 24 hours; param: `limit` (1–200) |
| `GET` | `/alerts/stats` | Alert counts by type; params: `from`, `to` (YYYY-MM-DD) |
| `GET` | `/alerts/reference/adr-codes` | ADR/UN substance codes dict |
| `GET` | `/alerts/reference/kemler-codes` | Kemler danger codes dict |
| `GET` | `/alerts/visit/{visit_id}` | All alerts linked to a visit |
| `GET` | `/alerts/{alert_id}` | Single alert by ID. `404` if not found |
| `POST` | `/alerts` | Create generic alert; body: `{visit_id?, type, description, image_url?}`. Returns 201 |
| `POST` | `/alerts/hazmat` | Create hazmat/ADR alert; body: `{appointment_id, un_code?, kemler_code?, detected_hazmat?}`. Returns 201. `404` if appointment not found |

---

## `arrivals.py` — `/arrivals`

`GET /{id}` is the only two-tier read: Redis hot cache → PostgreSQL fallback with cache warm-up on miss.

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/arrivals` | Paginated list; params: `page`, `limit`, `gate_id`, `status`, `statuses` (comma-sep), `scheduled_date`, `search`, `highway_infraction` |
| `GET` | `/arrivals/stats` | Counts by status; params: `gate_id`, `target_date` |
| `GET` | `/arrivals/avg-permanence` | Average visit duration for completed visits |
| `GET` | `/arrivals/transport-stats` | Per-company stats; param: `days` (1–365) |
| `GET` | `/arrivals/next/{gate_id}` | Upcoming arrivals for operator sidebar |
| `GET` | `/arrivals/{id}/detail` | Enriched view (driver, company, booking, cargo, gates, visit) |
| `GET` | `/arrivals/{id}` | Single appointment — Redis → PG fallback |
| `GET` | `/arrivals/pin/{arrival_id}` | Lookup by PIN/arrival_id (driver app) |
| `GET` | `/arrivals/query/license-plate/{lp}` | Lookup by truck plate (Decision Engine) |
| `PATCH` | `/arrivals/{id}/highway-infraction` | Sets `highway_infraction = True` via UoW |
| `PATCH` | `/arrivals/{id}/status` | Updates status; body: `{status, notes?}` |
| `POST` | `/arrivals/{id}/decision` | Processes Decision Engine result; body: `{decision, status, notes?, alerts[]}` |
| `POST` | `/arrivals/{id}/visit` | Creates visit on truck arrival; body: `{shift_gate_id, shift_type, shift_date}` |
| `PATCH` | `/arrivals/{id}/visit` | Updates visit state; body: `{state, out_time?}` |

**Known Issues:** `GET /{id}/detail` and `GET /{id}` overlap — `/detail` must be registered first (it is). Write endpoints re-query PG after commit to build the response.

---

## `decisions.py` — `/decisions`

Primary integration point for the Decision Engine microservice.

**Pydantic Models:**
- `DecisionIncomingRequest` — `event_id?`, `license_plate`, `gate_id`, `appointment_id?`, `decision`, `appointment_status?`, `delivery_state?`, `notes?`, `alerts?`. Normalises legacy `status`→`appointment_status` and `state`→`delivery_state`.
- `DetectionEventRequest` — `type`, `license_plate?`, `gate_id`, `confidence?`, `agent`, `raw_data?`

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/decisions/process` | Main decision endpoint. `422` if `appointment_status` missing when `appointment_id` provided |
| `POST` | `/decisions/query-appointments` | Decision Engine queries candidate appointments (`in_transit`/`delayed`) for a gate |
| `POST` | `/decisions/detection-event` | Registers AI agent detection to MongoDB. Returns `{status, event_id}` |
| `GET` | `/decisions/events/detections` | Lists detection events; params: `license_plate?`, `gate_id?`, `event_type?`, `limit` (1–500) |
| `GET` | `/decisions/events/decisions` | Lists decision events; params: `license_plate?`, `gate_id?`, `decision?`, `limit` |
| `GET` | `/decisions/events/{event_id}` | Single event by MongoDB ObjectId. `400` on invalid ID, `404` if not found |
| `POST` | `/decisions/manual-review/{appointment_id}` | Operator review; params: `decision` (approved\|rejected), `notes?`, `gate_id?`. When approved + gate_id: creates Visit |

**Known Issues:** Decision Engine endpoint auth not enforced. MongoDB audit in `manual_review` may fail silently.

---

## `driver.py` — `/drivers`

Driver mobile app and backoffice endpoints. Authentication uses internal JWT; planned migration to Keycloak.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/drivers/login` | Login; body: `{drivers_license, password}`. Returns `{token, drivers_license, name, company_nif, company_name}`. `401` on failure |
| `POST` | `/drivers/claim` | Claim appointment by PIN (`arrival_id`); params: `drivers_license`, `debug` (requires `DEBUG_MODE=true`). Returns dock + cargo info |
| `GET` | `/drivers/me/active` | Driver's active appointment (`in_process` or `unloading`) |
| `GET` | `/drivers/me/today` | Today's appointments, ordered by scheduled time |
| `GET` | `/drivers/me/history` | Appointment history; param: `limit` (1–200) |
| `GET` | `/drivers` | All drivers (backoffice); params: `skip`, `limit`, `only_active` |
| `GET` | `/drivers/{drivers_license}` | Single driver. `404` if not found |
| `GET` | `/drivers/{drivers_license}/arrivals` | Appointment history for a driver |

**Known Issues:** JWT Bearer not enforced on `GET /me/*` — `drivers_license` is a plain query param. `ClaimAppointmentResponse` always returns `dock_bay_number=None` and `dock_location=None`; dock assignment not implemented.

---

## `events.py` — `/events` (legacy)

Single legacy endpoint. No prefix defined — relies on `/api/v1` from `main.py`. New consumers should use `/decisions/events/detections` and `/decisions/events/decisions`.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/events` | Recent events from legacy MongoDB `events` collection; params: `type?`, `limit` |

---

## `notifications.py` — `/notifications`

Operator notifications stored in MongoDB `notifications`. Notifications are created by the decision pipeline — this router only exposes reads and mark-read.

**`NotificationOut`:** `id`, `gate_id`, `title`, `message`, `type`, `read`, `created_at`, `appointment_id?`, `license_plate?` (extra fields pass through via `extra="allow"`).

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/notifications` | Most recent for a gate; params: `gate_id` (required), `limit` (max 200), `unread_only` |
| `PATCH` | `/notifications/{notification_id}/read` | Mark single as read. `400` on invalid ObjectId, `404` if not found |
| `PATCH` | `/notifications/read-all` | Mark all unread for a gate; param: `gate_id`. Returns `{updated: int}` |

**Known Issues:** No authentication — any client knowing a `gate_id` can read or clear all notifications.

---

## `statistics.py` — `/statistics`

All statistics and analytics endpoints. Combines `manager_statistics_queries` (PostgreSQL + MongoDB, frontend contract) and `statistics_queries` (MongoDB + Redis, operational dashboards).

### Manager Dashboard (frontend `statistics.ts` contract)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/statistics/summary` | Daily dashboard summary; param: `date` (default today) |
| `GET` | `/statistics/by-company` | Per-company KPIs; params: `from`, `to` (YYYY-MM-DD) |
| `GET` | `/statistics/volume` | Time-series entry/exit counts; params: `from`, `to`, `interval` (hour\|day\|week). `400` on bad interval |
| `GET` | `/statistics/alerts` | Alerts breakdown by type with percentages; params: `from`, `to` |
| `GET` | `/statistics/decision-analytics` | Decision analytics from MongoDB; param: `date` |

### Real-Time Metrics

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/statistics/realtime/{gate_id}` | Current-hour Redis counters. `404` if no metrics |
| `GET` | `/statistics/trend/{gate_id}/{metric}` | Hourly trend; param: `hours` (1–168) |

### Aggregated Analytics

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/statistics/detections/success-rate` | Detection success rate by agent; params: `gate_id` (required), `hours` |
| `GET` | `/statistics/pipeline/performance` | Totals, acceptance rate, latency percentiles |
| `GET` | `/statistics/agent/{agent_type}/performance` | Per-agent performance (AgentA/B/C) |
| `GET` | `/statistics/operators/performance` | Operator manual-review stats |

### Truck Journey & Admin

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/statistics/truck/{truck_id}/journey` | Full detection-to-decision timeline. `404` if not found |
| `POST` | `/statistics/compute/hourly/{gate_id}` | Triggers hourly materialisation; param: `hour_timestamp` (ISO UTC) |
| `GET` | `/statistics/dashboard/summary` | Legacy combined dashboard (deprecated); param: `gate_id` (required) |

**Known Issues:** `POST /statistics/compute/hourly/{gate_id}` writes directly to MongoDB — not outbox-driven.

---

## `worker.py` — `/workers`

Backoffice and API Gateway auth flow. Mutations go through `SqlAlchemyUnitOfWork` via `worker_handlers`; reads use `worker_queries`. JWT is currently issued by `generate_internal_jwt`; Keycloak integration is planned.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/workers/login` | Authenticate worker; returns `{token, num_worker, name, email, active}`. `401` on failure |
| `GET` | `/workers/by-email/{email}` | Profile lookup by email (API Gateway post-Keycloak). `404` if not found/deactivated |
| `GET` | `/workers/shifts` | Paginated shift list; params: `target_date`, `shift_type`, `gate_id` |
| `GET` | `/workers/operators` | Lists operators; params: `skip`, `limit` |
| `GET` | `/workers/operators/me` | Authenticated operator info via `num_worker` query param |
| `GET` | `/workers/operators/{num_worker}` | Single operator. `404` if missing |
| `GET` | `/workers/operators/{num_worker}/current-shift/{gate_id}` | Operator's current shift for a gate |
| `GET` | `/workers/operators/{num_worker}/shifts` | All shifts for an operator |
| `GET` | `/workers/operators/{num_worker}/dashboard/{gate_id}` | Upcoming arrivals + status stats |
| `GET` | `/workers/managers` | Lists managers |
| `GET` | `/workers/managers/me` | Authenticated manager info via `num_worker` |
| `GET` | `/workers/managers/{num_worker}` | Single manager |
| `GET` | `/workers/managers/{num_worker}/shifts` | Shifts supervised by a manager |
| `GET` | `/workers/managers/{num_worker}/overview` | Manager dashboard — gates, shifts, alerts, performance |
| `GET` | `/workers` | Lists all workers; params: `skip`, `limit`, `only_active` |
| `GET` | `/workers/{num_worker}` | Single worker. `404` if missing |
| `POST` | `/workers/password` | Update password via `num_worker` query param |
| `POST` | `/workers/email` | Update email. `400` if in use |
| `POST` | `/workers` | Create worker. Returns 201 |
| `DELETE` | `/workers/{num_worker}` | Deactivate worker. `404` if missing |
| `POST` | `/workers/{num_worker}/promote` | Promote operator → manager |

**Known Issues:** `POST /workers/password` and `/email` accept `num_worker` with no JWT enforcement.

---

## Related Docs

- [QUERIES_REFERENCE.md](QUERIES_REFERENCE.md)
- [USE_CASES_REFERENCE.md](USE_CASES_REFERENCE.md)
- [PERSISTENCE_REFERENCE.md](PERSISTENCE_REFERENCE.md)
- [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md)
