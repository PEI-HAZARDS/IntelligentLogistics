# Data Module Tests

## Structure

```
tests/
├── conftest.py                              # Shared fixtures (pg_session)
├── .venv/                                   # Test-only virtualenv (pip install -r requirements.txt)
│
├── unit/                                    # No running services required
│   ├── __init__.py
│   ├── test_decision_state_machine.py       # BR-43, BR-45, BR-46, BR-47
│   ├── test_decision_source_derivation.py   # BR-44 final_decision_source logic
│   ├── test_plate_validation.py             # BR-49 plate format validator
│   ├── test_auth_bcrypt.py                  # BR-39, BR-40, BR-41
│   ├── test_consensus_validation.py         # BR-18 confidence + origin checks
│   ├── test_redis_atomicity.py              # Redis INCR+EXPIRE pipeline, SETEX atomicity
│   ├── test_phase1_correctness.py           # Phase 1: UTC datetime, cache eviction, NULL version, hazmat 404
│   ├── test_phase2_auth.py                  # Phase 2: JWT verify/role, Redis session helpers
│   ├── test_pending_review_durability.py    # Phase 4: PD-01 durable pending_review handler
│   ├── test_phase5_outbox_consolidation.py  # Phase 5: DW-01/06/07 outbox consolidation
│   ├── test_phase6_read_path.py             # Phase 6: Redis→PG read path, stats Mongo-first
│   ├── test_phase7_decision_single_write.py # Phase 7: DW-03/04/08 — deleted deprecated functions
│   ├── test_phase8_uuidv7.py               # Phase 8: UUIDv7 event_id, hazmat inbox dedup
│   ├── test_phase9_mongo_hygiene.py         # Phase 9: TTL indexes, analytics collections declared
│   ├── test_phase10_infra_polish.py         # Phase 10: UoW retry, inbox SAVEPOINT, shift race
│   ├── test_phase11_dead_code.py            # Phase 11: deleted dead utilities
│   ├── test_phase12_query_hygiene.py        # Phase 12: query hygiene, dock/transport stats
│   └── test_phase13_validators.py           # Phase 13: plate + consensus validators
│
├── integration/                             # Structural tests — no live services required
│   ├── __init__.py
│   ├── test_container_moved_atomicity.py    # BR-27 UoW atomicity (mock-based)
│   ├── test_decision_accept_flow.py         # BR-46 structural guard
│   ├── test_appointment_row_lock.py         # BR-48 SELECT FOR UPDATE pattern
│   ├── test_mongo_unique_indexes.py         # BR-37 unique index declarations
│   ├── test_arrivals_read_fallback.py       # BR-29 Redis→PG two-tier + scale-up documentation
│   ├── test_arrival_state_enums.py          # BR-15, BR-16 enum coverage
│   ├── test_pg_constraints.py              # BR-01, BR-04, BR-07 – BR-10 FK/PK constraints
│   ├── test_pg_check_enums.py              # BR-11, BR-13, BR-14, BR-17 check constraints
│   ├── test_redis_ttl.py                   # BR-30 – BR-36 TTL constants
│   ├── test_appointment_defaults.py         # BR-42 ORM/schema defaults
│   ├── test_driver_vehicle_history.py       # BR-52 driver_vehicle model
│   └── test_phase3_schema.py               # Phase 3: BR-11/13/14/52, PD-01, session columns removed
│
├── test_appointment_commands_uow.py         # BR-23 – BR-26, BR-50 UoW command patterns
├── test_appointment_optimistic_concurrency.py  # BR-48 optimistic locking (version column)
├── test_arrival_id_no_orm_listener.py       # BR-20 arrival_id via SQL trigger (not ORM)
├── test_event_dedup_a3.py                   # BR-21 event_id dedup in decision route + consumer
├── test_manager_statistics_endpoints.py     # Manager dashboard statistics endpoints
├── test_outbox_worker_b1.py                 # Outbox worker projection structural guards
├── kafka_decision_consumer_unit_test.py     # DecisionCorrelator unit tests (mock Kafka)
└── test_integration.py                      # HTTP integration (requires all V_APP services running)
```

## Running Tests

