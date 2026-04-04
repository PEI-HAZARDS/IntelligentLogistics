# Current State Analysis — Data Module (Phase 1 Discovery)

> **Date:** 2026-03-21
> **Branch:** `refactor/data_module`
> **Purpose:** Pre-execution discovery for demo deadline (Tuesday 2026-03-24)

---

## 1. Kafka Consumer Inventory

### 1.1 KafkaDecisionConsumer (PRIMARY — Data Module)

**File:** `src/V_APP/Data_Module/infrastructure/messaging/kafka_decision_consumer.py`

| Property | Value |
|----------|-------|
| **Topics** | `agent-decision-{gate_id}`, `operator-decision-{gate_id}`, `infraction-decision-{gate_id}` |
| **Consumer Group** | `data-module-decisions` |
| **Library** | confluent_kafka via `KafkaConsumerWrapper` |
| **Auto-commit** | Disabled (`enable.auto.commit = False`) |

**Event Envelope (built by `_dispatch_container_moved`):**

```
event_id:        UUID v4
correlation_id:  truck_id
causation_id:    None
aggregate_type:  "appointment"
aggregate_id:    str(appointment_id)
event_type:      "ContainerMoved"
event_version:   1
occurred_at:     datetime.now(timezone.utc)
producer:        msg.topic()
partition_key:   truck_id
payload:         decision_data dict
```

**Field Normalization:**
- `truck_id` extracted from Kafka message headers
- `gate_id` parsed from topic name suffix
- `appointment_id` resolved from `decision_data` or via license plate lookup
- `status` / `appointment_status` — both used inconsistently (see §3 Mismatches)

**Idempotency Gate:**
- ContainerMoved path: `InboxEvent.UNIQUE(event_id)` via `uow.inbox.try_insert_received(event, ctx)` → duplicate returns False → ACK + NOOP
- Infraction path: **NO idempotency gate** — `_store_infraction_decision()` writes directly to MongoDB

**Offset Commit Strategy:**
- ContainerMoved: manual commit ONLY after `ContainerMovedHandler.handle()` succeeds
- Infraction: **no controlled offset commit** — committed implicitly or not at all

**Error Handling:**
- ContainerMoved: inbox marks `FAILED` or `DEAD_LETTER` on handler error; no Kafka DLQ topic
- Infraction: catch-all with `sleep(1)`, no retry/DLQ, errors logged only

**Metrics:** None emitted (logger only)

### 1.2 Outbox Worker (Projection — polls PostgreSQL)

**File:** `src/V_APP/Data_Module/scripts/simple_outbox_worker.py`

| Property | Value |
|----------|-------|
| **Source** | PostgreSQL `outbox_events` table (poll every 2s, batch 50) |
| **Targets** | MongoDB (`appointments_read`, `decision_events`), Redis (appointment cache, counters) |
| **Idempotency** | Upsert by `event_id` (Mongo) and `appointment_id` (Redis) |
| **Retry** | Exponential backoff (2^n, cap 60s, +0-2s jitter), max 5 retries |
| **DLQ** | `DEAD_LETTER` status in outbox table after max retries or permanent error |
| **Checkpoint** | None — re-scans all PENDING on restart |

### 1.3 Other Consumers (non-Data Module)

| Component | Topics | Group | DB Writes | Idempotency |
|-----------|--------|-------|-----------|-------------|
| **Decision Engine** | `lp-results-{gid}`, `hz-results-{gid}` | `decision-engine-group` | None (API read-only) | In-memory buffer expiry |
| **Infraction Engine** | `lp-results-{gid}`, `hz-results-{gid}` | `infraction-engine-group` | None (API read-only) | In-memory buffer expiry |
| **API Gateway** | `agent-decision-{gid}`, `infraction-decision-{gid}`, `scale-up`, `scale-down` | `api-gateway-group` | None (WebSocket broadcast) | None |
| **AI Agents** | `reset-agentA-{gid}`, control topics | `{agent}-{gid}-group` | MinIO images only | None |

### 1.4 Decision Correlation Flow (DecisionCorrelator)

