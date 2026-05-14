# `kafka_protocol.py`

> Defines the typed message protocol for all Kafka communication in the IntelligentLogistics pipeline, with serialization, deserialization, and factory methods.

---

## Overview

`kafka_protocol.py` establishes a shared contract for every Kafka message exchanged between system components. It defines an abstract `Message` base class, four concrete message types — one per pipeline stage — and a `KafkaTopicFactory` that generates consistent, gate-scoped topic names. Together these ensure that producers and consumers agree on field names, types, serialization format (JSON), and topic naming conventions.

The module is imported by every component that publishes or consumes Kafka messages: `AgentA` (truck detection), `AgentB`/`AgentC` (plate recognition), the `decision_engine`, the `broker`, the `api-gateway`, gateways, and the operator frontend. By centralizing schema definitions and topic naming here, field-name mismatches, topic typos, and silent data loss are avoided across the distributed system.

It does **not** handle Kafka transport (see `kafka_wrapper.py`) or business logic — it is purely a data-contract, topic-naming, and serialization layer.

---

## Location
```
src/shared/src/kafka_protocol.py
```

## Dependencies

### Internal
> N/A

### External
> N/A

> Standard library modules used: `json`, `time`, `abc`, `typing`, `logging`.

---

## Architecture & Flow

```
  Producer (e.g. AgentA)                     Consumer (e.g. Broker)
       │                                          │
       │  topic = KafkaTopicFactory                │
       │           .truck_detected(gate_id)        │
       │  msg   = KafkaMessageProto                │
       │           .truck_detected(...)            │
       ▼                                          │
  TruckDetectedMessage                            │
       │                                          │
       │  .to_dict() → JSON                       │
       ▼                                          │
  ─── Kafka Topic ──────────────────────────►     │
                                                   │
                                        JSON → deserialize_message()
                                                   │
                                                   ▼
                                          TruckDetectedMessage
```

**Message flow:**
1. Producers resolve the target topic via `KafkaTopicFactory` methods.
2. Producers create messages via `KafkaMessageProto` factory methods.
3. Messages are serialized with `.to_dict()` / `.to_json()` and published to the resolved topic.
4. Consumers receive JSON, pass it to `deserialize_message()`, and get back a typed `Message` subclass.

---

## Classes

### `KafkaTopicFactory`

> Factory for generating consistent, gate-scoped Kafka topic names. Eliminates hardcoded topic strings across the codebase.

**Inherits from:** `None`

---

#### Methods

##### `truck_detected(gate_id)` *(classmethod)*

> Returns the topic name for truck-detected events.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `gate_id` | `str \| int` | required | Gate identifier |

**Returns:** `str` — `"truck-detected-{gate_id}"`

---

##### `license_plate_results(gate_id)` *(classmethod)*

> Returns the topic name for license plate results.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `gate_id` | `str \| int` | required | Gate identifier |

**Returns:** `str` — `"lp-results-{gate_id}"`

---

##### `hazard_plate_results(gate_id)` *(classmethod)*

> Returns the topic name for hazard plate results.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `gate_id` | `str \| int` | required | Gate identifier |

**Returns:** `str` — `"hz-results-{gate_id}"`

---

##### `agent_decision(gate_id)` *(classmethod)*

> Returns the topic name for agent decision results.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `gate_id` | `str \| int` | required | Gate identifier |

**Returns:** `str` — `"agent-decision-{gate_id}"`

---

##### `operator_decision(gate_id)` *(classmethod)*

> Returns the topic name for operator decision results.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `gate_id` | `str \| int` | required | Gate identifier |

**Returns:** `str` — `"operator-decision-{gate_id}"`

**Example**
```python
from shared.src.kafka_protocol import KafkaTopicFactory

topic = KafkaTopicFactory.truck_detected("1")
# → "truck-detected-1"

topic = KafkaTopicFactory.agent_decision(2)
# → "agent-decision-2"
```

---

### `Message` _(abstract)_

> Base class for all Kafka messages. Subclasses must implement `to_dict()` and `from_dict()`.

**Inherits from:** `ABC`

**Constructor**
```python
Message(timestamp: Optional[int] = None)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timestamp` | `Optional[int]` | `None` | Unix timestamp in milliseconds. Auto-generated from `time.time() * 1000` if not provided. |

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `self.timestamp` | `int` | Message creation time (ms since epoch) |

**Class-level Constants**
| Constant | Type | Value | Description |
|----------|------|-------|-------------|
| `MESSAGE_TYPE` | `Optional[str]` | `None` | Must be overridden by subclasses |

---

#### Methods

##### `to_dict()` _(abstract)_

> Serializes the message to a dictionary.

**Returns:** `dict`

---

##### `to_json()`

> Convenience method — serializes the message to a JSON string via `to_dict()`.