All commands assume `cd src/V_APP/Data_Module` first.

```bash
# All tests — unit + structural integration, no running services needed
# tests/integration/ is a subdirectory of tests/ and is already included
# Verified: 498 passed, 49 deselected (live-service tests), 0 warnings
PYTHONPATH=. tests/.venv/bin/python -m pytest tests/ \
  --ignore=tests/kafka_decision_consumer_unit_test.py \
  --ignore=tests/test_integration.py -v

# Live-service integration tests — requires docker-compose up -d (PG + Mongo + Redis)
# Run from src/V_APP/Data_Module. Set env vars to match your .env file:
# Verified: 48 passed, 1 skipped, 0 failed
PYTHONPATH=. \
  POSTGRES_HOST=localhost POSTGRES_USER=pei_user POSTGRES_PASSWORD='peiHazards**' POSTGRES_DB=IntelligentLogistics \
  MONGO_URL="mongodb://pei_user:peiHazards**@localhost:27017" \
  REDIS_HOST=localhost \
  tests/.venv/bin/python -m pytest tests/ \
  --ignore=tests/kafka_decision_consumer_unit_test.py \
  --ignore=tests/test_integration.py \
  -m integration --override-ini="addopts=" -v

# Structural integration tests only (subset of the command above — no live services needed)
# Verified: 65 passed, 49 deselected, 0 warnings
PYTHONPATH=. tests/.venv/bin/python -m pytest tests/integration/ -v

# Kafka consumer unit tests — mock-based, no services
PYTHONPATH=. tests/.venv/bin/python -m pytest tests/kafka_decision_consumer_unit_test.py -v

# HTTP integration suite — requires all V_APP services (docker-compose up -d in src/V_APP)
PYTHONPATH=. tests/.venv/bin/python -m pytest tests/test_integration.py -v

# Single test
PYTHONPATH=. tests/.venv/bin/python -m pytest \
  tests/unit/test_decision_state_machine.py::test_accepted_decision_transitions_to_in_process -v

# With coverage
PYTHONPATH=. tests/.venv/bin/python -m pytest tests/ \
  --ignore=tests/kafka_decision_consumer_unit_test.py \
  --ignore=tests/test_integration.py \
  --cov=. --cov-report=term -v
```

> **Note on test venv**: `tests/.venv` requires `psycopg2-binary` and `pymongo` for live-service
> tests. Install once: `tests/.venv/bin/pip install psycopg2-binary pymongo`

## Fixtures (`conftest.py`)

| Fixture | Scope | Description |
|---------|-------|-------------|
| `pg_session` | function | Transactional SQLAlchemy session; rolls back after each test |

## Markers

| Marker | Meaning |
|--------|---------|
| `@pytest.mark.integration` | Requires running PostgreSQL + MongoDB + Redis |
| `@pytest.mark.xfail(strict=True)` | Documents a known gap; must continue to fail |

## Coverage Summary

| Status | BR count |
|--------|----------|
| Covered (structural/unit/integration) | 39 |
| HTTP only | 4 |
| xfail gap documented | 0 |
| No test | 7 |
| N/A | 2 |

Full rule-by-rule table: [`code_documentation/V_APP/Data_Module/TEST_COVERAGE_MAP.md`](../../../code_documentation/V_APP/Data_Module/TEST_COVERAGE_MAP.md)

## Environment Variables for Tests

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_URL` | `postgresql://porto:porto@localhost:5432/porto_logistica` | PG connection for `pg_session` fixture |
| `MONGO_URL` | `mongodb://localhost:27017` | Mongo connection for integration tests |
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |

## Adding New Tests

- **Unit tests** (no services): place in `tests/unit/`, use `_FakeUoW` pattern from `test_decision_state_machine.py`.
- **Structural tests** (source inspection): read source as text via `pathlib.Path.read_text()`; import nothing that would trigger DB connections. No marker needed.
- **Integration tests**: decorate with `@pytest.mark.integration`; use the `pg_session` fixture for PG; create a module-scoped Mongo/Redis fixture that cleans up after itself.
- **Gap documentation**: use `@pytest.mark.xfail(strict=True, reason="BR-XX gap: ...")` to track missing implementation without failing CI.
