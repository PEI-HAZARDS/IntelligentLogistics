# TEST COVERAGE MAP — Data Module

> Business rule coverage status for all 52 BR IDs extracted from `docs/bd/`. Updated as of 2026-05-09. Test count: **512 unit / 61 integration** (0 failures).

Legend — **Covered**: rule directly verified at the right layer. **Arch**: structural source inspection confirms the mechanism. **HTTP**: exercised only via `test_integration.py` HTTP calls. **No test**: not covered.

---

## Coverage Table

| ID | Rule (one sentence) | Status | Test file | Gap |
|----|---------------------|--------|-----------|-----|
| BR-01 | `company.nif` UNIQUE (PK). | Arch + Integration | `test_pg_constraints.py` | — |
| BR-02 | `driver.drivers_license` PK. | HTTP | `test_integration.py` | HTTP only |
| BR-03 | `truck.license_plate` PK. | No | — | No test |
| BR-04 | `worker.email` UNIQUE. | Arch + Integration | `test_pg_constraints.py` | — |
| BR-05 | `manager.num_worker` PK+FK. | No | — | No test |
| BR-06 | `operator.num_worker` PK+FK. | No | — | No test |
| BR-07 | `driver.company_nif` FK → company. | Arch + Integration | `test_pg_constraints.py` | — |
| BR-08 | appointment FKs to truck, cargo, dock, shift, gate. | Arch + Integration | `test_pg_constraints.py` | — |
| BR-09 | Appointment: 1 entry gate, 0..1 exit gate. | Arch | `test_pg_constraints.py` | — |
| BR-10 | Detection 1:1 with appointment. | xfail (gap) | `test_pg_constraints.py` | No PG detection table |
| BR-11 | `alert.severity` INT 1–5. | Arch + Integration | `test_pg_check_enums.py`, `test_phase3_schema.py` | — |
| BR-12 | `cargo.adr` boolean. | No | — | No test |
| BR-13 | `dock.estado` ∈ {Ativo, Inativo}. | Arch + Integration | `test_pg_check_enums.py`, `test_phase3_schema.py` | — |
| BR-14 | `gate.estado` ∈ {Ativo, Inativo}. | Arch + Integration | `test_pg_check_enums.py`, `test_phase3_schema.py` | — |
| BR-15 | `appointment.status` enum. | Arch + Domain | `test_arrival_state_enums.py` | — |
| BR-16 | `visit.state` enum. | Arch + Domain | `test_arrival_state_enums.py` | — |
| BR-17 | `detection.origem` ∈ {IA, Manual}. | xfail (gap) | `test_pg_check_enums.py` | Detections in Mongo only (by design) |
| BR-18 | Consensus: confidence/origin validation. | Unit | `test_phase13_validators.py`, `test_consensus_validation.py` | — |
| BR-19 | UTF-8, SERIAL/UUID PKs. | N/A | — | Not testable |
| BR-20 | `arrival_id` via trigger; `version` column. | Arch | `test_arrival_id_no_orm_listener.py` | — |
| BR-21 | `inbox_events.event_id` UNIQUE → idempotent dedup. | Integration | `test_inbox_state_machine.py` | — |
| BR-22 | Inbox state machine RECEIVED→…→DEAD_LETTER. | Integration | `test_inbox_state_machine.py` | — |
| BR-23 | Outbox state machine PENDING→…→DEAD_LETTER. | Arch | `test_appointment_commands_uow.py` | — |
| BR-24 | Outbox worker: 2s poll, 2^n backoff ≤60s, 5 retries. | Arch | `test_appointment_commands_uow.py` | — |
| BR-25 | Permanent errors skip retries → DEAD_LETTER. | Arch | `test_appointment_commands_uow.py` | — |
| BR-26 | Domain state + outbox in same PG tx. | Arch | `test_appointment_commands_uow.py` | — |
| BR-27 | Kafka offset committed only after PG UoW commit. | Unit + Arch | `test_container_moved_atomicity.py` | — |
| BR-28 | Read endpoints fall back to PG on cache miss. | HTTP | `test_integration.py` | HTTP only |
| BR-29 | `GET /arrivals/{id}` Redis→Mongo→PG fallback. | Arch + xfail (gap) | `test_arrivals_read_fallback.py` | Mongo tier missing |
| BR-30 | `dedup:event:{id}` TTL 300s, SET NX. | Arch | `test_redis_ttl.py` | — |
| BR-31 | `plate:…:tb:…` dedup TTL 300s. | Arch + Integration | `test_redis_ttl.py` | — |
| BR-32 | `decision:plate:…` TTL 3600s. | Arch + Integration | `test_redis_ttl.py` | — |
| BR-33 | `appointment:{id}:details` TTL 1800s. | Arch + Integration | `test_redis_ttl.py` | — |
| BR-34 | `lp_lookup:…` TTL 600s. | Arch + Integration | `test_redis_ttl.py` | — |
| BR-35 | `counter:gate:…` TTL 7200s, INCRBY. | Arch + Integration | `test_redis_ttl.py` | — |
| BR-36 | `pending_review:{event_id}` TTL 1800s. | Arch + Integration | `test_redis_ttl.py`, `test_pending_review_durability.py` | Key changed from `truck_id` to `event_id` (Phase 4) |
| BR-37 | `decision_events.truck_id` UNIQUE. | xfail (gap) | `test_mongo_unique_indexes.py` | Non-unique by design; spec clarification needed |
| BR-38 | `appointments_read.appointment_id` UNIQUE. | Arch (partial) | `test_phase9_mongo_hygiene.py` | Index exists; outbox projection not yet writing to collection |
| BR-39 | Worker auth: email + bcrypt. | Unit | `test_auth_bcrypt.py` | — |
| BR-40 | Driver auth: licence + password; PIN claim. | Unit | `test_auth_bcrypt.py` | — |
| BR-41 | `DEBUG_MODE=true` bypasses sequential delivery check. | Unit | `test_auth_bcrypt.py` | — |
| BR-42 | `appointment.highway_infraction` BOOL DEFAULT FALSE. | Arch | `test_appointment_defaults.py` | — |
| BR-43 | Agent decision ∈ {ACCEPTED, REJECTED, MANUAL_REVIEW}. | Unit | `test_decision_state_machine.py` | — |
| BR-44 | `final_decision_source` = agent \| operator. | Arch + Unit | `test_decision_source_derivation.py` | — |
| BR-45 | ACCEPTED → appointment `IN_PROCESS`. | Unit | `test_decision_state_machine.py` | — |
| BR-46 | MANUAL_REVIEW → IN_PROCESS only after operator decision. | Unit + Arch | `test_decision_state_machine.py`, `test_decision_accept_flow.py` | — |
| BR-47 | REJECTED → no status change, alert created. | Unit | `test_decision_state_machine.py` | — |
| BR-48 | Command handler acquires `SELECT FOR UPDATE`. | Arch + Integration | `test_appointment_row_lock.py` | — |
| BR-49 | Plate format AA-00-BB. | Unit + Arch | `test_phase13_validators.py`, `test_plate_validation.py` | — |
| BR-50 | Outbox worker batch size 50. | Arch | `test_appointment_commands_uow.py` | — |
| BR-51 | Relational model is 3NF. | N/A | — | Not testable |
| BR-52 | `Condutor_Veiculo` temporal history. | Arch + Integration | `test_driver_vehicle_history.py`, `test_phase3_schema.py` | — |