**Returns:** `str` — JSON-encoded representation.

---

##### `from_dict(data)` _(abstract, classmethod)_

> Reconstructs a message instance from a dictionary.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `data` | `dict` | required | Dictionary with message fields |

**Returns:** `Message`

---

### `TruckDetectedMessage`

> Signals that a truck has been detected in a video frame.

**Inherits from:** `Message`

**`MESSAGE_TYPE`:** `"truck_detected"`

**Constructor**
```python
TruckDetectedMessage(confidence: float, num_detections: int, timestamp: Optional[int] = None)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `confidence` | `float` | required | Maximum detection confidence score |
| `num_detections` | `int` | required | Number of trucks detected in the frame |
| `timestamp` | `Optional[int]` | `None` | Unix timestamp in ms |

**Serialized fields:**
| Field | Type |
|-------|------|
| `message_type` | `str` |
| `timestamp` | `int` |
| `confidence` | `float` |
| `num_detections` | `int` |

**`from_dict` Raises:**
- `ValueError` — If `confidence` or `num_detections` is missing.

---

### `LicensePlateResultsMessage`

> Carries license plate OCR results from Agent B.

**Inherits from:** `Message`

**`MESSAGE_TYPE`:** `"license_plate_results"`

**Constructor**
```python
LicensePlateResultsMessage(license_plate: str, crop_url: str, confidence: float, timestamp: Optional[int] = None)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `license_plate` | `str` | required | Recognized plate text |
| `crop_url` | `str` | required | Presigned URL to the plate crop image |
| `confidence` | `float` | required | OCR confidence score |
| `timestamp` | `Optional[int]` | `None` | Unix timestamp in ms |

**Serialized fields:**
| Field | Type |
|-------|------|
| `message_type` | `str` |
| `timestamp` | `int` |
| `license_plate` | `str` |
| `crop_url` | `str` |
| `confidence` | `float` |

**`from_dict` Raises:**
- `ValueError` — If any required field is missing.

---

### `HazardPlateResultsMessage`

> Carries hazard plate OCR results (UN and Kemler codes) from Agent C.

**Inherits from:** `Message`

**`MESSAGE_TYPE`:** `"hazard_plate_results"`

