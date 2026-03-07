# `ai_gateway.py`

> Bridges the AI application's Kafka broker with external gateways by consuming detection events and forwarding operator decisions.

---

## Overview

`ai_gateway.py` defines `AIGateway`, a thin concrete implementation of `BaseGateway` that connects the AI subsystem to the rest of the Intelligent Logistics platform. It subscribes to the three Kafka topics produced within the AI application — `truck_detected`, `license_plate_results`, and `hazard_plate_results` — for every configured gate. Consumed messages are passed through `process_message` (currently a no-op log-and-forward) and then HTTP-POSTed to one or more receiver gateways (typically `VGateway` in the V_APP).

In the inbound direction, `AIGateway` also exposes a FastAPI endpoint (`/receive_message`) where external gateways can POST operator `decision_results` messages. These are written onto the local Kafka `agent_decision_<gate_id>` topic. The routing map built by `get_topics_produce` ensures unambiguous topic resolution even in multi-gate deployments by keying on the `X-Source-Topic` HTTP header; a `message_type`-based fallback is also provided, but only registered when exactly one gate is configured.

`AIGateway` contains no business logic of its own; it delegates all transport, threading, and HTTP concerns to `BaseGateway`.

---

## Location
```
src/AI_APP/gateway/ai_gateway.py
```

## Dependencies

### Internal
| Module | Why it's used |
|--------|---------------|
| `shared/src/base_gateway.py` | Base class (`BaseGateway`) providing Kafka consumer loop, FastAPI server, HTTP forwarding, and lifecycle management |
| `shared/src/kafka_protocol.py` | `Message` type; `KafkaTopicFactory` for topic name construction |

### External
| Package | Version | Why it's used |
|---------|---------|---------------|
| `fastapi` | — | HTTP server for `/receive_message` and `/health` endpoints (via `BaseGateway`) |
| `uvicorn` | — | ASGI runner for the FastAPI app (via `BaseGateway`) |
| `httpx` | — | HTTP client for forwarding messages to receiver gateways (via `BaseGateway`) |
| `prometheus_fastapi_instrumentator` | — | Exposes Prometheus metrics at `/metrics` (via `BaseGateway`) |
| `kafka-python` | — | Kafka consumer/producer via `KafkaWrapper` (via `BaseGateway`) |
| `pydantic-settings` | — | `BaseGatewayConfig` environment loading (via `BaseGateway`) |

---

## Architecture & Flow

```
AI_APP Kafka broker
  ├── truck_detected_<gate_id>         ─┐
  ├── license_plate_results_<gate_id>   ├─► AIGateway._consumer_loop()
  └── hazard_plate_results_<gate_id>   ─┘        │
                                                  │ process_message() [passthrough]
                                                  │
                                                  ▼ HTTP POST /receive_message
                                          Receiver gateways (e.g. VGateway)
                                                  │
                                      ┌───────────┘  (inbound direction)
                                      │  HTTP POST /receive_message
                                      ▼
                               AIGateway FastAPI
                                      │
                                      ▼ produce to local Kafka
                              agent_decision_<gate_id>
```

---

## Classes

### `AIGateway`

> Concrete `BaseGateway` that wires AI-side Kafka topics to external receiver gateways and routes inbound operator decisions back onto the local broker.

**Inherits from:** `BaseGateway`

**Constructor**
```python
AIGateway(config: BaseGatewayConfig, kafka_producer=None, kafka_consumer=None)
```

Fully delegated to `BaseGateway.__init__`. `AIGateway` defines no additional constructor logic or attributes.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `BaseGatewayConfig` | required | Gateway configuration (bootstrap, gate IDs, port, receivers) |
| `kafka_producer` | `KafkaProducerWrapper` | `None` | Kafka producer; created from config if omitted |
| `kafka_consumer` | `KafkaConsumerWrapper` | `None` | Kafka consumer; created from config if omitted |

**Attributes**

> All attributes are inherited from `BaseGateway`. `AIGateway` adds none of its own.

---

#### Methods

##### `get_topics_consume() -> list[str]`

> Builds the list of Kafka topics the gateway subscribes to across all configured gates.

**Parameters**

> N/A

**Returns:** `list[str]` — For every `gate_id` in `self.config.gate_ids`, appends the results of `KafkaTopicFactory.truck_detected(gate_id)`, `KafkaTopicFactory.license_plate_results(gate_id)`, and `KafkaTopicFactory.hazard_plate_results(gate_id)`. Total length = `len(gate_ids) × 3`.

**Raises:**

> N/A