```
Agent Decision ACCEPTED → build final → dispatch ContainerMovedHandler immediately
Agent Decision MANUAL_REVIEW → store in Redis (pending_review:{truck_id}, TTL 30min) → wait
Operator Decision arrives → fetch agent data from Redis → merge → dispatch ContainerMovedHandler
Infraction Decision → _store_infraction_decision() → direct Mongo write + PG flag update
```

**Known issue:** `pending_review:{truck_id}` key can collide if truck_id is reused within 30min TTL window.

---

## 2. Contract Map: Frontend → Endpoint → Payload → Response → UI Usage

### 2.1 Web Frontend (Gate Operator / Logistics Manager)

#### arrivals.ts

| Function | Method | Path | Request | Response | UI Usage |
|----------|--------|------|---------|----------|----------|
| `getArrivals` | GET | `/arrivals` | Query: `ArrivalsQueryParams` (page, limit, gate_id, status, search, highway_infraction) | `PaginatedResponse<Appointment>` OR legacy `Appointment[]` | ArrivalsList.tsx — main table |
| `getArrivalsStats` | GET | `/arrivals/stats` | Query: gate_id, target_date | `Record<string, number>` {in_transit, in_process, delayed, completed, total, infractions} | ArrivalsList.tsx — status badges |
| `getUpcomingArrivals` | GET | `/arrivals/next/{gateId}` | Query: limit, status | `Appointment[]` | Operator dashboard — queue |
| `getArrival` | GET | `/arrivals/{appointmentId}` | — | `Appointment` | ArrivalDetail.tsx |
| `getArrivalByPin` | GET | `/arrivals/pin/{arrivalId}` | — | `Appointment` | PIN lookup |
| `queryArrivalsByLicensePlate` | GET | `/arrivals/query/license-plate/{plate}` | Query: partial params | `Appointment[]` | Decision Engine query |
| `updateArrivalStatus` | PATCH | `/arrivals/{appointmentId}/status` | Body: `{status, notes?}` | `Appointment` | Status update button |
| `createVisit` | POST | `/arrivals/{appointmentId}/visit` | Body: `{shift_gate_id, shift_type, shift_date}` | `Visit` | Visit creation on accept |
| `updateVisit` | PATCH | `/arrivals/{appointmentId}/visit` | Body: `{state, entry_time?, out_time?, notes?}` | `Visit` | Visit status update |

#### alerts.ts

| Function | Method | Path | Request | Response | UI Usage |
|----------|--------|------|---------|----------|----------|
| `getAlerts` | GET | `/alerts` | Query: skip, limit, alert_type, visit_id | `Alert[]` | Alerts panel |
| `getActiveAlerts` | GET | `/alerts/active` | Query: limit | `Alert[]` | Active alerts badge |
| `getAlertsStats` | GET | `/alerts/stats` | — | `Record<string, number>` | Stats dashboard |
| `getVisitAlerts` | GET | `/alerts/visit/{visitId}` | — | `Alert[]` | Visit detail |
| `getAlert` | GET | `/alerts/{alertId}` | — | `Alert` | Alert detail |
| `createAlert` | POST | `/alerts` | Body: `{visit_id?, type, description, image_url?}` | `Alert` | Manual alert |
| `createHazmatAlert` | POST | `/alerts/hazmat` | Body: `{appointment_id, un_code?, kemler_code?, detected_hazmat?}` | `Alert` | Hazmat detection |

#### decisions.ts

| Function | Method | Path | Request | Response | UI Usage |
|----------|--------|------|---------|----------|----------|
| `getDetectionEvents` | GET | `/decisions/events/detections` | Query: license_plate, gate_id, event_type, limit | `DetectionEvent[]` | Events log |
| `getDecisionEvents` | GET | `/decisions/events/decisions` | Query: license_plate, gate_id, decision, limit | `DecisionEvent[]` | Decisions log |
| `getEvent` | GET | `/decisions/events/{eventId}` | — | Event doc | Event detail |
| `processDecision` | POST | `/decisions/process` | Body: `DecisionIncomingRequest` | void | Decision Engine callback |
| `queryAppointments` | POST | `/decisions/query-appointments` | Body: `{time_frame?, gate_id?}` | `{found, candidates[], message?}` | Decision Engine query |
| `submitManualReview` | POST | `/manual-review/` | **Query params**: gate_id, license_plate, decision, decision_reason, + optional metadata | void | Operator approve/reject |

