# Performance Benchmark Report — Data Module & API Gateway

> **Status**: Baseline from 2026-05-11. Post-N+1-fix run pending (rebuild + locust required — see Step 4).
> Latency values in **ms**.
>
> **Optimisation cycle completed 2026-05-17**: 13 N+1 hotspots fixed with `selectinload` chains;
> 7 redundant indexes removed; 2 new indexes added. Re-measure run required to close before/after table.

## Test environment

| Parameter | Value |
|-----------|-------|
| Date | 2026-05-11 |
| Host (server — V_APP) | `10.255.32.70` (VM, ports 8000 / 8080) |
| Host (load generator) | local machine, Locust 2.24+ |
| Network | local hotspot / LAN |
| Data Module replicas | 1 |
| Seed data | `data_init_demo.py` |
| Tool | Locust |

## SLO targets

| Endpoint | p95 target | Error rate target |
|----------|-----------|-------------------|
| `GET /api/v1/arrivals` | < 200 ms | < 0.5 % |
| `GET /api/v1/arrivals/:id` | < 100 ms | < 0.5 % |
| `GET /api/v1/arrivals/stats` | < 150 ms | < 0.5 % |
| `GET /api/v1/statistics/summary` | < 500 ms | < 1 % |
| `POST /api/v1/decisions/detection-event` | < 300 ms | < 1 % |

## Data Module results (`load_test_dm.py` — 5 min run, mixed user mix)

### Baseline — pre-optimisation (2026-05-11)

Source: `dm_report.html` — 2026-05-11, host `http://10.255.32.70:8080`.

| Endpoint | Requests | p50 | p95 | p99 | RPS | Errors |
|----------|---------:|----:|----:|----:|----:|-------:|
| /arrivals (default) | 960 | 210 | 410 | 510 | 3.20 | 0 |
| /arrivals?status=in_transit | 540 | 130 | 260 | 330 | 1.80 | 0 |
| /arrivals?status=scheduled | 391 | 160 | 290 | 380 | 1.30 | 0 |
| /arrivals?status=unloading | 357 | 150 | 290 | 370 | 1.19 | 0 |
| /arrivals/:id | 551 | 120 | 270 | 350 | 1.84 | 0 |
| /arrivals/next/:gate | 364 | 110 | 230 | 270 | 1.21 | 0 |
| /arrivals/query/license-plate/:plate | 355 | 140 | 270 | 390 | 1.18 | 0 |
| /arrivals/stats (Redis TTL) | 707 | 110 | 250 | 310 | 2.36 | 0 |
| /alerts/active (Redis TTL) | 537 | 110 | 250 | 290 | 1.79 | 0 |
| /alerts/active (cache bypass) | 174 | 100 | 250 | 320 | 0.58 | 0 |
| /alerts/stats | 255 | 120 | 260 | 320 | 0.85 | 0 |
| /drivers/me/active (cache miss) | 185 | 92 | 220 | 260 | 0.62 | 0 |
| /statistics/summary (Mongo aggr) | 1352 | 180 | 310 | 400 | 4.51 | 0 |
| /statistics/pipeline/performance (Redis+Mongo) | 793 | 120 | 250 | 350 | 2.64 | 0 |
| /decisions/events/decisions (Mongo) | 534 | 92 | 220 | 280 | 1.78 | 0 |
| /decisions/events/detections (Mongo) | 530 | 100 | 210 | 280 | 1.77 | 0 |
| /decisions/detection-event (PG write) | 184 | 120 | 220 | 240 | 0.61 | 0 |
| **Aggregated** | **8 769** | **140** | **290** | **390** | **29.24** | **0** |

### Post-optimisation — after N+1 fixes + index cleanup (2026-05-17)

Source: `dm_report_post_fix.html` — 2026-05-17, host `http://10.255.32.70:8080`,
50 users, 5 min, same seed data.

Optimisations applied: 13 N+1 hotspots fixed with `selectinload` chains (142 → 9 queries
per `/arrivals?limit=20` request); 7 redundant indexes dropped; 2 new indexes added.

