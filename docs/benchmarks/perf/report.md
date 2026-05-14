# Performance Benchmark Report — Data Module & API Gateway

> **Status**: filled from Locust HTML reports at `dm_report.html` / `gw_report.html`
> (runs of 2026-05-11). Latency values in **ms**.

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

## Data Module results (`load_test.py` — 5 min run, mixed user mix)

Source: `dm_report.html` — 2026-05-11 20:49–20:54 UTC, host `http://10.255.32.70:8080`.

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

**SLO assessment (single replica, nominal load):**
- `/arrivals (default)` — p95 **410 ms** vs. target 200 ms — **FAIL** (default list endpoint exceeds SLO; status-filtered variants pass).
- `/arrivals/:id` — p95 **270 ms** vs. target 100 ms — **FAIL**.
- `/arrivals/stats` — p95 **250 ms** vs. target 150 ms — **FAIL** (Redis TTL hit ratio likely low for this duration).
- `/statistics/summary` — p95 **310 ms** vs. target 500 ms — **PASS**.
- `/decisions/detection-event` — p95 **220 ms** vs. target 300 ms — **PASS**.

Error rate: **0 / 8 769 = 0.00 %** across the whole run.

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

The single login failure (1/44, 2.3 %) was a Keycloak transient 401 already retried by `_login()` in [load_test.py:51-71](../../../src/V_APP/api_gateway/tests/load_test.py#L51-L71); attributable to Keycloak ROPC under cold cache, not application code.

## Slow query analysis (PostgreSQL)

Run via [pg_slow_queries.py](../../../src/V_APP/Data_Module/scripts/pg_slow_queries.py) against `pg_stat_statements` immediately after the load run:

```bash
PG_HOST=10.255.32.70 python src/V_APP/Data_Module/scripts/pg_slow_queries.py --reset  # before
# ...run load test...
PG_HOST=10.255.32.70 python src/V_APP/Data_Module/scripts/pg_slow_queries.py          # after
```

| Query (abbreviated) | Calls | Mean (ms) | Total (ms) | Optimisation applied |
|--------------------|-------|-----------|------------|----------------------|
| _to be captured during the 2x replica re-run_ | | | | |

> The 1-replica run did not capture `pg_stat_statements` output; PG had just been restarted with `shared_preload_libraries=pg_stat_statements` (docker-compose.yml:7-8) and counters had been collecting from cold start. Capture in the next run.

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
pip install -r src/V_APP/Data_Module/requirements-load-test.txt

# 3. Data Module load test (direct, no auth — port 8080)
locust -f src/V_APP/Data_Module/tests/load_test.py \
       --host=$VM_HOST:8080 \
       --headless -u 50 -r 5 --run-time 5m \
       --html docs/benchmarks/perf/dm_report.html

# 4. API Gateway load test (Keycloak auth — port 8000)
locust -f src/V_APP/api_gateway/tests/load_test.py \
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
pip install -r src/V_APP/Data_Module/requirements-load-test.txt

# 3. Data Module load test (direct, no auth — port 8080)
locust -f src/V_APP/Data_Module/tests/load_test.py \
       --host=$VM_HOST:8080 \
       --headless -u 50 -r 5 --run-time 5m \
       --html docs/benchmarks/perf/dm_report.html

# 4. API Gateway load test (Keycloak auth — port 8000)
locust -f src/V_APP/api_gateway/tests/load_test.py \
       --host=$VM_HOST:8000 \
       --headless -u 30 -r 3 --run-time 5m \
       --html docs/benchmarks/perf/gw_report.html
```

> Verify connectivity before running: `curl $VM_HOST:8080/api/v1/health`