#### notifications.ts

| Function | Method | Path | Request | Response | UI Usage |
|----------|--------|------|---------|----------|----------|
| `getNotifications` | GET | `/notifications` | Query: gate_id, limit, unread_only | `Notification[]` | Notification panel |
| `getUnreadCount` | GET | `/notifications` | Query: gate_id, limit=200, unread_only=true | count from array length | Badge counter |
| `markNotificationRead` | PATCH | `/notifications/{id}/read` | — | `Notification` | Mark read |
| `markAllNotificationsRead` | PATCH | `/notifications/read-all` | Query: gate_id | `{updated: number}` | Mark all read |

#### workers.ts

| Function | Method | Path | Request | Response | UI Usage |
|----------|--------|------|---------|----------|----------|
| `login` | POST | `/workers/login` | Body: `{email, password}` | `{token, num_worker, name, email, active}` | Login page |
| `getOperators` | GET | `/workers/operators` | Query: skip, limit | `WorkerInfo[]` | Admin panel |
| `getOperatorDashboard` | GET | `/workers/operators/{num}/dashboard/{gateId}` | — | `OperatorDashboard` | Gate dashboard |
| `getManagerDashboard` | GET | `/workers/managers/{num}/overview` | — | `ManagerOverview` | Manager dashboard |
| `getShifts` | GET | `/workers/shifts` | Query: target_date, shift_type, gate_id | `ShiftListItem[]` | Shift management |
| (+ 15 more CRUD endpoints) | | | | | |

#### statistics.ts

| Function | Method | Path | Request | Response | UI Usage |
|----------|--------|------|---------|----------|----------|
| `getDashboardSummary` | GET | `/statistics/summary` | Query: date | `DashboardSummary` {totalTrucks, entriesCount, exitsCount, avgPermanenceMinutes, delayRate, slaCompliance} | Manager KPIs |
| `getTransportStats` | GET | `/statistics/by-company` | Query: from, to | `TransportStats[]` | Company table |
| `getVolumeData` | GET | `/statistics/volume` | Query: from, to, interval | `VolumeDataPoint[]` | Volume chart |
| `getAlertsBreakdown` | GET | `/statistics/alerts` | Query: from, to | `AlertsBreakdown[]` | Alerts chart |

#### streams.ts

| Function | Method | Path | Response |
|----------|--------|------|----------|
| `getLowStreamUrl` | GET | `/stream/{gateId}/low` | `StreamInfo` {gate_id, quality, hls_url, webrtc_url} |
| `getHighStreamUrl` | GET | `/stream/{gateId}/high` | `StreamInfo` |
| `getStreamUrl` | GET | `/stream/{gateId}/{quality}` | `string` (webrtc_url) |

### 2.2 Driver App (React Native)

#### drivers.ts

| Function | Method | Path | Request | Response | UI Usage |
|----------|--------|------|---------|----------|----------|
| `login` | POST | `/drivers/login` | Body: `{drivers_license, password}` | `{token, drivers_license, name, company_nif?, company_name?}` | Login screen |
| `claimArrival` | POST | `/drivers/claim` | Body: `{arrival_id}`, Query: drivers_license | `ClaimAppointmentResponse` {appointment_id, dock_bay_number, dock_location, license_plate, cargo_description, navigation_url} | PIN claim |
| `getMyActiveArrival` | GET | `/drivers/me/active` | Query: drivers_license | `Appointment \| null` | Active screen |
| `getMyTodayArrivals` | GET | `/drivers/me/today` | Query: drivers_license | `Appointment[]` | Home screen |
| `getDriver` | GET | `/drivers/{license}` | — | `Driver` | Profile |
| `getDriverArrivals` | GET | `/drivers/{license}/arrivals` | Query: limit | `Appointment[]` | History |
| `updateArrivalStatus` | PATCH | `/arrivals/{appointmentId}/status` | Body: `{status, notes?}` | void | Status transitions |
| `completeAppointment` | PATCH | `/arrivals/{appointmentId}/status` | Body: `{status: 'completed'}` | void | Complete button |