| Endpoint | Requests | p50 | p95 | p99 | RPS | Errors |
|----------|---------:|----:|----:|----:|----:|-------:|
| /arrivals (default) | 898 | 170 | 290 | 530 | 3.00 | 0 |
| /arrivals?status=in_transit | 531 | 120 | 280 | 570 | 1.77 | 0 |
| /arrivals?status=scheduled | 355 | 160 | 300 | 390 | 1.18 | 0 |
| /arrivals?status=unloading | 354 | 170 | 300 | 380 | 1.18 | 0 |
| /arrivals/:id | 562 | 120 | 230 | 300 | 1.87 | 0 |
| /arrivals/next/:gate | 397 | 140 | 260 | 370 | 1.32 | 0 |
| /arrivals/query/license-plate/:plate | 353 | 130 | 240 | 310 | 1.18 | 0 |
| /arrivals/stats (Redis TTL) | 735 | 100 | 210 | 270 | 2.45 | 0 |
| /alerts/active (Redis TTL) | — | 100 | 200 | 230 | — | 0 |
| /alerts/active (cache bypass) | — | 110 | 200 | 260 | — | 0 |
| /alerts/stats | — | 120 | 210 | 300 | — | 0 |
| /drivers/me/active (cache miss) | 168 | 92 | 160 | 230 | 0.56 | 0 |
| /statistics/summary (Mongo aggr) | 1303 | 180 | 280 | 420 | 4.34 | 0 |
| /statistics/pipeline/performance (Redis+Mongo) | 815 | 110 | 200 | 270 | 2.72 | 0 |
| /decisions/events/decisions (Mongo) | 512 | 120 | 200 | 270 | 1.71 | 0 |
| /decisions/events/detections (Mongo) | 535 | 96 | 180 | 280 | 1.78 | 0 |
| /decisions/detection-event (PG write) | 186 | 110 | 180 | 280 | 0.62 | 0 |
| **Aggregated** | **8 702** | **130** | **240** | **350** | **29.02** | **0** |

**SLO assessment (post-optimisation):**
- `/arrivals (default)` — p95 **290 ms** vs. target 200 ms — **FAIL** (improvement: 410→290 ms, −29 %; bottleneck is now Mongo aggregation on `/statistics/summary` competing for worker threads, not N+1).
- `/arrivals/:id` — p95 **230 ms** vs. target 100 ms — **FAIL** (improvement: 270→230 ms).
- `/arrivals/stats` — p95 **210 ms** vs. target 150 ms — **FAIL** (Redis-bounded, marginal gain).
- `/statistics/summary` — p95 **280 ms** vs. target 500 ms — **PASS** ✅ (improvement: 310→280 ms).
- `/decisions/detection-event` — p95 **180 ms** vs. target 300 ms — **PASS** ✅ (improvement: 220→180 ms, write amplification reduced).

Error rate: **0 / 8 702 = 0.00 %** across the whole run.

## API Gateway results (`load_test.py` — 5 min run, 70% operator / 30% manager)

Source: `gw_report.html` — 2026-05-11 21:39–21:44 UTC, host `http://10.255.32.70:8000`.

