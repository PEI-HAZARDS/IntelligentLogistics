# `kafka_wrapper.py`

> Producer and consumer wrappers around `confluent-kafka` with JSON serialization, typed message deserialization, header extraction, and stale-message draining.

---

## Overview

`kafka_wrapper.py` provides two classes — `KafkaProducerWrapper` and `KafkaConsumerWrapper` — that encapsulate the `confluent-kafka` `Producer` and `Consumer` clients. They add JSON serialization/deserialization, delivery callbacks, header parsing (notably `truck_id` extraction), typed message consumption via `kafka_protocol.deserialize_message()`, and a method to drain stale messages on agent startup.

Within the IntelligentLogistics pipeline, `AgentA` uses `KafkaProducerWrapper` to publish truck-detection events. The `broker` and `decision_engine` use `KafkaConsumerWrapper` to consume results from multiple topics, receiving fully typed `Message` objects. `BaseAgent` instantiates both wrappers as shared dependencies for all agent subclasses. Both classes implement the context-manager protocol for clean resource management.

The module does **not** define message schemas (see `kafka_protocol.py`) or perform any detection or business logic.

---

## Location
```
src/shared/src/kafka_wrapper.py
```

## Dependencies

### Internal
| Module | Why it's used |
|--------|---------------|
| `shared/src/kafka_protocol.py` | `deserialize_message()` for typed message consumption |

### External
| Package | Version | Why it's used |
|---------|---------|---------------|
| `confluent-kafka` | — | Kafka `Producer` and `Consumer` clients |

> Standard library modules used: `json`, `logging`, `typing`.

---

## Architecture & Flow

```
  Producer side                          Consumer side
  ──────────                             ─────────────
  AgentA / BaseAgent                     Broker / DecisionEngine
       │                                      │
       │  produce(topic, data, headers)        │  consume_typed_message()
       ▼                                      ▼
 ┌──────────────────┐               ┌──────────────────────┐
 │KafkaProducerWrapper│              │KafkaConsumerWrapper   │
 │                    │              │                       │
 │ json.dumps()       │              │ poll() → parse_message│
 │ producer.produce() │              │ → deserialize_message │
 │ _delivery_callback │              │ → typed Message obj   │
 └──────────────────┘               └──────────────────────┘
       │                                      │
       ▼                                      ▼
  ─── Kafka Broker ──────────────────── Kafka Broker ───
```

---

## Classes

### `KafkaProducerWrapper`

> Wraps `confluent_kafka.Producer` with JSON serialization and delivery logging.

**Inherits from:** `None`

**Constructor**
```python
KafkaProducerWrapper(bootstrap_servers: str)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `bootstrap_servers` | `str` | required | Kafka broker address (e.g. `"10.255.32.143:9092"`) |

**Constructor Raises:**
- `ValueError` — If `bootstrap_servers` is empty.

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `self.producer` | `confluent_kafka.Producer` | Underlying Kafka producer instance (log level set to `1`) |

---

#### Methods

##### `produce(topic, data, key=None, headers=None)`

> Encodes data as JSON and publishes to a Kafka topic.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `topic` | `str` | required | Target Kafka topic |
| `data` | `Any` | required | JSON-serializable payload (typically from `Message.to_dict()`) |
| `key` | `Optional[str]` | `None` | Optional message key |
| `headers` | `Optional[dict]` | `None` | Optional message headers (e.g. `{"truck_id": "TRK123"}`) |

**Returns:** `None`

**Raises:**
- `TypeError` / `ValueError` — If `data` is not JSON-serializable.
- `KafkaException` — If the message cannot be enqueued.

**Example**
```python
from shared.src.kafka_wrapper import KafkaProducerWrapper
from shared.src.kafka_protocol import KafkaMessageProto

producer = KafkaProducerWrapper("10.255.32.143:9092")
msg = KafkaMessageProto.truck_detected(confidence=0.95, num_detections=1)
producer.produce(
    topic="truck-detected-1",
    data=msg.to_dict(),
    headers={"truck_id": "TRK1234abcd"}
)
```

> ⚠️ **Note:** Calls `producer.poll(0)` after each produce to trigger delivery callbacks immediately.

---

##### `flush(timeout=10)`

> Blocks until all queued messages are delivered or timeout expires.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `timeout` | `int` | `10` | Maximum seconds to wait |

**Returns:** `None`

---

##### `close(timeout=10)`

> Flushes pending messages and closes the producer.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `timeout` | `int` | `10` | Maximum seconds to wait for flush |

**Returns:** `None`

---

##### `_delivery_callback(err, msg)`

> Internal callback invoked by `confluent-kafka` on message delivery. Logs errors at `ERROR` and successes at `DEBUG`.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `err` | `KafkaError \| None` | required | Delivery error, if any |
| `msg` | `Message` | required | The delivered Kafka message |

**Returns:** `None`

---

##### `__enter__()` / `__exit__(exc_type, exc_val, exc_tb)`

> Context-manager support. `__exit__` calls `close()` and returns `False`.

---

### `KafkaConsumerWrapper`

> Wraps `confluent_kafka.Consumer` with JSON parsing, typed message deserialization, header extraction, and stale-message draining.

**Inherits from:** `None`

**Constructor**
```python
KafkaConsumerWrapper(bootstrap_servers: str, group_id: str, topics: list)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `bootstrap_servers` | `str` | required | Kafka broker address |
| `group_id` | `str` | required | Consumer group ID |
| `topics` | `list` | required | List of topic names to subscribe to |

**Constructor Raises:**
- `ValueError` — If `bootstrap_servers` is empty.

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `self.consumer` | `confluent_kafka.Consumer` | Underlying Kafka consumer (`auto.offset.reset=latest`, `enable.auto.commit=False`) |