---

## 3. Contract Mismatches Identified

### 3.1 Status Terminology Inconsistency

| Location | Field | Values | Issue |
|----------|-------|--------|-------|
| **PostgreSQL** `appointment.status` | `status` | `in_transit, in_process, canceled, delayed, completed` | Source of truth — **no UNLOADING state** |
| **PostgreSQL** `visit.state` | `state` | `not_started, unloading, completed` | Visit-level delivery status — has `unloading` |
| **Frontend types** | `AppointmentStatusEnum` | `in_transit, in_process, canceled, delayed, completed` | Matches PG appointment |
| **Frontend types** | `DeliveryStatusEnum` | `not_started, unloading, completed` | Matches PG visit |
| **Driver app** | `DeliveryPhase` (local) | `idle, in_transit, gate_opening, in_port, unloading, completed` | **UI-only state machine**, not synced with backend |
| **Kafka consumer** | `decision_data.status` vs `decision_data.appointment_status` | Inconsistent field names | Consumer uses both interchangeably |

**Critical gap:** The driver app has a local `DeliveryPhase` state machine that is NOT synchronized with the backend. The "unloading" phase is purely client-side — the backend appointment stays `in_process` during unloading. To implement the UNLOADING requirement, we need to decide:
- **Option A:** Add `unloading` to `AppointmentStatusEnum` (backend + all frontends)
- **Option B:** Keep appointment as `in_process`, use `visit.state = 'unloading'` (already exists), and surface visit state in APIs

### 3.2 Notification Storage Inconsistency

| Write path | Storage | Transactional? |
|------------|---------|----------------|
| `kafka_decision_consumer._store_infraction_decision()` | MongoDB direct | No — outside UoW |
| `notification_queries.create_notification()` | MongoDB direct | No — fire-and-forget |
| Alert-based notifications | Not created — alerts go to PG, no notification linkage | N/A |

**Issue:** Notifications are written directly to MongoDB, violating Guardrails 2 and 3. No outbox event, no idempotency, no retry on failure.

### 3.3 Infraction Flow Gaps

Current infraction path:
```
InfractionEngine → Kafka (infraction-decision-{gate_id})
  → KafkaDecisionConsumer._store_infraction_decision()
    → MongoDB write (infraction event) — NO inbox dedup
    → PG write (appointment.highway_infraction = True) — via cmd_flag_highway_infraction + UoW
    → MongoDB write (notification) — direct, no outbox
  → API Gateway (WebSocket broadcast to gate UI)
```

**Gaps:**
1. No inbox dedup for infraction events → duplicate processing possible
2. Notification write is not transactional with PG update
3. Driver notification not created — only gate notification exists
4. Alert record not created in PG alerts table — only the `highway_infraction` flag is set
5. No outbox event for infraction → Redis/Mongo projections may be stale

### 3.4 Auto-Accept Flow Gaps

Current auto-accept path:
```
DecisionEngine → Kafka (agent-decision-{gate_id})
  → KafkaDecisionConsumer (agent decision = ACCEPTED)
  → DecisionCorrelator.resolve_agent() → immediate dispatch
  → _dispatch_container_moved()
    → ContainerMovedHandler.handle() [UoW: inbox + PG state + outbox]
    → Kafka offset commit
  → [Outbox Worker: project to Mongo/Redis]
```

**Gaps:**
1. Visit not auto-created on accept — gate operator must create visit manually
2. Driver notification not sent on accept — no notification creation in ContainerMovedHandler
3. Appointment transitions to `in_process` but visit.state starts as `unloading` (skip `not_started`)
4. Gate UI updates via WebSocket (from API Gateway consumer), but appointment label in list may be stale until outbox worker projects

### 3.5 Frontend localStorage Usage

| Key | Type | Issue |
|-----|------|-------|
| `auth_token` | Auth | Acceptable (JWT bearer) |
| `user_info` | Auth metadata | Acceptable (session context) |
| `theme` | UI preference | Acceptable |
| `ws_payloads` | Decision debug data | **Low risk** — debug only, max 10 items, clearable |