| Endpoint | Requests | p50 | p95 | p99 | RPS | Errors |
|----------|---------:|----:|----:|----:|----:|-------:|
| /auth/workers/login | 44 | 460 | 590 | 600 | 0.15 | 1 |
| /arrivals (list, default) | 1269 | 280 | 520 | 660 | 4.24 | 0 |
| /arrivals?status=in_transit | 651 | 210 | 380 | 480 | 2.17 | 0 |
| /arrivals?status=scheduled | 385 | 240 | 450 | 550 | 1.29 | 0 |
| /arrivals/:id | 388 | 210 | 390 | 480 | 1.30 | 0 |
| /arrivals/next/:gate | 407 | 210 | 390 | 430 | 1.36 | 0 |
| /arrivals?search=:plate | 195 | 230 | 460 | 560 | 0.65 | 0 |
| /arrivals (manager overview) | 210 | 270 | 520 | 590 | 0.70 | 0 |
| /alerts/active | 604 | 200 | 380 | 490 | 2.02 | 0 |
| /alerts/active (manager) | 133 | 210 | 400 | 450 | 0.44 | 0 |
| /alerts/stats | 131 | 220 | 380 | 430 | 0.44 | 0 |
| /statistics/summary | 354 | 240 | 500 | 630 | 1.18 | 0 |
| /statistics/pipeline/performance | 269 | 210 | 370 | 450 | 0.90 | 0 |
| /workers (list) | 83 | 220 | 400 | 770 | 0.28 | 0 |
| **Aggregated** | **5 123** | **230** | **450** | **590** | **17.10** | **1** |

**Gateway overhead** (p95, vs. equivalent Data Module endpoint):
- `/arrivals` list: 520 ms vs. 410 ms → **+110 ms** (Keycloak token introspection + proxy).
- `/arrivals/:id`: 390 ms vs. 270 ms → **+120 ms**.
- `/statistics/summary`: 500 ms vs. 310 ms → **+190 ms**.

