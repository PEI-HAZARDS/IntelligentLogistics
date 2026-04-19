Now I have all the information needed to fill the template accurately.

# `infraction_engine.py`

> Stateful infraction-detection service that correlates license-plate and hazard-plate events across highway/approach gates to determine hazardous-goods violations.

---

## Overview

The `InfractionEngine` is one of two decision engines in the V_APP business-logic layer. It subscribes to license-plate (LP) and hazard-plate (HZ) Kafka result topics for a configurable set of highway/approach gates (`infraction_gate_ids`). When both results arrive for the same truck at the same gate, it evaluates whether the truck is transporting hazardous goods and, if so, whether a valid appointment exists at the operational entry gate.

A truck carrying no hazardous goods (UN and Kemler codes absent or `"N/A"`) results in a `infraction=False` decision published immediately. A truck with hazardous goods always produces `infraction=True` — the presence or absence of a matching appointment is logged for traceability but does not change the outcome. The result is published to the per-gate `infraction-decision-{gate_id}` Kafka topic so the API Gateway can forward it to the gate operator's WebSocket.

This module is exclusively responsible for the infraction evaluation path. It does not make access-control decisions (ACCEPTED / MANUAL_REVIEW) — that is the responsibility of the `DecisionEngine`. Both engines share the buffering, message consumption, and appointment-query infrastructure provided by `BaseDecisionEngine`.

---

## Location
```
src/V_APP/infraction_engine/src/infraction_engine.py
```

## Dependencies

### Internal
| Module | Why it's used |
|--------|---------------|
| `V_APP/shared/src/base_decision_engine.py` | Base class providing LP/HZ buffering, Kafka lifecycle, appointment queries, and hazard-code enrichment |
| `shared/src/kafka_protocol.py` | `KafkaTopicFactory`, `KafkaMessageProto`, `LicensePlateResultsMessage`, `HazardPlateResultsMessage` |
| `V_APP/shared/src/plate_matcher.py` | Fuzzy license-plate matching (Levenshtein) via `PlateMatcher` (inherited) |
| `V_APP/shared/src/database_client.py` | HTTP client to the Data Module API for appointment queries (inherited) |

### External
| Package | Version | Why it's used |
|---------|---------|---------------|
| `prometheus_client` | `*` | `Counter` metrics for infraction evaluation totals |
| `pydantic-settings` | `*` | `BaseDecisionEngineConfig` / `BaseSettings` for environment-driven configuration |

---

## Architecture & Flow

```
[lp-results-{gate_id}]  ──┐
                           ├──► BaseDecisionEngine (buffer)
[hz-results-{gate_id}]  ──┘         │
                                     ▼ both available
                              InfractionEngine._execute_logic()
                                     │
                    ┌────────────────┴────────────────┐
                    │ not hazardous                   │ hazardous
                    ▼                                 ▼
              infraction=False           _has_matching_appointment()
                    │                                 │
                    └──────────────┬──────────────────┘
                                   ▼
                         _publish_infraction()
                                   │
                                   ▼
                    [infraction-decision-{gate_id}]
                                   │
                                   ▼
                           API Gateway → WebSocket → Operator
```

The engine subscribes to `infraction_gate_ids` (highway/approach cameras). The appointment lookup is performed against the first gate in `decision_gate_ids` (the port entry gate), not the source camera gate.

---

## Classes

### `InfractionEngineConfig`

> Configuration class for the Infraction Engine; extends `BaseDecisionEngineConfig` without adding new fields.

**Inherits from:** `BaseDecisionEngineConfig`

**Constructor**
```python
InfractionEngineConfig(
    kafka_bootstrap: str = "10.255.32.70:9092",
    gate_ids: str = '["1"]',
    decision_gate_ids: str = '["1"]',
    infraction_gate_ids: str = '["1"]',
    api_url: str = "http://localhost:8080/api/v1",
    time_tolerance_minutes: int = 30,
    max_levenshtein_distance: int = 2,
    expiration_time_hours: int = 24,
    un_numbers_file: str = "./data/un_numbers.txt",
    kemler_codes_file: str = "./data/kemler_codes.txt",
)
```