**Verdict:** No business data stored in localStorage. The `ws_payloads` key is debug/transient, not business persistence.

### 3.6 Missing Endpoints / Payload Gaps

| Frontend expects | Backend provides | Gap |
|------------------|------------------|-----|
| `GET /workers/operators/me` | Not a route — frontend constructs from `num_worker` query param | Works via catch-all `/workers/operators/{num_worker}` |
| `GET /workers/managers/me` | Same pattern | Works via catch-all |
| `PATCH /arrivals/{id}/status` with `status: 'unloading'` | Not a valid `AppointmentStatusEnum` value | **UNLOADING state not in backend enum** |
| Driver notification on accept/infraction | No endpoint creates driver notifications | **Missing: driver push notification path** |
| Energy metrics iframe in Manager dashboard | No backend endpoint needed (static iframe) | Frontend-only change |

---

## 4. Canonical Schemas

### 4.1 Appointment (PostgreSQL — Source of Truth)

```
id:                     INTEGER PK
arrival_id:             VARCHAR(50) UNIQUE — auto-generated by PG sequence trigger
booking_reference:      VARCHAR(50) FK→booking.reference
driver_license:         VARCHAR(50) FK→driver.drivers_license
truck_license_plate:    VARCHAR(20) FK→truck.license_plate
terminal_id:            INTEGER FK→terminal.id
gate_in_id:             INTEGER FK→gate.id (nullable)
gate_out_id:            INTEGER FK→gate.id (nullable)
scheduled_start_time:   TIMESTAMP
expected_duration:      INTEGER (minutes)
status:                 ENUM(in_transit, in_process, canceled, delayed, completed) DEFAULT 'in_transit'
version:                INTEGER DEFAULT 1 — optimistic concurrency
highway_infraction:     BOOLEAN DEFAULT FALSE
notes:                  TEXT
```

**Computed:** `delayed` is derived at query time if `scheduled_start_time + 1min < now()` and status is `in_transit`.

### 4.2 Visit (PostgreSQL)

```
appointment_id:     INTEGER PK FK→appointment.id
shift_gate_id:      INTEGER \
shift_type:         ENUM(MORNING, AFTERNOON, NIGHT) | composite FK→shift
shift_date:         DATE /
entry_time:         TIMESTAMP
out_time:           TIMESTAMP
state:              ENUM(not_started, unloading, completed) DEFAULT 'unloading'
```

### 4.3 Alert (PostgreSQL)

```
id:              INTEGER PK AUTOINCREMENT
visit_id:        INTEGER FK→visit.appointment_id (nullable)
appointment_id:  INTEGER FK→appointment.id (nullable) — for pre-visit alerts
type:            ENUM(generic, safety, problem, operational) DEFAULT 'generic'
description:     TEXT
image_url:       TEXT
timestamp:       TIMESTAMP DEFAULT now()
```

### 4.4 Driver (PostgreSQL)

```
drivers_license:        VARCHAR(50) PK
company_nif:            VARCHAR(20) FK→company.nif
name:                   VARCHAR(100)
password_hash:          TEXT
mobile_device_token:    TEXT
active:                 BOOLEAN DEFAULT TRUE
created_at:             TIMESTAMP
session_token:          VARCHAR(64) INDEXED
session_expires_at:     TIMESTAMP
current_appointment_id: INTEGER
```

### 4.5 Gate Decision Event (Kafka → Data Module)

**From Decision Engine (agent-decision-{gate_id}):**
```json
{
  "truck_id": "string (from headers)",
  "license_plate": "string",
  "decision": "ACCEPTED | MANUAL_REVIEW | REJECTED",
  "appointment_id": "int | null",
  "appointment_status": "string",
  "delivery_state": "string",
  "notes": "string",
  "alerts": [{"type": "string", "description": "string"}],
  "extra_data": {}
}
```

**From Infraction Engine (infraction-decision-{gate_id}):**
```json
{
  "truck_id": "string (from headers)",
  "license_plate": "string",
  "infraction_type": "highway_route | speed | weight",
  "severity": "warning | critical",
  "details": {}
}
```