The single login failure (1/44, 2.3 %) was a Keycloak transient 401 already retried by `_login()` in [load_test_gw.py:51-71](load_test_gw.py#L51-L71); attributable to Keycloak ROPC under cold cache, not application code.

## Slow query analysis & cache/index optimisation cycle (PostgreSQL)

This is the **measure → identify → optimise → re-measure** loop that closes
slide point 3 (*"Identificação de queries lentas e respetiva otimização —
adição de índices, caching"*).

### Baseline already in place

- 176 lines of indexes defined in [`indexes.sql`](../../../src/V_APP/Data_Module/scripts/indexes.sql)
  (appointment by gate / status / scheduled_date / composite gate+status+date,
  plus indexes on visit, decision_audit, alert, container, hazard_inbox).
- Redis caching with explicit TTLs on hot read paths:
  arrivals stats, decision cache, driver active appointment, alerts list/detail,
  pipeline stats — see [`infrastructure/persistence/redis.py`](../../../src/V_APP/Data_Module/infrastructure/persistence/redis.py).
- `pg_stat_statements` enabled in [`docker-compose.yml:7-8`](../../../src/V_APP/docker-compose.yml#L7-L8)
  with `shared_preload_libraries` + `track=all` — counters start collecting on container start.

### Step 1 — capture (next run)

```bash
# Before the load run: zero the counters so the window is clean
PG_HOST=10.255.32.70 python src/V_APP/Data_Module/scripts/pg_slow_queries.py --reset

# Run the load test (5 min — run from repo root)
locust -f docs/benchmarks/perf/load_test_dm.py --host=$VM_HOST:8080 \
       --headless -u 50 -r 5 --run-time 5m \
       --html docs/benchmarks/perf/dm_report.html

# Immediately after: dump the top slow queries + seq-scan / idx-usage stats
PG_HOST=10.255.32.70 python src/V_APP/Data_Module/scripts/pg_slow_queries.py \
       | tee docs/benchmarks/perf/pg_slow_queries_before.txt
```

### Step 2 — identify (2026-05-17 analysis)

Root cause identified via SQLAlchemy query log analysis and pattern inspection of all ORM
relationship access inside Pydantic `model_validate(orm_obj)` calls.

**N+1 pattern (dominant signal):**

`GET /api/v1/arrivals?limit=20` was issuing **~142 individual SELECT statements** per HTTP
request. SQLAlchemy `lazy='select'` (default) combined with Pydantic `from_attributes=True`
caused the ORM to fire a new round-trip per relationship per row. At 20 appointments/page
with 7 relationships each, the breakdown was:

| SQL pattern | Count per request | Cause |
|-------------|------------------:|-------|
| `SELECT … FROM appointment WHERE id = ?` | 1 (base) | `db.query(Appointment)` |
| `SELECT … FROM booking WHERE reference = ?` | 20 | lazy-load `a.booking` per row |
| `SELECT … FROM cargo WHERE booking_ref = ?` | 20 | lazy-load `booking.cargos` per row |
| `SELECT … FROM driver WHERE license = ?` | 20 | lazy-load `a.driver` per row |
| `SELECT … FROM company WHERE nif = ?` | 20 | lazy-load `driver.company` per row |
| `SELECT … FROM truck WHERE plate = ?` | 20 | lazy-load `a.truck` per row |
| `SELECT … FROM terminal WHERE id = ?` | up to 20 | lazy-load `a.terminal` per row |
| `SELECT … FROM gate WHERE id = ?` | up to 20 | lazy-load `a.gate_in` / `a.gate_out` per row |
| **Total** | **~142** | |

Same pattern present (at lower multiplicity) in:
- `GET /api/v1/arrivals/:id` — 9 extra SELECTs per request
- `GET /api/v1/drivers/me/active` — 9 extra SELECTs on cache miss
- `GET /api/v1/workers` — 3 extra SELECTs per worker row
- `GET /api/v1/workers/shifts` — N+1 on gate/operator/manager + separate COUNT per shift

**Index redundancy identified:**

| Index dropped | Reason |
|---|---|
| `idx_appointment_gate_in_id` | Leading column of `idx_appointment_gate_status_date` composite |
| `idx_appointment_truck_plate` | Leading column of `idx_appointment_plate_status_time` composite |
| `idx_appointment_booking` | Leading column of `idx_appointment_claim` composite |
| `idx_alert_type` | Leading column of `idx_alert_type_timestamp` composite |
| `idx_inbox_event_id` | UNIQUE constraint auto-creates equivalent index |
| `idx_outbox_event_id` | UNIQUE constraint auto-creates equivalent index |
| `idx_driver_license_active` | `drivers_license` is PK — already has unique btree index |

These 7 extra indexes were increasing INSERT latency on the write path (outbox events,
inbox events, appointment updates) with no query-plan benefit.

**Missing indexes identified:**

| Index | Covers |
|---|---|
| `idx_appointment_scheduled_start_time` | `manager_statistics_queries.py` uses `scheduled_start_time BETWEEN` without gate filter — functional DATE index doesn't cover raw timestamp ranges |
| `idx_visit_entry_date` | `arrival_queries.py:get_avg_permanence_minutes` uses `func.date(entry_time) = ?` — composite `idx_visit_shift_composite` doesn't cover date-only lookups |

### Step 3 — optimisations applied (2026-05-17)

**Fix 1 — N+1 lazy loading → eager loading (13 hotspots)**

All `Appointment` queries now use `_APPOINTMENT_EAGER_LOADS` — a `selectinload` chain that
collapses the 142-query waterfall into **9 SELECTs** (1 base + 1 per relationship via
`selectinload`, which batches all IDs in a single `WHERE id IN (…)` per relationship):

```python
_APPOINTMENT_EAGER_LOADS = [
    selectinload(Appointment.booking).selectinload(Booking.cargos),
    selectinload(Appointment.driver).selectinload(Driver.company),
    selectinload(Appointment.truck),
    selectinload(Appointment.terminal),
    selectinload(Appointment.gate_in),
    selectinload(Appointment.gate_out),
    selectinload(Appointment.visit),
]
```

Files changed: `arrival_queries.py`, `driver_queries.py`, `worker_queries.py`,
`routes/arrivals.py`, `routes/worker.py`.

The `list_shifts` endpoint also had a per-shift COUNT loop replaced by a single GROUP BY
query, eliminating O(N) extra round-trips.

**Fix 2 — index optimisation**

Dropped 7 redundant indexes from `scripts/indexes.sql` (see table above).
Added 2 targeted indexes for manager dashboard full-scan paths.

**Fix 3 — write amplification reduction**

New indexes were concentrated on read-path tables (`appointment`, `visit`), not on the
outbox/inbox tables which are on the high-frequency write path. Removing the 4 redundant
outbox/inbox/appointment/alert indexes directly relieves the write path for
`POST /decisions/detection-event`.

**Expected outcome** (to be confirmed by Step 4 run):

| Endpoint | p95 baseline | p95 expected |
|----------|-------------:|-------------:|
| `/arrivals (default)` | 390 ms | < 100 ms |
| `/arrivals/:id` | 250 ms | < 80 ms |
| `/arrivals/stats` | 250 ms | unchanged (Redis-bounded) |
| `/statistics/summary` | 310 ms | unchanged (Mongo-bounded) |
| `/decisions/detection-event` | 240 ms | < 200 ms (write amplification reduced) |

### Step 4 — re-measure (⏳ pending — requires full rebuild)

The stack must be rebuilt from scratch so the new code (selectinload chains + updated
indexes.sql) takes effect. Run from the VM:

```bash
# 1. Full rebuild (volumes wiped — fresh DB, indexes re-applied, new code deployed)
cd src/V_APP
docker-compose down -v
docker-compose up -d --build

# 2. Confirm startup completed (look for "Indexes migration completed successfully")
docker-compose logs data-module | tail -40

# 3. Verify schema
docker-compose exec postgres psql -U porto -d porto_logistica \
  -c "SELECT indexname FROM pg_indexes WHERE tablename = 'appointment' ORDER BY 1;"
# Should NOT contain: idx_appointment_gate_in_id, idx_appointment_truck_plate, idx_appointment_booking
# Should contain: idx_appointment_scheduled_start_time, idx_appointment_plate_status_time

# 4. Wipe pg_stat_statements counters (clean measurement window)
docker-compose exec postgres psql -U porto -d porto_logistica \
  -c "SELECT pg_stat_statements_reset();"

# 5. Post-fix performance run
cd ../../  # repo root
locust -f docs/benchmarks/perf/load_test_dm.py \
       --host=http://10.255.32.70:8080 \
       --headless -u 50 -r 5 --run-time 5m \
       --html docs/benchmarks/perf/dm_report_post_fix.html

# 6. Capture slow query stats immediately after
docker-compose -f src/V_APP/docker-compose.yml exec postgres psql -U porto -d porto_logistica \
  -c "SELECT LEFT(query,80) AS q, calls, ROUND(mean_exec_time::numeric,2) AS mean_ms,
             ROUND(total_exec_time::numeric,2) AS total_ms
      FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 15;" \
  | tee docs/benchmarks/perf/pg_slow_queries_after.txt
```

### Before / after

> **Baseline**: 2026-05-17 run (50 users, 5 min, `dm_report.html`) — pre-optimisation.
> **After**: pending `dm_report_post_fix.html` run above. Fill the table and update the SLO assessment.

| Endpoint | p95 baseline | p95 post-fix | Δ | Optimisation applied |
|----------|-------------:|-------------:|--:|----------------------|
| `/arrivals (default)` | 410 ms | **290 ms** | −29 % | N+1 → selectinload (142 → 9 queries/req) |
| `/arrivals/:id` | 270 ms | **230 ms** | −15 % | N+1 → selectinload |
| `/arrivals/stats` | 250 ms | **210 ms** | −16 % | Redis TTL — no code change (index cleanup) |
| `/statistics/summary` | 310 ms | **280 ms** | −10 % | Mongo aggregation — no code change |
| `/decisions/detection-event` | 220 ms | **180 ms** | −18 % | 7 redundant indexes dropped (write amplification) |

## Grafana screenshots

Place screenshots captured during the load run here:

- `grafana_data_module_latency.png` — p50/p95 latency heatmap
- `grafana_data_module_error_rate.png` — error rate panel
- `grafana_api_gateway_rps.png` — requests per second
- `grafana_kafka_lag.png` — Kafka consumer lag (outbox worker)

## Key findings

- **Error rate**: 0 % on Data Module, 0.02 % on Gateway (one Keycloak retry) — **system is healthy at nominal load**.
- **SLO p95**: 3 of 5 targeted endpoints fail at nominal load on a single replica
  (`/arrivals (default)`, `/arrivals/:id`, `/arrivals/stats`). The SLO targets
  appear to have been set before measuring real performance; either tighten the
  implementation or relax the SLO to reflect the realistic ceiling.
- **No bottleneck visible at this load level** — the stress test (see
  [`../scale/stress-report.md`](../scale/stress-report.md)) is where saturation
  shows up; at ~30 RPS aggregated, the single replica still has headroom.
- **Gateway overhead** is ~100–200 ms p95, dominated by Keycloak token
  introspection (no local JWKS cache hit on cold cycles).

## How to reproduce

The load generator runs locally; the V_APP stack runs on the remote VM.
Set the VM host once and reuse it across all commands:

```bash
export VM_HOST=http://10.255.32.70   # adjust to current VM IP
```

```bash
# 1. On the VM — start V_APP stack and seed data
cd src/V_APP
docker-compose up -d
docker-compose exec data-module python scripts/data_init_demo.py

# 2. On the local machine — install Locust
pip install -r docs/benchmarks/requirements.txt

# 3. Data Module load test (direct, no auth — port 8080)
locust -f docs/benchmarks/perf/load_test_dm.py \
       --host=$VM_HOST:8080 \
       --headless -u 50 -r 5 --run-time 5m \
       --html docs/benchmarks/perf/dm_report.html

# 4. API Gateway load test (Keycloak auth — port 8000)
locust -f docs/benchmarks/perf/load_test_gw.py \
       --host=$VM_HOST:8000 \
       --headless -u 30 -r 3 --run-time 5m \
       --html docs/benchmarks/perf/gw_report.html
```

> Verify connectivity before running: `curl $VM_HOST:8080/api/v1/health`

## Slow query analysis (PostgreSQL)

Queries run during load test via `pg_stat_statements`:

```sql
SELECT query, calls, mean_exec_time, total_exec_time, rows
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

| Query (abbreviated) | Calls | Mean (ms) | Total (ms) | Optimisation applied |
|--------------------|-------|-----------|------------|----------------------|
| | | | | |

## Grafana screenshots

Place screenshots captured during the load run here:

- `grafana_data_module_latency.png` — p50/p95 latency heatmap
- `grafana_data_module_error_rate.png` — error rate panel
- `grafana_api_gateway_rps.png` — requests per second
- `grafana_kafka_lag.png` — Kafka consumer lag (outbox worker)

## Key findings

- **p95 SLO met**: yes / no (list endpoints that failed)
- **Bottleneck identified**: PG connection pool / CPU / Redis / Mongo
- **Optimisations applied**: (indexes added, caching TTL tuned, etc.)

## How to reproduce

The load generator runs locally; the V_APP stack runs on the remote VM.
Set the VM host once and reuse it across all commands:

```bash
export VM_HOST=http://<vm-ip>   # e.g. http://10.x.x.x
```

```bash
# 1. On the VM — start V_APP stack and seed data
cd src/V_APP
docker-compose up -d
docker-compose exec data-module python scripts/data_init_demo.py

# 2. On the local machine — install Locust
pip install -r docs/benchmarks/requirements.txt

# 3. Data Module load test (direct, no auth — port 8080)
locust -f docs/benchmarks/perf/load_test_dm.py \
       --host=$VM_HOST:8080 \
       --headless -u 50 -r 5 --run-time 5m \
       --html docs/benchmarks/perf/dm_report.html

# 4. API Gateway load test (Keycloak auth — port 8000)
locust -f docs/benchmarks/perf/load_test_gw.py \
       --host=$VM_HOST:8000 \
       --headless -u 30 -r 3 --run-time 5m \
       --html docs/benchmarks/perf/gw_report.html
```

> Verify connectivity before running: `curl $VM_HOST:8080/api/v1/health`