**Consumer Configuration:**
| Setting | Value | Rationale |
|---------|-------|-----------|
| `auto.offset.reset` | `latest` | Only process new messages, not historical backlog |
| `enable.auto.commit` | `False` | Manual commit after processing for at-least-once semantics |

---

#### Methods

##### `consume_message(timeout=1.0)`

> Polls for a single raw Kafka message.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `timeout` | `float` | `1.0` | Poll timeout in seconds |

**Returns:** `confluent_kafka.Message | None` — Raw message, or `None` on timeout or error.

**Raises:**

> N/A

> ⚠️ **Note:** `PARTITION_EOF` errors are silently ignored (not logged as errors).

---

##### `consume_typed_message(timeout=1.0)`

> Consumes, parses, and deserializes a message into a typed `Message` object.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `timeout` | `float` | `1.0` | Poll timeout in seconds |

**Returns:** `tuple[str, Message, str] | tuple[None, None, None]` — `(topic, message_obj, truck_id)` or `(None, None, None)` on timeout or parse failure.

**Raises:**
- `Exception` — If deserialization of a valid (parseable) message fails (propagated from `deserialize_message()`).

**Example**
```python
from shared.src.kafka_wrapper import KafkaConsumerWrapper

consumer = KafkaConsumerWrapper("10.255.32.143:9092", "broker-group", ["truck-detected-1"])
topic, msg, truck_id = consumer.consume_typed_message()
if msg is not None:
    print(f"Got {msg.MESSAGE_TYPE} for truck {truck_id}")
```

---

##### `clear_stale_messages(max_messages=1000)`

> Drains all pending messages from subscribed topics. Intended to be called at agent startup to discard messages that are no longer actionable.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `max_messages` | `int` | `1000` | Maximum number of messages to drain |

**Returns:** `int` — Number of messages cleared.

**Raises:**

> N/A

---

##### `parse_message(msg)`

> Parses a raw Kafka message: decodes JSON payload and extracts `truck_id` from headers.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `msg` | `confluent_kafka.Message` | required | Raw Kafka message |

**Returns:** `tuple[str, dict, str] | tuple[None, None, None]` — `(topic, data_dict, truck_id)` or `(None, None, None)` on failure.

**Raises:**

> N/A

> ⚠️ **Note:** Messages with invalid JSON or missing `truck_id` headers are skipped with a warning log.

---

##### `extract_truck_id_from_headers(headers)`

> Extracts the `truck_id` value from Kafka message headers. Accepts both `"truck_id"` and `"truckId"` key names.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `headers` | `list[tuple[str, bytes]] \| None` | required | Raw Kafka headers |

**Returns:** `Optional[str]` — Decoded truck ID string, or `None` if not found.

**Raises:**

> N/A

---

##### `close()`

> Closes the consumer and releases resources.

**Returns:** `None`

---

##### `__enter__()` / `__exit__(exc_type, exc_val, exc_tb)`

> Context-manager support. `__exit__` calls `close()` and returns `False`.

---

## Standalone Functions

> N/A

---

## Configuration & Environment Variables

> N/A

> Both wrappers receive connection parameters via constructor arguments. Consuming modules resolve environment variables (`KAFKA_BOOTSTRAP`, etc.) before instantiation.

---

## Usage Example

```python
from shared.src.kafka_wrapper import KafkaProducerWrapper, KafkaConsumerWrapper
from shared.src.kafka_protocol import KafkaMessageProto

# --- Producer ---
with KafkaProducerWrapper("10.255.32.143:9092") as producer:
    msg = KafkaMessageProto.truck_detected(confidence=0.95, num_detections=1)
    producer.produce("truck-detected-1", msg.to_dict(), headers={"truck_id": "TRK1234"})

# --- Consumer ---
with KafkaConsumerWrapper("10.255.32.143:9092", "broker-group", ["truck-detected-1"]) as consumer:
    consumer.clear_stale_messages()
    while True:
        topic, msg, truck_id = consumer.consume_typed_message()
        if msg is not None:
            print(f"[{topic}] {msg.MESSAGE_TYPE} for {truck_id}")
```

---

## Error Handling

**Producer:**
- **Serialization errors** — `TypeError` / `ValueError` from `json.dumps()` are logged and re-raised.
- **Kafka errors** — `KafkaException` from `producer.produce()` is logged and re-raised.
- **Delivery failures** — Logged at `ERROR` via `_delivery_callback` (asynchronous, not raised).

**Consumer:**
- **Poll errors** — `PARTITION_EOF` is silently ignored; other errors are logged at `ERROR`, returning `None`.
- **Invalid JSON** — Logged at `WARNING`, returns `(None, None, None)`.
- **Missing truck_id** — Logged at `WARNING`, returns `(None, None, None)`.
- **Deserialization failure** — Logged at `ERROR` and re-raised (from `deserialize_message()`).
- **Stale-message clearing** — Errors during drain are logged at `WARNING` and skipped.

Logging uses a named logger (`KafkaWrapper`) at `DEBUG`, `WARNING`, and `ERROR` levels.

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| `kafka_wrapper_unit_test.py` | Unit | Producer initialization, message production, serialization errors, flush/close, delivery callbacks; Consumer initialization, message consumption, typed message deserialization, message parsing, header extraction, stale-message draining, error handling |

To run:
```bash
pytest src/shared/tests/kafka_wrapper_unit_test.py
```

---

## Known Issues / TODOs

> N/A

---

## Changelog

> N/A

---

## Related Docs

- [kafka_protocol.md](./kafka_protocol.md) — Message schema definitions used by this module
- [base_agent.md](./base_agent.md) — Base class that instantiates both wrappers
- [stream_manager.md](./stream_manager.md) — Provides frames that lead to Kafka events