### 4.6 Notification (MongoDB)

```json
{
  "_id": "ObjectId",
  "gate_id": "int",
  "title": "string",
  "message": "string",
  "type": "info | warning | danger | success",
  "read": "boolean (default false)",
  "created_at": "datetime UTC",
  "appointment_id": "int | null",
  "license_plate": "string | null"
}
```

### 4.7 EventEnvelope (domain/events.py — frozen dataclass)

```
event_id:        str (UUIDv7)
correlation_id:  str
causation_id:    Optional[str]
aggregate_type:  str
aggregate_id:    str
event_type:      str
event_version:   int
occurred_at:     datetime (UTC)
producer:        str
partition_key:   str
payload:         dict[str, Any]
```

---

## 5. Guardrail Compliance Summary

| # | Guardrail | ContainerMoved | Infraction | Auto-Accept | Notifications | Alerts |
|---|-----------|----------------|------------|-------------|---------------|--------|
| 1 | Inbox idempotency | ✅ UNIQUE(event_id) | ❌ No dedup | ✅ (via ContainerMoved) | ❌ N/A | ✅ UoW |
| 2 | Single-DB command tx | ✅ PG only in UoW | ⚠️ PG via UoW + Mongo direct | ✅ PG only | ❌ Mongo direct | ✅ PG only |
| 3 | Transactional Outbox | ✅ Outbox append | ❌ No outbox | ✅ Outbox append | ❌ No outbox | ✅ Outbox append |
| 4 | Inbox state machine | ✅ Full RECEIVED→PROCESSED | ❌ Not used | ✅ (via ContainerMoved) | ❌ N/A | ✅ N/A (HTTP) |
| 5 | CQRS read split | ✅ Redis/Mongo→PG | ❌ Direct PG read | ✅ Projected | ❌ Mongo direct | ❌ PG direct |
| 6 | Repository + UoW | ✅ | ⚠️ Partial | ✅ | ❌ Raw Mongo | ✅ |
| 7 | Replayable projections | ⚠️ Idempotent but no checkpoint | ❌ N/A | ⚠️ Same | ❌ N/A | ⚠️ Same |
| 8 | DLQ per topic | ⚠️ Inbox DEAD_LETTER only | ❌ None | ⚠️ Same | ❌ None | ⚠️ Outbox DEAD_LETTER |
| 9 | Versioned events | ✅ event_version field | ❌ No envelope | ✅ Same envelope | ❌ N/A | ✅ event_version |
| 10 | Metrics/SLOs | ❌ Logger only | ❌ None | ❌ Same | ❌ None | ❌ None |
| 11 | Frontend compat | ✅ Routes preserved | ⚠️ No driver notif | ⚠️ No driver notif | ✅ Mongo→frontend | ✅ |

---

## 6. Demo Flow Gap Analysis

### Step 1: Gate selects next appointment, sets PIN
- **Status:** ✅ Working — `GET /arrivals/next/{gateId}`, `GET /arrivals/pin/{arrivalId}`

### Step 2: Truck arrives, passes camera 1
- **Status:** ✅ Working — AI agents detect, produce to `lp-results-{gid}`, `hz-results-{gid}`

### Step 3: Infraction detected (highway route warning)
- **Gaps:**
  - ❌ No inbox dedup for infraction events
  - ❌ No PG alert record created (only `highway_infraction` flag set)
  - ❌ No driver notification (only gate notification created)
  - ⚠️ Gate UI alert updates via WebSocket but appointment label in list may lag

### Step 4: Camera 2 detects truck, auto-accept
- **Gaps:**
  - ❌ Visit not auto-created on accept (requires manual operator action)
  - ❌ No driver notification on accept
  - ⚠️ Appointment goes to `in_process` but no visit exists yet

### Step 5: Driver app shows IN_PROCESS, enables UNLOADING action
- **Gaps:**
  - ❌ `UNLOADING` not a valid `AppointmentStatusEnum` — driver app uses local `DeliveryPhase` only
  - **Decision needed:** Use `visit.state = 'unloading'` (exists) or add to appointment enum
  - Driver app ActiveArrivalScreen.tsx already has UNLOADING UI phase but it's local-only
  - Backend `PATCH /arrivals/{id}/status` would reject `status: 'unloading'`