**Example**
```python
# config.gate_ids = ["1", "2"]
topics = gateway.get_topics_consume()
# → ["truck_detected_1", "license_plate_results_1", "hazard_plate_results_1",
#    "truck_detected_2", "license_plate_results_2", "hazard_plate_results_2"]
```

---

##### `get_gateway_name() -> str`

> Returns the unique name of this gateway instance.

**Parameters**

> N/A

**Returns:** `str` — `"AI_Gateway"`. Used as the FastAPI app title, logger name, and Kafka consumer group prefix.

**Raises:**

> N/A

---

##### `get_topics_produce() -> dict[str, str]`

> Builds the routing map used when an external gateway POSTs a message to `/receive_message`.

**Parameters**

> N/A

**Returns:** `dict[str, str]` — Keys are source identifiers; values are destination Kafka topics on the local broker.

- For every `gate_id`, adds `KafkaTopicFactory.agent_decision(gate_id) → KafkaTopicFactory.agent_decision(gate_id)` (keyed on the `X-Source-Topic` header value).
- If exactly one gate is configured, also adds `"decision_results" → KafkaTopicFactory.agent_decision(gate_ids[0])` as a `message_type`-based fallback.

**Raises:**

> N/A

**Example**
```python
# config.gate_ids = ["1"]
topics = gateway.get_topics_produce()
# → {"agent_decision_1": "agent_decision_1", "decision_results": "agent_decision_1"}
```

> ⚠️ **Note:** The `"decision_results"` fallback entry is only added when there is a single gate. In multi-gate deployments, callers must set the `X-Source-Topic` HTTP header to enable correct routing.

---

##### `get_receivers() -> list[str]`

> Returns the list of receiver gateway addresses to which Kafka messages are forwarded.

**Parameters**

> N/A

**Returns:** `list[str]` — `self.config.receivers` (list of `ip:port` strings, e.g., `["10.0.0.1:8001"]`).

**Raises:**

> N/A

---

##### `process_message(message) -> Message`

> Pre-processes a Kafka message before it is forwarded to receiver gateways.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `message` | `Message` | required | Typed message object deserialized from Kafka |

**Returns:** `Message` — The same message object, unchanged.

**Raises:**

> N/A

**Example**
```python
out = gateway.process_message(msg)
assert out is msg  # passthrough
```

> ⚠️ **Note:** The current implementation only logs the message type and returns the message unchanged. No transformation or filtering is applied.

---

## Standalone Functions

> N/A

---

## Configuration & Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `KAFKA_BOOTSTRAP` | ✅ | — | Kafka broker address (`BaseGatewayConfig.kafka_bootstrap`) |
| `GATE_IDS` | ❌ | `["1"]` | Comma-separated list of gate identifiers |
| `GATEWAY_PORT` | ❌ | `8000` | Port on which the FastAPI server listens |
| `GATEWAY_HOST` | ❌ | `0.0.0.0` | Bind address for the FastAPI server |
| `RECEIVERS` | ❌ | `[""]` | Comma-separated list of receiver gateway addresses (`ip:port`) |

---

## Usage Example

```python
from ai_gateway import AIGateway
from shared.src.base_gateway import BaseGatewayConfig

config = BaseGatewayConfig()  # reads from environment
gateway = AIGateway(config=config)
gateway.start()  # blocks: runs FastAPI server on main thread, Kafka consumer on daemon thread
```

---

## Error Handling

All transport-level error handling is implemented in `BaseGateway`. HTTP forwarding errors (`httpx.HTTPError` and general exceptions) per receiver are logged and do not abort forwarding to remaining receivers. The Kafka consumer loop logs and re-raises unhandled exceptions, setting `self.running = False`; the daemon thread surfaces the error and stops. Messages that cannot be deserialized are logged as warnings and skipped. Incoming HTTP messages with an unknown source topic or message type receive a `400` JSON response. Graceful shutdown via `stop()` joins the consumer thread (5-second timeout) and flushes the Kafka producer.

---

## Testing

> N/A

---

## Known Issues / TODOs

- [ ] `process_message` is a passthrough stub; no transformation or filtering logic has been implemented yet (noted by the inline comment: *"For now, we just log the message and return it unchanged."*)

---

## Changelog

> N/A

---

## Related Docs

- [`base_gateway.md`](../../shared/base_gateway.md)
- [`kafka_wrapper.md`](../../../shared/kafka_wrapper.md)
- [Architecture Overview](../../../docs/sketch_arquitetura/arquitetura_intelligent_logistics.md)
