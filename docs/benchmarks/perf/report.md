# Performance Benchmark Report — Data Module & API Gateway

> **Status**: template — fill in after running load tests.

## Test environment

| Parameter | Value |
|-----------|-------|
| Date | |
| Host (server) | |
| Host (load generator) | |
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

## Data Module results (`load_test.py`, -u 50 -r 5 --run-time 5m)

| Endpoint | Requests | p50 | p95 | p99 | RPS | Errors |
|----------|----------|-----|-----|-----|-----|--------|
| /arrivals (default) | | | | | | |
| /arrivals?status=in_transit | | | | | | |
| /arrivals/:id | | | | | | |
| /arrivals/stats (Redis TTL) | | | | | | |
| /alerts/active (Redis TTL) | | | | | | |
| /statistics/summary (Mongo) | | | | | | |
| /decisions/detection-event | | | | | | |
| **Total** | | | | | | |

## API Gateway results (`load_test.py`, -u 30 -r 3 --run-time 5m)

| Endpoint | Requests | p50 | p95 | p99 | RPS | Errors |
|----------|----------|-----|-----|-----|-----|--------|
| /auth/workers/login | | | | | | |
| /arrivals (list) | | | | | | |
| /arrivals/:id | | | | | | |
| /alerts/active | | | | | | |
| /statistics/summary | | | | | | |
| /statistics/pipeline/performance | | | | | | |
| **Total** | | | | | | |

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
