# `base_decision_engine.py`

> Abstract base class for decision engines (DecisionEngine, InfractionEngine) providing message buffering, Kafka loops, and utility methods.

---

## Overview

`BaseDecisionEngine` provides the foundational infrastructure for the business-logic engines inside the V_APP. It subscribes to Kafka topics for license-plate (`lp-results`) and hazard-plate (`hz-results`) events. Because these events arrive asynchronously from different AI agents, the base class buffers them in memory. Once both results are present for a specific `(gate_id, truck_id)`, it triggers the abstract `_execute_logic` method implemented by subclasses (`DecisionEngine` or `InfractionEngine`).

It also offers shared utility methods like interacting with the `PlateMatcher` for fuzzy matching plates against appointments fetched via `DatabaseClient`, loading UN and Kemler codes from text files for enrichment, and managing the main running loop.

---

## Location
```
src/V_APP/shared/src/base_decision_engine.py
```

## Dependencies

### Internal
| Module | Why it's used |
|--------|---------------|
| `shared/src/utils.py` | `load_from_file` helper |
| `shared/src/kafka_wrapper.py` | `KafkaConsumerWrapper` and `KafkaProducerWrapper` |
| `shared/src/kafka_protocol.py` | Typed messages (`LicensePlateResultsMessage`, `HazardPlateResultsMessage`) |
| `V_APP/shared/src/plate_matcher.py` | `PlateMatcher` |
| `V_APP/shared/src/database_client.py` | `DatabaseClient` |

### External
| Package | Version | Why it's used |
|---------|---------|---------------|
| `prometheus_client` | — | Defines the `processing_latency` Histogram |
| `pydantic_settings` | — | Defines `BaseDecisionEngineConfig` |

---

## Architecture & Flow

```
[Kafka lp-results / hz-results] 
          │
          ▼
   _consumer_loop() (in start)
          │
          ├─ _store_in_buffer()
          ├─ _clear_stale_buffer_entries()
          └─ _try_process_truck()
                   │
                   ▼ (both LP and HZ present)
            _execute_logic() (implemented by subclasses)
```

---

## Classes

### `BaseDecisionEngineConfig`

> Common configuration for all decision engines, parsing gate IDs into lists and setting API URLs.

**Inherits from:** `BaseSettings` (`pydantic_settings`)

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `kafka_bootstrap` | `str` | Kafka bootstrap string |
| `gate_ids` | `str` | Master list of all gates |
| `decision_gate_ids` | `str` | Inbound/Entry gates |
| `infraction_gate_ids` | `str` | Highway/Approach gates |
| `api_url` | `str` | URL for the Data Module API |
| `time_tolerance_minutes` | `int` | Appointment time tolerance |
| `max_levenshtein_distance` | `int` | Edit distance max for plate matching |
| `expiration_time_hours` | `int` | Hours before stale buffer items are cleared |
| `un_numbers_file` | `str` | Data file for UN numbers |
| `kemler_codes_file` | `str` | Data file for Kemler codes |

---

### `BaseDecisionEngine`

> Abstract base class for gate-agnostic decision engines.

**Inherits from:** `ABC`

**Constructor**
```python
BaseDecisionEngine(
    config: Optional[BaseDecisionEngineConfig] = None,
    kafka_producer: Optional[KafkaProducerWrapper] = None,
    kafka_consumer: Optional[KafkaConsumerWrapper] = None,
    plate_matcher: Optional[PlateMatcher] = None,
    database_client: Optional[DatabaseClient] = None,
)
```

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `self.lp_buffer` | `dict` | In-memory buffer for LP messages |
| `self.hz_buffer` | `dict` | In-memory buffer for HZ messages |
| `self.last_truck_detected` | `dict` | Used to prevent duplicate processing |

---

#### Methods

##### `start()`

> Starts the main Kafka consumer loop, storing messages in buffers and invoking `_try_process_truck()`. 

**Parameters**
> N/A

**Returns:** `None`

---

##### `stop()`

> Stops the running loop gracefully.

**Parameters**
> N/A

**Returns:** `None`

---

##### `_execute_logic(gate_id, truck_id, lp_msg, hz_msg)` *(abstract)*

> Invoked by `_try_process_truck` when both LP and HZ messages are available for a given truck.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `gate_id` | `str` | required | The gate ID |
| `truck_id` | `str` | required | The truck ID |
| `lp_msg` | `LicensePlateResultsMessage` | required | LP Message |
| `hz_msg` | `HazardPlateResultsMessage` | required | HZ Message |

**Returns:** `None`

---

##### `_enrich_hazard_codes(un, kemler)`

> Uses loaded UN/Kemler dictionary maps to return human-readable descriptions of the hazard codes.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `un` | `str` | required | UN Code |
| `kemler` | `str` | required | Kemler Code |

**Returns:** `tuple[str, str]` — Formatted description strings.

---

## Standalone Functions

> N/A

---

## Configuration & Environment Variables

Shared configurations are loaded from environment variables using Pydantic's `BaseSettings`. Crucial variables include `KAFKA_BOOTSTRAP`, `API_URL`, `GATE_IDS`, and `DECISION_GATE_IDS`.

---

## Usage Example

Implemented by concrete classes `DecisionEngine` and `InfractionEngine`.

---

## Error Handling

- Missing UN/Kemler lookup files log exceptions but return empty dictionaries.
- Invalid JSON payloads from Kafka are caught gracefully, and execution continues.
- Buffer expiration logic ensures that missing/dropped messages don't cause indefinite memory leaks.
- `_cleanup_resources` ensures Kafka resources are flushed and closed upon loop termination.

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| `base_decision_engine_unit_test.py` | Unit | Buffer logic, message parsing, metrics setup, hazard code enrichment, and cleanup behavior |

To run:
```bash
pytest src/V_APP/shared/tests/base_decision_engine_unit_test.py
```

---

## Known Issues / TODOs

> N/A

---

## Changelog

> N/A

---

## Related Docs

- [`decision_engine.md`](../decision_engine/decision_engine.md)
- [`infraction_engine.md`](../infraction_engine/infraction_engine.md)
- [`plate_matcher.md`](./plate_matcher.md)
- [`database_client.md`](./database_client.md)
