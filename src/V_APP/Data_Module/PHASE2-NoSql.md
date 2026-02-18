# Phase 2: NoSQL Data Layer

## Overview

Phase 2 uses polyglot persistence with three complementary databases:

- **PostgreSQL**: single source of truth for transactional data (ACID)
- **MongoDB**: event store for auditing and analytics
- **Redis**: high-performance cache and real-time counters

This enables end-to-end truck journey tracking, real-time metrics, and fast reads.

## What Is Implemented

### MongoDB (Event Store)

Main collections:
- `agent_detections` for per-agent detections (AgentA/B/C)
- `decision_events` for the full decision journey
- `statistics_hourly` for pre-aggregated metrics

Legacy collections remain for backward compatibility.

### Redis (Cache + Counters)

Main patterns:
- Dedup keys for repeated detections
- Decision cache for fast replays
- Hot appointment cache
- License plate lookup cache
- Real-time counters for dashboards

### PostgreSQL (Transactional)

Appointments, drivers, trucks, alerts, and visits remain the source of truth.

## Processing Flow (Simplified)

```
Detection -> Redis dedup -> PostgreSQL update -> MongoDB event -> Redis cache/counters
```

## Key API Endpoints

- `GET /api/v1/statistics/realtime/{gate_id}`
- `GET /api/v1/statistics/pipeline/performance?gate_id=1&hours=24`
- `GET /api/v1/statistics/truck/{truck_id}/journey`
- `GET /api/v1/statistics/dashboard/summary?gate_id=1`

## Expected Performance

| Operation | Target |
|----------|--------|
| Cache read | <50ms |
| MongoDB aggregation | <200ms |
| Real-time counters | <10ms |

**Edge-case note:** under very high concurrency, `arrival_id` generation should be monitored and validated in the future to avoid collisions.

## Why This Works Well

- PostgreSQL keeps data integrity
- MongoDB preserves a full audit trail
- Redis provides low-latency reads

The result is a fast, observable, and scalable data layer for Phase 2.
