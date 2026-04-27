# `v_brain.py`

> Central orchestrator for the V_APP that handles cross-gate truck tracking, triggering stream scale-up/down events, and emitting AgentA reset signals.

---

## Overview

`VBrain` is the gate-agnostic central orchestrator for the Intelligent Logistics V_APP. A single instance manages all gates by subscribing to multiple Kafka topics per gate (`truck-detected`, `lp-results`, `hz-results`, `agent-decision`, `infraction-decision`). It uses the `ScaleCorrelator` to track the state of each truck as it progresses through the detection pipeline. 

When a truck is detected, `VBrain` emits a `scale-up` event to request a high-quality video stream. It then accumulates results from the OCR agents. Once both results are received or a final decision is made, it emits a `scale-down` event and sends a reset signal to `AgentA`. It also runs a background thread to detect stale trucks that have timed out and cleans them up.

---

## Location
```
src/V_APP/v_brain/src/v_brain.py
```

## Dependencies

### Internal
| Module | Why it's used |
|--------|---------------|
| `shared/src/kafka_wrapper.py` | `KafkaConsumerWrapper` and `KafkaProducerWrapper` for Kafka I/O |
| `shared/src/kafka_protocol.py` | `KafkaTopicFactory`, `KafkaMessageProto`, `deserialize_message` |
| `V_APP/v_brain/config.py` | Configuration via `VBrainConfig` |
| `V_APP/v_brain/src/scale_correlator.py` | `ScaleCorrelator` for tracking per-truck state |

### External
| Package | Version | Why it's used |
|---------|---------|---------------|
| `prometheus_client` | — | Metrics tracking (`Counter`, `Histogram`, `Gauge`) |
| `requests` | — | HTTP client to call the network scaling API |

---

## Architecture & Flow

```
[Kafka Topics per Gate]
  ├─ truck-detected       → scale UP, register truck in correlator
  ├─ lp-results           → update correlator, scale DOWN if both results ready
  ├─ hz-results           → update correlator, scale DOWN if both results ready
  ├─ agent-decision       → scale DOWN, reset AgentA
  └─ infraction-decision  → scale DOWN, reset AgentA
            │
            ▼
        [VBrain] ──(Timeout Thread)──> scale DOWN, reset AgentA (if stale)
            │
            ├─→ [Kafka: scale-up/scale-down (global)]
            └─→ [Kafka: reset-agentA-{gate_id} (per gate)]
            └─→ [HTTP: scaling API (slice manipulation)]
```

---

## Classes

### `VBrain`

> V_Brain — central orchestrator for the V_APP.

**Inherits from:** `None`

**Constructor**
```python
VBrain(
    config: VBrainConfig | None = None,
    kafka_producer: KafkaProducerWrapper | None = None,
    kafka_consumer: KafkaConsumerWrapper | None = None,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `VBrainConfig \| None` | `None` | Configuration object |
| `kafka_producer` | `KafkaProducerWrapper \| None` | `None` | Kafka producer |
| `kafka_consumer` | `KafkaConsumerWrapper \| None` | `None` | Kafka consumer |

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `self.config` | `VBrainConfig` | VBrain configuration |
| `self.running` | `bool` | Lifecycle flag for the main loop |
| `self._topic_map` | `dict[str, tuple[str, str]]` | Maps topic names to `(gate_id, topic_type)` |
| `self.consume_topics` | `list[str]` | List of all subscribed topics |
| `self.scale_status` | `bool` | Current scale state (`True` = scaled up) |
| `self.kafka_consumer` | `KafkaConsumerWrapper` | Consumer instance |
| `self.kafka_producer` | `KafkaProducerWrapper` | Producer instance |
| `self.correlator` | `ScaleCorrelator` | Tracks truck progress and timeouts |

---

#### Methods

##### `start()`

> Starts the V_Brain consumer loop (blocking). Initializes Prometheus metrics, starts the timeout tracking thread, and continuously consumes/dispatches Kafka messages.

**Parameters**
> N/A

**Returns:** `None`

---

##### `stop()`

> Signals the main loop and timeout thread to stop.

**Parameters**
> N/A

**Returns:** `None`

---

##### `_handle_message(topic, message, truck_id)`

> Routes a consumed message to the appropriate handler based on `self._topic_map`.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `topic` | `str` | required | The Kafka topic name |
| `message` | `Message` | required | The deserialized message object |
| `truck_id` | `str \| None` | required | Truck ID extracted from headers |

**Returns:** `None`

---

##### `_scale_up_try(gate_id, reason)`

> Publishes a `scale_up` event via Kafka and makes an HTTP call to the network scaling API if not already scaled up.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `gate_id` | `str` | required | Gate identifier |
| `reason` | `str` | `"unknown"` | Reason for scaling up |

**Returns:** `None`

---

##### `_scale_down_try(gate_id, reason)`

> Publishes a `scale_down` event via Kafka. Makes an HTTP call to scale down the network slice if no active trucks require the high-quality stream.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `gate_id` | `str` | required | Gate identifier |
| `reason` | `str` | `"unknown"` | Reason for scaling down |

**Returns:** `None`

---

##### `_reset_agent_a(gate_id, reason)`

> Publishes a `reset-agentA` message for the given gate with a 7-second delay (via a background thread).

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `gate_id` | `str` | required | Gate identifier |
| `reason` | `str` | `"unknown"` | Reason for resetting |

**Returns:** `None`

---

##### `_timeout_loop()`

> Background thread that periodically (every 5s) checks `self.correlator` for timed-out trucks. Forcing scale-down and reset if found.

**Parameters**
> N/A

**Returns:** `None`

---

## Standalone Functions

> N/A

---

## Configuration & Environment Variables

Most configuration happens via `VBrainConfig`. Key parameters involve the scaling API configuration (`SCALING_API_URL`, `SCALING_SLICE_ID`, etc.) and the correlator timeout (`CORRELATOR_TIMEOUT_SECONDS`).

---

## Usage Example

```python
from v_brain.src.v_brain import VBrain
from v_brain.config import VBrainConfig

config = VBrainConfig()
v_brain = VBrain(config=config)
v_brain.start()
```

---

## Error Handling

- Invalid JSON payloads and deserialization errors log a warning and are skipped.
- HTTP requests to the scaling API log success or failure but do not crash the service.
- The main Kafka consumer loop catches unexpected exceptions, logs them, and stops the service.

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| `v_brain_unit_test.py` | Unit | Topic routing, scaling logic, timeout loops, HTTP client mocks, and message handling |

To run:
```bash
pytest src/V_APP/v_brain/tests/
```

---

## Known Issues / TODOs

> N/A

---

## Changelog

> N/A

---

## Related Docs

- [`scale_correlator.md`](./scale_correlator.md)
- [`kafka_wrapper.md`](../../shared/kafka_wrapper.md)
- [`kafka_protocol.md`](../../shared/kafka_protocol.md)
