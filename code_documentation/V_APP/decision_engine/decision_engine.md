# `decision_engine.py`

> Implements the access-control decision logic that correlates LP and HZ Kafka events per truck and gate, then publishes a structured decision to V_Brain.

---

## Overview

This module is the concrete implementation of the gate-entry decision engine within the **V_APP**. It subscribes to per-gate `lp-results-{gate_id}` and `hz-results-{gate_id}` Kafka topics, waits until both a license-plate result and a hazard-plate result arrive for the same truck, and then evaluates whether the truck should be granted access.

The evaluation follows a strict priority chain: if the license plate was not detected, the appointment API is unreachable, no matching appointment is found, or the plate does not fuzzy-match any candidate, the outcome is `MANUAL_REVIEW`. Only a confirmed plate match against an active appointment yields `ACCEPTED`. A `SKIPPED` status is emitted when the same truck is re-detected before it has cleared the camera view, signalling V_Brain to reset rather than reprocess.

This class does **not** handle hazard-infraction logic (that is the responsibility of `InfractionEngine`) and does not manage WebSocket notifications (that is done by `APIGateway`). It acts purely as a stateless evaluation step between detection events and the V_Brain orchestrator, relying on `BaseDecisionEngine` for all buffering, lifecycle management, and shared helpers.

---

## Location
```
src/V_APP/decision_engine/src/decision_engine.py
```

## Dependencies

### Internal
| Module | Why it's used |
|--------|---------------|
| `V_APP/shared/src/base_decision_engine.py` | Abstract base class providing LP/HZ buffering, Kafka loop, and shared helpers |
| `shared/src/kafka_protocol.py` | `LicensePlateResultsMessage`, `HazardPlateResultsMessage`, `KafkaMessageProto`, `KafkaTopicFactory` |

### External
| Package | Version | Why it's used |
|---------|---------|---------------|
| `prometheus_client` | `*` | `Counter` metrics for decisions, approvals, and manual reviews |

---

## Architecture & Flow

```
[lp-results-{gate_id}]  ──┐
                           ├─→ BaseDecisionEngine (buffer) ─→ DecisionEngine._execute_logic
[hz-results-{gate_id}]  ──┘         (both present)                      │
                                                              ┌──────────▼──────────┐
                                                              │  DatabaseClient      │
                                                              │  (get_appointments)  │
                                                              └──────────┬──────────┘
                                                                         │
                                                              ┌──────────▼──────────┐
                                                              │  PlateMatcher        │
                                                              │  (fuzzy match)       │
                                                              └──────────┬──────────┘
                                                                         │
                                                         [agent-decision-{gate_id}] → V_Brain
```

---

## Classes

### `DecisionStatus`

> Enumeration of the three possible outcomes produced by the automated decision process.

**Inherits from:** `Enum`

**Constructor**
```python
# Standard enum — no direct instantiation
DecisionStatus.ACCEPTED       # "ACCEPTED"
DecisionStatus.MANUAL_REVIEW  # "MANUAL_REVIEW"
DecisionStatus.SKIPPED        # "SKIPPED"
```

| Member | Value | Description |
|--------|-------|-------------|
| `ACCEPTED` | `"ACCEPTED"` | Truck plate matched a confirmed appointment |
| `MANUAL_REVIEW` | `"MANUAL_REVIEW"` | Automated check failed; gate operator must decide |
| `SKIPPED` | `"SKIPPED"` | Same truck re-detected before leaving camera view |

---

### `DecisionEngineConfig`

> Configuration class for `DecisionEngine`; inherits all fields from `BaseDecisionEngineConfig` without additions.

**Inherits from:** `BaseDecisionEngineConfig` (Pydantic `BaseSettings`)