---

## Summary

| Status | Count |
|--------|-------|
| Covered (Arch / Unit / Integration) | 39 |
| HTTP only (needs direct layer test) | 4 |
| xfail (gap documented — by design or spec pending) | 4 |
| No test | 3 |
| N/A (not testable) | 2 |
| **Total** | **52** |

---

## Test Files Index

| File | Layer | BRs / areas covered |
|------|-------|---------------------|
| `tests/integration/test_inbox_state_machine.py` | Integration | BR-21, BR-22 |
| `tests/integration/test_container_moved_atomicity.py` | Unit + Arch | BR-27 |
| `tests/unit/test_decision_state_machine.py` | Unit | BR-43, BR-45, BR-46, BR-47 |
| `tests/integration/test_decision_accept_flow.py` | Arch | BR-46 |
| `tests/integration/test_appointment_row_lock.py` | Arch + Integration | BR-48 |
| `tests/integration/test_mongo_unique_indexes.py` | Arch + Integration | BR-37 |
| `tests/integration/test_arrivals_read_fallback.py` | Arch + Integration | BR-29 |
| `tests/unit/test_plate_validation.py` | Unit | BR-49 (strict validator) |
| `tests/unit/test_decision_source_derivation.py` | Arch + Unit | BR-44 |
| `tests/integration/test_arrival_state_enums.py` | Arch + Domain | BR-15, BR-16 |
| `tests/integration/test_pg_constraints.py` | Arch + Integration | BR-01, BR-04, BR-07, BR-08, BR-09 |
| `tests/integration/test_pg_check_enums.py` | Arch + Integration | BR-11, BR-13, BR-14, BR-17 |
| `tests/integration/test_redis_ttl.py` | Arch + Integration | BR-30–36 |
| `tests/unit/test_auth_bcrypt.py` | Unit | BR-39, BR-40, BR-41 |
| `tests/integration/test_appointment_defaults.py` | Arch | BR-42 |
| `tests/integration/test_driver_vehicle_history.py` | Arch + Integration | BR-52 |
| `tests/unit/test_consensus_validation.py` | Unit | BR-18 |
| `tests/test_appointment_commands_uow.py` | Arch + Unit | BR-23–26, BR-50 |
| `tests/test_arrival_id_no_orm_listener.py` | Arch | BR-20 |
| `tests/test_integration.py` | HTTP Integration | BR-02, BR-15, BR-16, BR-28, BR-39–42 |
| `tests/kafka_decision_consumer_unit_test.py` | Unit | BR-43, BR-44 (correlator layer) |
| `tests/integration/test_phase3_schema.py` | Arch + Integration | BR-11, BR-13, BR-14, BR-52, PD-01 table |
| `tests/unit/test_pending_review_durability.py` | Unit + Arch | PD-01, BR-36 |
| `tests/unit/test_phase1_correctness.py` | Unit | UTC fixes, cache fallback, hazmat 404 |
| `tests/unit/test_phase2_auth.py` | Unit | JWT, X-Service-Key, session Redis helpers |
| `tests/unit/test_phase5_outbox_consolidation.py` | Arch | DW-01, DW-02, DW-06, DW-07 |
| `tests/unit/test_phase6_read_path.py` | Arch | BR-29, three-tier structure |
| `tests/unit/test_phase7_decision_single_write.py` | Arch | DW-03, DW-04, DW-08, PD-02 |
| `tests/unit/test_phase8_uuidv7.py` | Unit | UUIDv7 generation, format, inbox dedup |
| `tests/unit/test_phase9_mongo_hygiene.py` | Arch | TTL indexes, removed cache_metadata, BR-38 index |
| `tests/unit/test_phase10_infra_polish.py` | Unit + Arch | UoW retry, SAVEPOINT inbox, shift race, DLQ forwarding |
| `tests/unit/test_phase11_dead_code.py` | Arch | rate_limit removed, cache_detection removed, deprecated events |
| `tests/unit/test_phase12_query_hygiene.py` | Arch + Unit | FULL OUTER JOIN, dock_bay_number, transport-stats canonical |
| `tests/unit/test_phase13_validators.py` | Unit + Arch | BR-49 relaxed, BR-18 consensus, wiring checks |
| `tests/unit/test_redis_atomicity.py` | Unit | Redis pipeline atomicity |
| `tests/test_event_dedup_a3.py` | Unit + Arch | `is_duplicate_and_mark` legacy removal, event-id dedup |
| `tests/test_outbox_worker_b1.py` | Arch | outbox worker projection logic |
| `tests/test_manager_statistics_endpoints.py` | Unit + Arch | manager stats queries |
| `tests/load_test.py` | Load (Locust) | Polyglot persistence paths under concurrent load — see table below |