### Step 6: Driver completes unloading → COMPLETED
- **Gaps:**
  - ⚠️ `completeAppointment()` sends `{status: 'completed'}` — this works
  - ❌ No gate UI notification of completion
  - ❌ Manager metrics may not reflect completion in real-time (outbox worker 2s lag)

### Energy iframe in Manager dashboard
- **Status:** Frontend-only change needed in `ManagerDashboard.tsx`

---

## 7. Recommended Phase 2 Execution Plan

### 7.1 UNLOADING State Decision

**Recommendation: Option A — Add `unloading` to AppointmentStatusEnum**

Rationale:
- The demo requires the gate UI to show "unloading" state
- Manager metrics need to track unloading time
- Visit.state already has `unloading` but is not surfaced in appointment-level APIs
- Adding to the appointment enum is simpler than teaching all frontends to merge appointment + visit state

Changes required:
1. PostgreSQL: `ALTER TYPE appointment_status ADD VALUE 'unloading'`
2. Backend: Update `AppointmentStatusEnum` in `schemas.py` and `sql_models.py`
3. Backend: Allow `in_process → unloading` and `unloading → completed` transitions
4. Frontend web: Add status color/label for `unloading`
5. Driver app: Map `DeliveryPhase.unloading` to backend status `unloading`
6. Stats: Include `unloading` in `/arrivals/stats` response

### 7.2 Infraction Flow Fix

1. Add inbox dedup for infraction events in `_store_infraction_decision()`
2. Create PG alert record (type: `operational`, description: highway infraction details)
3. Create driver notification via `notification_queries.create_notification()` with driver context
4. Emit outbox event for infraction state change

### 7.3 Auto-Accept Flow Fix

1. Auto-create Visit when ContainerMovedHandler transitions to `in_process`
2. Create driver notification on accept (gate opening)
3. Create gate notification on accept

### 7.4 Notification Reliability (Post-Demo Candidate)

1. Move notification creation into UoW transaction as outbox event
2. Add notification projection handler in outbox worker
3. This is lower priority for demo — current MongoDB direct write works for happy path

### 7.5 Frontend Changes

1. Add `unloading` status handling to web frontend (ArrivalsList, ArrivalDetail, stats)
2. Connect driver app UNLOADING phase to backend `PATCH /arrivals/{id}/status {status: 'unloading'}`
3. Add energy iframe to ManagerDashboard.tsx
4. Verify all notification types display correctly

---

## 8. Files That Will Be Modified in Phase 2

### Backend
- `infrastructure/persistence/sql_models.py` — add `unloading` to appointment_status enum
- `application/schemas.py` — add `unloading` to AppointmentStatusEnum
- `infrastructure/messaging/kafka_decision_consumer.py` — fix infraction path (inbox + alert + driver notif)
- `application/use_cases/container_moved_handler.py` — auto-create visit on accept, driver notif
- `routes/arrivals.py` — allow `unloading` status in PATCH endpoint
- `routes/driver.py` — ensure driver can set `unloading` status
- `application/queries/arrival_queries.py` — include `unloading` in stats
- `scripts/triggers.sql` — update visit completion trigger if needed
- `scripts/simple_outbox_worker.py` — handle new event types if needed

### API Gateway
- `api_gateway/src/routers/arrivals.py` — pass through `unloading` status (should work if no enum validation)

### Frontend Web
- `pages/gate-operator/ArrivalsList.tsx` — add `unloading` status display
- `pages/gate-operator/ArrivalDetail.tsx` — add `unloading` label
- `pages/logistics-manager/ManagerDashboard.tsx` — add energy iframe
- `types/types.ts` — add `unloading` to `AppointmentStatusEnum`

### Driver App
- `services/drivers.ts` — add `startUnloading()` function that PATCHes status to `unloading`
- `screens/ActiveArrivalScreen.tsx` — connect UNLOADING phase to backend call
- `types/types.ts` — add `unloading` to `AppointmentStatusEnum`