**Constructor**
```python
DecisionEngineConfig(
    kafka_bootstrap: str = "10.255.32.70:9092",
    decision_gate_ids: str = '["1"]',
    api_url: str = "http://localhost:8080/api/v1",
    time_tolerance_minutes: int = 30,
    max_levenshtein_distance: int = 2,
    expiration_time_hours: int = 24,
    un_numbers_file: str = "./data/un_numbers.txt",
    kemler_codes_file: str = "./data/kemler_codes.txt",
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `kafka_bootstrap` | `str` | `"10.255.32.70:9092"` | Kafka broker address |
| `gate_ids` | `str` | `'["1"]'` | Master JSON array of all gate IDs |
| `decision_gate_ids` | `str` | `'["1"]'` | JSON array of gate IDs this engine monitors |
| `infraction_gate_ids` | `str` | `'["1"]'` | JSON array for infraction engine (not used here) |
| `api_url` | `str` | `"http://localhost:8080/api/v1"` | Data Module base URL |
| `time_tolerance_minutes` | `int` | `30` | Appointment window tolerance |
| `max_levenshtein_distance` | `int` | `2` | Max edit distance for fuzzy plate matching |
| `expiration_time_hours` | `int` | `24` | Hours before a buffered LP/HZ message is dropped |
| `un_numbers_file` | `str` | `"./data/un_numbers.txt"` | Path to UN number lookup file |
| `kemler_codes_file` | `str` | `"./data/kemler_codes.txt"` | Path to Kemler code lookup file |

**Attributes**

Inherits `decision_gate_id_list`, `gate_id_list`, `infraction_gate_id_list` properties from `BaseDecisionEngineConfig` which parse the JSON string fields into `list[str]`.

---

### `DecisionEngine`

> Stateful service that correlates LP and HZ Kafka messages per gate and truck, evaluates access, and publishes the result.

**Inherits from:** `BaseDecisionEngine`

**Constructor**
```python
DecisionEngine(
    config: Optional[BaseDecisionEngineConfig] = None,
    kafka_producer: Optional[KafkaProducerWrapper] = None,
    kafka_consumer: Optional[KafkaConsumerWrapper] = None,
    plate_matcher: Optional[PlateMatcher] = None,
    database_client: Optional[DatabaseClient] = None,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `BaseDecisionEngineConfig` | `DecisionEngineConfig()` | Service configuration |
| `kafka_producer` | `KafkaProducerWrapper` | auto-created | Producer for `agent-decision-{gate_id}` |
| `kafka_consumer` | `KafkaConsumerWrapper` | auto-created | Consumer for LP and HZ topics |
| `plate_matcher` | `PlateMatcher` | `PlateMatcher()` | Fuzzy license-plate matcher |
| `database_client` | `DatabaseClient` | auto-created | HTTP client for the Data Module |

**Attributes**

Inherited from `BaseDecisionEngine`:

| Attribute | Type | Description |
|-----------|------|-------------|
| `running` | `bool` | Controls the main Kafka consume loop |
| `config` | `BaseDecisionEngineConfig` | Resolved configuration instance |
| `lp_buffer` | `dict[tuple[str,str], LicensePlateResultsMessage]` | Pending LP messages keyed by `(gate_id, truck_id)` |
| `hz_buffer` | `dict[tuple[str,str], HazardPlateResultsMessage]` | Pending HZ messages keyed by `(gate_id, truck_id)` |
| `last_truck_detected` | `dict[str, str]` | Maps `gate_id` → last matched plate; used to detect re-entries |
| `processing_latency` | `Histogram` | Base Prometheus histogram for end-to-end processing time |
| `un_numbers` | `dict` | UN number → description lookup loaded from file |
| `kemler_codes` | `dict` | Kemler code → description lookup loaded from file |

Own attributes initialised by `_init_specific_metrics`:

| Attribute | Type | Description |
|-----------|------|-------------|
| `decisions_processed` | `Counter` | Total decisions emitted |
| `approved_access` | `Counter` | Total `ACCEPTED` decisions |
| `manual_review_decisions` | `Counter` | Total `MANUAL_REVIEW` decisions |

---

#### Methods

##### `_get_active_gate_ids()`

> Returns the list of gate IDs this engine subscribes to, sourced from `config.decision_gate_id_list`.

**Parameters:** None

**Returns:** `list[str]` — Gate IDs parsed from the `decision_gate_ids` config field.

---

##### `_get_consumer_group()`

> Returns the Kafka consumer group identifier for this engine.

**Parameters:** None

**Returns:** `str` — `"decision-engine-group"`

---

##### `_init_specific_metrics()`

> Registers the three Prometheus `Counter` metrics owned by `DecisionEngine`.

**Parameters:** None

**Returns:** `None`

> ⚠️ **Note:** Called once during `__init__` by `BaseDecisionEngine`. Re-registering the same metric names across processes will raise a `ValueError` from `prometheus_client`.

---

##### `_execute_logic(gate_id, truck_id, lp_msg, hz_msg)`

> Evaluates a complete LP + HZ pair for a truck and publishes the resulting access decision.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `gate_id` | `str` | required | Gate that produced the detection events |
| `truck_id` | `str` | required | Kafka `truckId` header identifying the truck |
| `lp_msg` | `LicensePlateResultsMessage` | required | License-plate detection result |
| `hz_msg` | `HazardPlateResultsMessage` | required | Hazard-plate detection result |

**Returns:** `None`

**Decision priority chain (first match wins):**

| Condition | Decision | Reason string |
|-----------|----------|---------------|
| `license_plate == "N/A"` | `MANUAL_REVIEW` | `"License plate not detected"` |
| Appointment API returns error | `MANUAL_REVIEW` | `"API unavailable"` |
| No appointment found | `MANUAL_REVIEW` | `"No appointments found"` |
| Plate does not fuzzy-match | `MANUAL_REVIEW` | `"License plate did not match"` |
| Matched plate equals `last_truck_detected[gate_id]` | `SKIPPED` | `"Same truck detected again shortly after initial detection"` |
| Plate matched a new appointment | `ACCEPTED` | `"License plate matched with appointment"` |

> ⚠️ **Note:** `self.database_client.gate_id` is temporarily overridden to `gate_id` during the appointment query and restored immediately after, making the method non-thread-safe if a single `DatabaseClient` instance is shared across gate threads.

**Example**
```python
engine._execute_logic(
    gate_id="1",
    truck_id="TRUCK-42",
    lp_msg=lp_result,
    hz_msg=hz_result,
)
# Publishes to Kafka topic: agent-decision-1
```

---

##### `_publish_decision(gate_id, truck_id, license_plate, lp_msg, hz_msg, un_number, kemler_code, decision, reason, start_time, alerts, route)`

> Serialises the decision payload and produces it to the gate-specific `agent-decision-{gate_id}` topic.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `gate_id` | `str` | required | Target gate |
| `truck_id` | `str` | required | Kafka `truckId` header value |
| `license_plate` | `str` | required | Resolved or matched plate string |
| `lp_msg` | `LicensePlateResultsMessage` | required | Source LP message (for `crop_url`) |
| `hz_msg` | `HazardPlateResultsMessage` | required | Source HZ message (for `crop_url`) |
| `un_number` | `str` | required | Enriched UN number string (`"1234: Test Chemical"`) |
| `kemler_code` | `str` | required | Enriched Kemler code string |
| `decision` | `str` | required | One of `"ACCEPTED"`, `"MANUAL_REVIEW"`, `"SKIPPED"` |
| `reason` | `str` | required | Human-readable reason for the decision |
| `start_time` | `float` | required | `time.time()` value from the start of `_execute_logic` |
| `alerts` | `list \| None` | `None` | Optional alert strings attached to the message |
| `route` | `str` | `""` | Optional routing instruction (unused in current logic) |

**Returns:** `None`

> ⚠️ **Note:** `gate_id` is injected directly into the Kafka payload dict as `payload["gate_id"]` after `KafkaMessageProto.decision_result()` builds the base message.

---

##### `_record_decision_metrics(decision, start_time)`

> Records processing latency and increments the appropriate decision counter.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `decision` | `str` | required | Decision value string from `DecisionStatus` |
| `start_time` | `float` | required | Epoch timestamp marking the start of processing |

**Returns:** `None`

**Behaviour:**
- Always calls `self.processing_latency.observe(duration)` and `self.decisions_processed.inc()`.
- Increments `approved_access` for `ACCEPTED`; increments `manual_review_decisions` for `MANUAL_REVIEW`.
- `SKIPPED` increments only `decisions_processed`.

---

## Standalone Functions

> N/A

---

## Configuration & Environment Variables

All variables are read by `DecisionEngineConfig` (Pydantic `BaseSettings`) from the process environment.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `KAFKA_BOOTSTRAP` | ❌ | `10.255.32.70:9092` | Kafka broker address |
| `GATE_IDS` | ❌ | `["1"]` | Master JSON array of all gate IDs |
| `DECISION_GATE_IDS` | ❌ | `["1"]` | JSON array of gates this engine monitors |
| `API_URL` | ❌ | `http://localhost:8080/api/v1` | Data Module base URL |
| `TIME_TOLERANCE_MINUTES` | ❌ | `30` | Appointment window tolerance in minutes |
| `MAX_LEVENSHTEIN_DISTANCE` | ❌ | `2` | Max edit distance for fuzzy plate matching |
| `EXPIRATION_TIME_HOURS` | ❌ | `24` | Hours before buffered messages are evicted |
| `UN_NUMBERS_FILE` | ❌ | `./data/un_numbers.txt` | Path to the UN number lookup file |
| `KEMLER_CODES_FILE` | ❌ | `./data/kemler_codes.txt` | Path to the Kemler code lookup file |

---

## Usage Example

```python
from decision_engine.src.decision_engine import DecisionEngine, DecisionEngineConfig

config = DecisionEngineConfig(
    kafka_bootstrap="kafka:9092",
    decision_gate_ids='["1", "2"]',
    api_url="http://data-module:8080/api/v1",
)

engine = DecisionEngine(config=config)
engine.start()  # Blocking loop; call engine.stop() from another thread to exit
```

With injected dependencies (e.g. in tests):
```python
engine = DecisionEngine(
    config=config,
    kafka_producer=mock_producer,
    kafka_consumer=mock_consumer,
    plate_matcher=mock_matcher,
    database_client=mock_db,
)
```

---

## Error Handling

Exceptions thrown by `DatabaseClient.get_appointments()` are caught inside `_execute_logic` and logged via `self.logger.exception()`; the engine falls back to `appointments = None`, which subsequently triggers a `MANUAL_REVIEW` decision. This ensures a network or serialisation error in the Data Module never crashes the Kafka loop.

The outer `while self.running` loop in `BaseDecisionEngine.start()` also wraps each iteration in a broad `except Exception` catch-all, logs the traceback, and continues — so a bug in `_execute_logic` will not terminate the process.

Kafka consumer/producer errors propagate up from the wrappers; they are caught by the same outer handler and logged without re-raise.

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| `src/V_APP/decision_engine/tests/decision_engine_unitTest.py` | Unit | Initialisation, buffer storage, processing trigger, all decision branches, Prometheus metric increments, resource cleanup |

To run:
```bash
cd IntelligentLogistics
source .venv/bin/activate
pytest src/V_APP/decision_engine/tests/decision_engine_unitTest.py -v
```

Or via the V_APP runner:
```bash
cd src/V_APP && ./test_all.sh
```

---

## Known Issues / TODOs

- [ ] `self.last_truck_detected[gate_id] = matched_plate` is commented out in `_execute_logic` after an `ACCEPTED` decision — the deduplication guard for re-detecting the same truck on a successful access is currently inactive.
- [ ] `self.database_client.gate_id` is temporarily mutated during `_execute_logic` to target the correct gate. This is not thread-safe if the same `DatabaseClient` instance were shared across concurrent gate-processing threads.
- [ ] Evaluate the change to a Redis based storage of UN/kemler codes instead of a python dictionary loaded from a text file.

---

## Changelog

> N/A

---

## Related Docs

- [`base_decision_engine.md`](../../shared/base_decision_engine.md)
- [`kafka_wrapper.md`](../../../shared/kafka_wrapper.md)
- [`kafka_protocol.md`](../../../shared/kafka_protocol.md)
- [`database_client.md`](../../shared/database_client.md)
- [`plate_matcher.md`](../../shared/plate_matcher.md)
- [Architecture Overview](../../../../docs/sketch_arquitetura/arquitetura_intelligent_logistics.md)