All parameters are inherited from `BaseDecisionEngineConfig` and populated from environment variables via Pydantic `BaseSettings`.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `kafka_bootstrap` | `str` | `"10.255.32.70:9092"` | Kafka broker address |
| `gate_ids` | `str` | `'["1"]'` | Master JSON array of gate IDs |
| `decision_gate_ids` | `str` | `'["1"]'` | Entry/operational gate IDs used for appointment lookup |
| `infraction_gate_ids` | `str` | `'["1"]'` | Highway/approach gate IDs this engine subscribes to |
| `api_url` | `str` | `"http://localhost:8080/api/v1"` | Data Module REST API base URL |
| `time_tolerance_minutes` | `int` | `30` | Appointment time-window tolerance |
| `max_levenshtein_distance` | `int` | `2` | Max edit distance for fuzzy plate matching |
| `expiration_time_hours` | `int` | `24` | TTL for buffered LP/HZ messages |
| `un_numbers_file` | `str` | `"./data/un_numbers.txt"` | Path to UN number lookup file |
| `kemler_codes_file` | `str` | `"./data/kemler_codes.txt"` | Path to Kemler code lookup file |

**Attributes**

Inherited from `BaseDecisionEngineConfig`:

| Attribute | Type | Description |
|-----------|------|-------------|
| `infraction_gate_id_list` | `list[str]` | Parsed list from `infraction_gate_ids` JSON string |
| `decision_gate_id_list` | `list[str]` | Parsed list from `decision_gate_ids` JSON string |
| `gate_id_list` | `list[str]` | Parsed list from `gate_ids` JSON string |

---

### `InfractionEngine`

> Stateful service that evaluates hazardous-goods infractions by correlating LP and HZ Kafka messages across one or more highway/approach gates.

**Inherits from:** `BaseDecisionEngine`