**Constructor**
```python
HazardPlateResultsMessage(un: str, kemler: str, crop_url: str, confidence: float, timestamp: Optional[int] = None)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `un` | `str` | required | UN hazard code |
| `kemler` | `str` | required | Kemler hazard code |
| `crop_url` | `str` | required | Presigned URL to the hazard plate crop |
| `confidence` | `float` | required | OCR confidence score |
| `timestamp` | `Optional[int]` | `None` | Unix timestamp in ms |

**Serialized fields:**
| Field | Type |
|-------|------|
| `message_type` | `str` |
| `timestamp` | `int` |
| `un` | `str` |
| `kemler` | `str` |
| `crop_url` | `str` |
| `confidence` | `float` |

**`from_dict` Raises:**
- `ValueError` — If any required field is missing.

---

### `DecisionResultsMessage`

> Carries the final decision result combining all agent detections, alerts, and routing.

**Inherits from:** `Message`

**`MESSAGE_TYPE`:** `"decision_results"`

**Constructor**
```python
DecisionResultsMessage(
    license_plate: str,
    license_crop_url: str,
    un: str,
    kemler: str,
    hazard_crop_url: str,
    alerts: List[str],
    route: str,
    decision: str,
    decision_reason: str,
    decision_source: str,
    timestamp: Optional[int] = None,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `license_plate` | `str` | required | Recognized license plate text |
| `license_crop_url` | `str` | required | Presigned URL to the license plate crop |
| `un` | `str` | required | UN hazard code |
| `kemler` | `str` | required | Kemler hazard code |
| `hazard_crop_url` | `str` | required | Presigned URL to the hazard plate crop |
| `alerts` | `List[str]` | required | List of triggered alert messages |
| `route` | `str` | required | Assigned route |
| `decision` | `str` | required | Final decision (e.g. `"ACCEPTED"`, `"MANUAL_REVIEW"`) |
| `decision_reason` | `str` | required | Explanation for the decision |
| `decision_source` | `str` | required | Origin of the decision (e.g. `"automated"`, `"operator"`) |
| `timestamp` | `Optional[int]` | `None` | Unix timestamp in ms |

**Serialized fields:**
| Field | Type |
|-------|------|
| `message_type` | `str` |
| `timestamp` | `int` |
| `license_plate` | `str` |
| `license_crop_url` | `str` |
| `un` | `str` |
| `kemler` | `str` |
| `hazard_crop_url` | `str` |
| `alerts` | `List[str]` |
| `route` | `str` |
| `decision` | `str` |
| `decision_reason` | `str` |
| `decision_source` | `str` |

**`from_dict` Raises:**
- `ValueError` — If any required field is missing.

---

### `KafkaMessageProto`

> Factory class providing convenience class methods for creating message instances without importing individual message classes.

**Inherits from:** `None`

---

#### Methods

##### `truck_detected(confidence, num_detections)` _(classmethod)_

> Creates a `TruckDetectedMessage`.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `confidence` | `float` | required | Detection confidence |
| `num_detections` | `int` | required | Number of detections |

**Returns:** `TruckDetectedMessage`

---

##### `license_plate_result(license_plate, crop_url, confidence)` _(classmethod)_

> Creates a `LicensePlateResultsMessage`.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `license_plate` | `str` | required | Plate text |
| `crop_url` | `str` | required | Presigned URL to crop |
| `confidence` | `float` | required | OCR confidence |

**Returns:** `LicensePlateResultsMessage`

---

##### `hazard_plate_result(un, kemler, crop_url, confidence)` _(classmethod)_

> Creates a `HazardPlateResultsMessage`.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `un` | `str` | required | UN code |
| `kemler` | `str` | required | Kemler code |
| `crop_url` | `str` | required | Presigned URL to crop |
| `confidence` | `float` | required | OCR confidence |

**Returns:** `HazardPlateResultsMessage`

---

##### `decision_result(license_plate, license_crop_url, un, kemler, hazard_crop_url, alerts, route, decision, decision_reason, decision_source)` _(classmethod)_

> Creates a `DecisionResultsMessage`.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `license_plate` | `str` | required | Plate text |
| `license_crop_url` | `str` | required | Presigned URL to license crop |
| `un` | `str` | required | UN code |
| `kemler` | `str` | required | Kemler code |
| `hazard_crop_url` | `str` | required | Presigned URL to hazard crop |
| `alerts` | `List[str]` | required | Alert messages |
| `route` | `str` | required | Assigned route |
| `decision` | `str` | required | Decision value |
| `decision_reason` | `str` | required | Decision explanation |
| `decision_source` | `str` | required | Decision origin |

**Returns:** `DecisionResultsMessage`

---

## Standalone Functions

### `deserialize_message(data)`

> Deserializes a dictionary into the appropriate `Message` subclass by inspecting the `message_type` field.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `data` | `dict` | required | Dictionary containing at least a `message_type` key |

**Returns:** `Message` — The appropriate `Message` subclass instance.

**Raises:**
- `ValueError` — If `message_type` is missing, unknown, or if required fields are absent.

**Example**
```python
from shared.src.kafka_protocol import deserialize_message

data = {"message_type": "truck_detected", "confidence": 0.95, "num_detections": 1, "timestamp": 1700000000000}
msg = deserialize_message(data)
# msg is a TruckDetectedMessage
```

---

## Module-level Constants

| Constant | Type | Description |
|----------|------|-------------|
| `MESSAGE_TYPES` | `dict[str, type[Message]]` | Registry mapping `message_type` strings to their `Message` subclasses. Used by `deserialize_message()`. |

---

## Configuration & Environment Variables

> N/A

---

## Usage Example

```python
from shared.src.kafka_protocol import KafkaMessageProto, deserialize_message

# --- Producer side ---
msg = KafkaMessageProto.truck_detected(confidence=0.95, num_detections=1)
payload = msg.to_dict()
# publish payload to Kafka...

# --- Consumer side ---
received_data = {"message_type": "truck_detected", "confidence": 0.95, "num_detections": 1, "timestamp": 1700000000000}
msg = deserialize_message(received_data)
print(msg.confidence)  # 0.95
```

---

## Error Handling

- **Missing fields** — All `from_dict()` methods catch `KeyError` and raise `ValueError` with a descriptive message naming the missing field.
- **Unknown message type** — `deserialize_message()` raises `ValueError` if the `message_type` is not registered in `MESSAGE_TYPES`.
- No exceptions are silently swallowed.

Logging uses a named logger (`protocol`).

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| `kafka_wrapper_unit_test.py` | Unit | Protocol serialization/deserialization is tested indirectly through wrapper integration |

To run:
```bash
pytest src/shared/tests/kafka_wrapper_unit_test.py
```

---

## Known Issues / TODOs

- [x] ~~Add topics name Enum/factory so every consumer/producer can easily get the correct necessary topics~~ — Resolved: `KafkaTopicFactory` added.

---

## Changelog

| Version / Date | Change |
|----------------|--------|
| `2026-02-21` | Added `KafkaTopicFactory` class with gate-scoped topic name generation (`truck_detected`, `license_plate_results`, `hazard_plate_results`, `agent_decision`, `operator_decision`) |

---

## Related Docs

- [kafka_wrapper.md](./kafka_wrapper.md) — Transport layer that uses these message types
- [base_agent.md](./base_agent.md) — Base class for agents that produce/consume these messages