---

## Load Tests (`tests/load_test.py`)

Requires Locust (`pip install locust>=2.24.0` or `tests/requirements-load-test.txt`). Targets a running stack; not part of the CI unit suite.

```bash
tests/load-venv/bin/locust -f tests/load_test.py \
  --host=http://<host>:8080 \
  --headless -u 20 -r 2 --run-time 60s
```

| User class | Weight | Store path exercised |
|---|---|---|
| `ReadHeavyUser` | — | PG paginated arrivals (default + status filters + virtual `delayed`/`unloading`) |
| | | PG single arrival by id |
| | | PG license-plate lookup |
| | | PG next arrivals by gate |
| | | Redis cache hit: `/arrivals/stats` (TTL key) |
| | | Redis cache hit: `/alerts/active?limit=50` (default limit) |
| | | Redis cache bypass: `/alerts/active?limit=10` (custom limit skips cache) |
| | | Redis miss → PG fallback: `/drivers/me/active` (unknown plate) |
| | | PG write + Outbox: `POST /decisions/detection-event` |
| `ManagerDashboardUser` | — | Mongo aggregation: `/statistics/summary` |
| | | Redis + Mongo: `/statistics/pipeline/performance` |
| | | Mongo read: `/decisions/events/decisions`, `/decisions/events/detections` |
| | | Redis TTL: `/alerts/stats` |

Baseline results (VM `10.255.32.70`, 20 users, 60 s): **662 requests, 0 failures**, p95 ≤ 430 ms across all endpoints.