**Constructor**
```python
InfractionEngine(
    config: Optional[InfractionEngineConfig] = None,
    kafka_producer: Optional[KafkaProducerWrapper] = None,
    kafka_consumer: Optional[KafkaConsumerWrapper] = None,
    plate_matcher: Optional[PlateMatcher] = None,
    database_client: Optional[DatabaseClient] = None,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `Optional[InfractionEngineConfig]` | `None` | Engine configuration; defaults to `InfractionEngineConfig()` |
| `kafka_producer` | `Optional[KafkaProducerWrapper]` | `None` | Kafka producer; instantiated from config if not provided |
| `kafka_consumer` | `Optional[KafkaConsumerWrapper]` | `None` | Kafka consumer; instantiated from config if not provided |
| `plate_matcher` | `Optional[PlateMatcher]` | `None` | Fuzzy plate matcher; defaults to `PlateMatcher()` |
| `database_client` | `Optional[DatabaseClient]` | `None` | Data Module HTTP client; defaults to `DatabaseClient(api_url, gate_id)` |

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `infractions_processed` | `Counter` | Total infraction evaluations performed |
| `infractions_detected` | `Counter` | Total evaluations that resulted in an infraction |
| `no_infractions` | `Counter` | Total evaluations that resulted in no infraction |
| `lp_buffer` | `dict[tuple[str,str], LicensePlateResultsMessage]` | In-memory LP message buffer keyed by `(gate_id, truck_id)` (inherited) |
| `hz_buffer` | `dict[tuple[str,str], HazardPlateResultsMessage]` | In-memory HZ message buffer keyed by `(gate_id, truck_id)` (inherited) |
| `processing_latency` | `Histogram` | Prometheus histogram of evaluation duration (inherited) |

---

#### Methods

##### `_get_active_gate_ids()`

> Returns the list of gate IDs this engine subscribes to (highway/approach gates from `infraction_gate_id_list`).

**Parameters:** None

**Returns:** `list[str]` — Gate ID strings from `config.infraction_gate_id_list`.

---

##### `_get_consumer_group()`

> Returns the Kafka consumer group identifier for this engine.

**Parameters:** None

**Returns:** `str` — Always `"infraction-engine-group"`.

---

##### `_init_specific_metrics()`

> Initialises the three Prometheus `Counter` metrics specific to `InfractionEngine`.

**Parameters:** None

**Returns:** `None`

> ⚠️ **Note:** Called automatically by `BaseDecisionEngine.__init__`. Registers `infraction_engine_processed_total`, `infraction_engine_infractions_total`, and `infraction_engine_no_infractions_total`.

---

##### `_execute_logic(gate_id, truck_id, lp_msg, hz_msg)`

> Core infraction evaluation: determines whether a truck with hazardous goods is violating highway regulations and publishes the decision.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `gate_id` | `str` | required | Source camera gate the truck was detected at |
| `truck_id` | `str` | required | Unique truck identifier (Kafka `truckId` header) |
| `lp_msg` | `LicensePlateResultsMessage` | required | License-plate detection result |
| `hz_msg` | `HazardPlateResultsMessage` | required | Hazard-plate detection result |

**Returns:** `None`

**Example**
```python
engine._execute_logic(
    gate_id="2",
    truck_id="truck-abc",
    lp_msg=LicensePlateResultsMessage("AB12CD", "http://…/lp.jpg", 0.9),
    hz_msg=HazardPlateResultsMessage("1234", "33", "http://…/hz.jpg", 0.85),
)
```

> ⚠️ **Note:** A hazardous truck always yields `infraction=True` regardless of whether an appointment was found. The appointment check is performed against `decision_gate_id_list[0]`, not the source camera gate.

---

##### `_is_hazardous(raw_un, raw_kemler)`

> Returns `True` if either the UN number or Kemler code is present and not `"N/A"`.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `raw_un` | `str` | required | Raw UN number string from the HZ detection result |
| `raw_kemler` | `str` | required | Raw Kemler code string from the HZ detection result |

**Returns:** `bool` — `True` if at least one code is non-empty and not `"N/A"`.

**Example**
```python
engine._is_hazardous("1234", "N/A")  # → True
engine._is_hazardous("N/A", "N/A")  # → False
engine._is_hazardous("", "")        # → False
```

---

##### `_has_matching_appointment(gate_id, license_plate)`

> Queries the Data Module for scheduled appointments at the given gate and fuzzy-matches the license plate against candidates.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `gate_id` | `str` | required | Entry gate ID to query (temporarily overrides `database_client.gate_id`) |
| `license_plate` | `str` | required | Detected license plate to match |

**Returns:** `Tuple[bool, str]` — `(matched, plate)` where `matched` indicates a successful match and `plate` is the canonical plate string from the appointment (or the original input on failure).

**Raises:**
- `Exception` — Caught internally; logged via `logger.exception`; returns `(False, license_plate)` on any error.

**Example**
```python
matched, plate = engine._has_matching_appointment("1", "AB12CD")
# matched → True, plate → "AB12CD"  (if appointment exists)
# matched → False, plate → "AB12CD" (if no appointment or API unavailable)
```

> ⚠️ **Note:** Temporarily mutates `database_client.gate_id` for the duration of the API call and restores it afterwards. Returns `(False, license_plate)` immediately when `license_plate == "N/A"`.

---

##### `_publish_infraction(gate_id, truck_id, license_plate, lp_msg, hz_msg, un_number, kemler_code, infraction, start_time)`

> Builds the infraction decision payload and publishes it to the `infraction-decision-{gate_id}` Kafka topic.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `gate_id` | `str` | required | Source camera gate ID; used for topic routing and payload fields |
| `truck_id` | `str` | required | Truck identifier sent as the `truckId` Kafka header |
| `license_plate` | `str` | required | Canonical license plate (possibly corrected by fuzzy match) |
| `lp_msg` | `LicensePlateResultsMessage` | required | Original LP message (provides `crop_url`) |
| `hz_msg` | `HazardPlateResultsMessage` | required | Original HZ message (provides `crop_url`) |
| `un_number` | `str` | required | Enriched UN number string (e.g. `"1234: Test Chemical"`) |
| `kemler_code` | `str` | required | Enriched Kemler code string (e.g. `"33: Highly Flammable"`) |
| `infraction` | `bool` | required | Whether an infraction was detected |
| `start_time` | `float` | required | `time.time()` value captured at the start of `_execute_logic` for latency measurement |

**Returns:** `None`

> ⚠️ **Note:** Both `gate_id` and `source_gate_id` fields in the payload are set to the source camera gate ID. Calls `_record_infraction_metrics` after publishing.

---

##### `_record_infraction_metrics(infraction, start_time)`

> Records Prometheus metrics for a completed infraction evaluation.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `infraction` | `bool` | required | Whether an infraction was detected |
| `start_time` | `float` | required | Unix timestamp from the start of the evaluation |

**Returns:** `None`

---

## Standalone Functions

> N/A

---

## Configuration & Environment Variables

All variables are read by `InfractionEngineConfig` (via Pydantic `BaseSettings`) from the process environment.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `KAFKA_BOOTSTRAP` | ❌ | `10.255.32.70:9092` | Kafka broker address |
| `GATE_IDS` | ❌ | `["1"]` | Master JSON array of gate IDs |
| `DECISION_GATE_IDS` | ❌ | `["1"]` | JSON array of entry/operational gate IDs used for appointment lookups |
| `INFRACTION_GATE_IDS` | ❌ | `["1"]` | JSON array of highway/approach gate IDs this engine subscribes to |
| `API_URL` | ❌ | `http://localhost:8080/api/v1` | Data Module REST API base URL |
| `TIME_TOLERANCE_MINUTES` | ❌ | `30` | Appointment match time-window tolerance in minutes |
| `MAX_LEVENSHTEIN_DISTANCE` | ❌ | `2` | Maximum edit distance for fuzzy plate matching |
| `EXPIRATION_TIME_HOURS` | ❌ | `24` | Hours before a buffered LP/HZ message is discarded |
| `UN_NUMBERS_FILE` | ❌ | `./data/un_numbers.txt` | Path to pipe-separated UN number lookup file |
| `KEMLER_CODES_FILE` | ❌ | `./data/kemler_codes.txt` | Path to pipe-separated Kemler code lookup file |

