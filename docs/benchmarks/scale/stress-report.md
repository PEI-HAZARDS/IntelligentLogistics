# Scalability Stress Report — Data Module

> **Status**: template — fill in after running stress test.

## Objective

Force the system to its breaking point to identify the primary bottleneck and
demonstrate horizontal scale-out via Docker replica + Nginx upstream.

## Test environment

| Parameter | Value |
|-----------|-------|
| Date | |
| Host (server) | |
| Host (load generator) | |
| Network | local hotspot / LAN |
| Tool | Locust + StressRampShape |

## Ramp profile (`stress_test.py` — StressRampShape)

| Stage | Duration | Users | Spawn rate | Intent |
|-------|----------|-------|------------|--------|
| 1 | 0 – 60 s | 0 → 20 | 1 u/s | Warm-up |
| 2 | 60 – 120 s | 20 → 60 | 2 u/s | Normal load |
| 3 | 120 – 180 s | 60 → 120 | 3 u/s | High load |
| 4 | 180 – 240 s | 120 → 200 | 5 u/s | Stress zone |
| 5 | 240 – 360 s | 200 (hold) | — | Sustained — find knee |

## Results — single replica

| Users | RPS | p95 (ms) | Error rate | Notes |
|-------|-----|----------|------------|-------|
| 20 | | | | |
| 60 | | | | |
| 120 | | | | |
| 200 | | | | |

**Breaking point**: \_\_\_ concurrent users  
**First failure**: \_\_\_ (endpoint + error)  
**Bottleneck**: CPU / PG connection pool (`max_connections`) / Redis OOM / Mongo cursor timeout

Evidence (add screenshot or `docker stats` output):

```
CONTAINER           CPU %   MEM USAGE   NET I/O
dm_data_module      ___     ___         ___
dm_postgres         ___     ___         ___
dm_redis            ___     ___         ___
```

## Horizontal scale-out demo (2 replicas)

### Setup

```bash
# 1. Add Nginx upstream (load-balancer) config
cp src/V_APP/nginx-scale-demo.conf /tmp/nginx-dm.conf

# 2. Start Nginx container pointing to 2 data-module replicas
docker-compose up -d --scale data-module=2

# Option A — Nginx upstream (see nginx-scale-demo.conf)
docker run --rm -d --name nginx-dm \
  --network v_app_default \
  -p 9090:80 \
  -v /tmp/nginx-dm.conf:/etc/nginx/nginx.conf:ro \
  nginx:alpine

# 3. Re-run stress test against :9090 (Nginx → 2 replicas)
locust -f src/V_APP/Data_Module/tests/stress_test.py \
       --host=http://localhost:9090 \
       --headless --run-time 6m \
       --html docs/benchmarks/scale/stress_report_2x.html
```

### Results — two replicas

| Users | RPS | p95 (ms) | Error rate | Notes |
|-------|-----|----------|------------|-------|
| 20 | | | | |
| 60 | | | | |
| 120 | | | | |
| 200 | | | | |

**Throughput improvement**: \_\_\_ RPS → \_\_\_ RPS (≈ \_\_× improvement)  
**New bottleneck after scale-out**: (PG shared connection pool / Mongo / Redis)

## Architecture — what scales horizontally vs. vertically

| Component | Scale mode | How |
|-----------|-----------|-----|
| `data-module` (FastAPI) | Horizontal | `docker-compose up --scale data-module=N` + Nginx upstream |
| `api-gateway` (FastAPI) | Horizontal | same pattern |
| `decision-engine` | Horizontal | Kafka consumer group auto-rebalances partitions |
| `infraction-engine` | Horizontal | same |
| AI Agents (A/B/C) | Horizontal | `scale-up` Kafka topic → V_Brain spawns replicas |
| PostgreSQL | Vertical + read replicas | PG streaming replication (not deployed — described) |
| MongoDB | Horizontal (sharding/replica set) | Mongo replica set (not deployed — described) |
| Redis | Vertical | Redis Cluster for HA (not deployed — described) |
| Kafka (KRaft) | Horizontal | add brokers + rebalance (not deployed — described) |

## Key findings

- Stateless services (gateways, engines) scale horizontally with no code changes.
- Shared state (PG, Mongo, Redis) is the ceiling — shared `max_connections` across replicas is the first limit observed.
- Auto-scaling of AI agents via Kafka topics already implemented and functional (see V_Brain `scale-up`/`scale-down` topics).

## How to reproduce

The load generator runs locally; the V_APP stack runs on the remote VM.
Set the VM host once and reuse it across all commands:

```bash
export VM_HOST=http://<vm-ip>   # e.g. http://10.x.x.x
```

```bash
# 1. Single replica stress test
locust -f src/V_APP/Data_Module/tests/stress_test.py \
       --host=$VM_HOST:8080 \
       --headless --run-time 6m \
       --html docs/benchmarks/scale/stress_report_1x.html

# 2. Scale out to 2 replicas (run on the VM)
docker-compose -f src/V_APP/docker-compose.yml up -d --scale data-module=2

docker run --rm -d --name nginx-dm \
  --network v_app_default \
  -p 9090:80 \
  -v $(pwd)/src/V_APP/nginx-scale-demo.conf:/etc/nginx/nginx.conf:ro \
  nginx:alpine

# 3. Two replica stress test (via Nginx on port 9090)
locust -f src/V_APP/Data_Module/tests/stress_test.py \
       --host=$VM_HOST:9090 \
       --headless --run-time 6m \
       --html docs/benchmarks/scale/stress_report_2x.html
```

> Monitor on the VM during the run:
> ```bash
> docker stats --no-stream
> watch -n2 'psql -U porto -d porto_logistica -c "SELECT count(*) FROM pg_stat_activity;"'
> ```