---

## Usage Example

```python
from V_APP.infraction_engine.src.infraction_engine import InfractionEngine, InfractionEngineConfig

config = InfractionEngineConfig(
    kafka_bootstrap="kafka:9092",
    infraction_gate_ids='["2", "3"]',   # highway approach cameras
    decision_gate_ids='["1"]',           # port entry gate for appointment lookup
    gate_ids='["1", "2", "3"]',
    api_url="http://data-module:8080/api/v1",
)

engine = InfractionEngine(config=config)
engine.start()   # blocking; call engine.stop() from another thread to exit
```

---

## Error Handling

`BaseDecisionEngine.start()` wraps the entire consumer loop in a `try/except Exception` that logs and continues, so the engine survives malformed or unexpected Kafka messages. Within `_execute_logic`, appointment query failures in `_has_matching_appointment` are caught locally and logged via `logger.exception`; the engine proceeds with `(False, license_plate)` and still publishes a decision. All resources (consumer, producer) are released in the `finally` block of `start()` via `_cleanup_resources`.

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| `src/V_APP/infraction_engine/tests/infraction_engine_unit_test.py` | Unit | Config inheritance, consumer group, metric initialisation, `_is_hazardous` boundary cases, `_has_matching_appointment` (API errors, unavailability, match/no-match, gate-id restoration), `_execute_logic` (no-hazard, hazardous with/without appointment), `_publish_infraction` (topic routing, headers, payload flags), `_record_infraction_metrics` |

To run:
```bash
cd IntelligentLogistics
source .venv/bin/activate
pytest src/V_APP/infraction_engine/tests/infraction_engine_unit_test.py -v
```

---

## Known Issues / TODOs

- Evaluate the change to a Redis based storage of UN/kemler codes instead of a python dictionary loaded from a text file.

---

## Changelog

> N/A

---

## Related Docs

- [`base_decision_engine.md`](../../shared/base_decision_engine.md)
- [`kafka_protocol.md`](../../../shared/kafka_protocol.md)
- [`plate_matcher.md`](../../shared/plate_matcher.md)
- [`database_client.md`](../../shared/database_client.md)
- [Architecture Overview](../../../docs/sketch_arquitetura/arquitetura_intelligent_logistics.md)
