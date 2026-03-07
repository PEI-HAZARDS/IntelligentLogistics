# `base_gateway.py`

> Abstract base class for inter-application gateways that bridge Kafka brokers across separate applications via HTTP forwarding.

---

## Overview

`BaseGateway` provides the foundational infrastructure for gateways that connect two or more applications in the IntelligentLogistics system. Each gateway consumes messages from a local Kafka broker, optionally transforms them, and forwards them via HTTP POST to one or more receiver gateways in other applications. Conversely, it exposes a FastAPI HTTP endpoint to receive messages from remote gateways and produce them to the local Kafka broker.

The module also defines `BaseGatewayConfig`, a Pydantic settings class that centralises configuration for Kafka connectivity, gate IDs, and network addressing. A shared logging dictionary (`LOG_CONFIG`) ensures every component in the process—uvicorn, FastAPI, httpx, and the gateway itself—uses a uniform log format and level.

Concrete subclasses such as `AIGateway` (`src/AI_APP/gateway/ai_gateway.py`) and `VGateway` (`src/V_APP/gateway/v_gateway.py`) implement the abstract methods to define topic routing, naming, and per-message processing.

---

## Location
```
src/shared/src/base_gateway.py
```

## Dependencies

### Internal
| Module | Why it's used |
|--------|---------------|
| `shared/src/kafka_wrapper.py` | `KafkaConsumerWrapper` and `KafkaProducerWrapper` for Kafka I/O |
| `shared/src/kafka_protocol.py` | `Message` dataclass and `deserialize_message` for typed (de)serialization |

### External
| Package | Version | Why it's used |
|---------|---------|---------------|
| `fastapi` | — | HTTP server framework for `/receive_message` and `/health` endpoints |
| `uvicorn` | — | ASGI server to run the FastAPI app on the main thread |
| `httpx` | — | Synchronous HTTP client for forwarding messages to receiver gateways |
| `pydantic-settings` | — | `BaseSettings` subclass for environment-driven configuration |
| `pydantic` | — | `Field` descriptors for config validation |
| `prometheus-fastapi-instrumentator` | — | Auto-instruments FastAPI with Prometheus metrics at `/metrics` |

---

## Architecture & Flow

```
                          ┌──────────────────────────────┐
                          │        BaseGateway           │
                          │                              │
  LOCAL Kafka ──consume──▶│  daemon thread               │
                          │   _consumer_loop()           │
                          │     ├─ deserialize_message() │
                          │     ├─ process_message()     │
                          │     └─ _forward_to_recievers()──HTTP POST──▶ Receiver Gateway(s)
                          │                              │
  Receiver Gateway(s)     │  main thread                 │
    ──HTTP POST──────────▶│   FastAPI / uvicorn          │
                          │     └─ /receive_message      │
                          │         ├─ deserialize       │
                          │         ├─ route via         │
                          │         │  get_topics_produce │
                          │         └─ kafka_producer    │──produce──▶ LOCAL Kafka
                          │                              │
                          │   /health   /metrics         │
                          └──────────────────────────────┘
```

---

## Classes

### `BaseGatewayConfig`

> Pydantic settings model holding gateway configuration sourced from environment variables or constructor arguments.

**Inherits from:** `BaseSettings` (`pydantic_settings`)

**Constructor**
```python
BaseGatewayConfig(
    kafka_bootstrap: str,
    gate_ids: list[str] = ["1"],
    gateway_port: int = 8000,
    gateway_host: str = "0.0.0.0",
    receivers: list[str] = [""],
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `kafka_bootstrap` | `str` | required | Kafka broker address |
| `gate_ids` | `list[str]` | `["1"]` | List of gate identifiers this gateway handles |
| `gateway_port` | `int` | `8000` | Port the FastAPI server listens on |
| `gateway_host` | `str` | `"0.0.0.0"` | Host address the FastAPI server binds to |
| `receivers` | `list[str]` | `[""]` | List of receiver gateway addresses (`ip:port`) to forward messages to |

**Attributes**

| Attribute | Type | Description |
|-----------|------|-------------|
| `kafka_bootstrap` | `str` | Kafka broker connection string |
| `gate_ids` | `list[str]` | Gate identifiers |
| `gateway_port` | `int` | HTTP server port |
| `gateway_host` | `str` | HTTP server bind address |
| `receivers` | `list[str]` | Receiver gateway addresses |

---

### `BaseGateway`

> Abstract base class for inter-app gateways that bridge Kafka brokers via HTTP forwarding.

**Inherits from:** `ABC` (`abc`)

**Constructor**
```python
BaseGateway(
    config: BaseGatewayConfig,
    kafka_producer: Optional[KafkaProducerWrapper] = None,
    kafka_consumer: Optional[KafkaConsumerWrapper] = None,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `BaseGatewayConfig` | required | Gateway configuration object |
| `kafka_producer` | `Optional[KafkaProducerWrapper]` | `None` | Pre-built Kafka producer; one is created from `config.kafka_bootstrap` if not supplied |
| `kafka_consumer` | `Optional[KafkaConsumerWrapper]` | `None` | Pre-built Kafka consumer; one is created from `config.kafka_bootstrap`, consumer group, and topics if not supplied |

**Attributes**

| Attribute | Type | Description |
|-----------|------|-------------|
| `self.config` | `BaseGatewayConfig` | Stored configuration |
| `self.topics_consume` | `list[str]` | Topics returned by `get_topics_consume()` |
| `self.gateway_name` | `str` | Name returned by `get_gateway_name()` |
| `self.receivers` | `list[str]` | Addresses returned by `get_receivers()` |
| `self.kafka_producer` | `KafkaProducerWrapper` | Kafka producer instance |
| `self.kafka_consumer` | `KafkaConsumerWrapper` | Kafka consumer instance (group = `{gateway_name}-group`) |
| `self.running` | `bool` | Lifecycle flag controlling the consumer loop |
| `self._consumer_thread` | `Optional[threading.Thread]` | Daemon thread running the consumer loop |
| `self._http_client` | `httpx.Client` | Synchronous HTTP client (10 s timeout) |
| `self.logger` | `logging.Logger` | Logger named after the gateway |
| `self.app` | `FastAPI` | FastAPI application instance |

---

#### Methods

##### `get_topics_consume()` *(abstract)*

> Return the list of Kafka topics this gateway consumes from the local broker.

**Parameters**

> N/A

**Returns:** `list[str]` — Topic names to subscribe to.

---

##### `get_topics_produce()` *(abstract)*

> Return a routing map used when this gateway receives an HTTP message from another gateway. Keys are source topics (from the `X-Source-Topic` header); values are destination topics on the local Kafka broker.

**Parameters**

> N/A

**Returns:** `dict[str, str]` — Source-topic → destination-topic mapping.

---

##### `get_gateway_name()` *(abstract)*

> Return a unique name for this gateway, used for logging and the Kafka consumer group.

**Parameters**

> N/A

**Returns:** `str` — Gateway name.

---

##### `get_receivers()` *(abstract)*

> Return the list of receiver gateway addresses (`ip:port`) to forward messages to.

**Parameters**

> N/A

**Returns:** `list[str]` — Receiver addresses.

---

##### `process_message(message)` *(abstract)*

> Pre-process a consumed Kafka message before it is forwarded to receiver gateways. Return the (possibly transformed) message, or `None` to drop it.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `message` | `Message` | required | Deserialized Kafka message |

**Returns:** `Optional[Message]` — Processed message, or `None` to discard.

---

##### `_create_app()`

> Build the FastAPI application with `/health`, `/receive_message`, and `/metrics` routes bound to this gateway instance.

**Parameters**

> N/A

**Returns:** `FastAPI` — Configured FastAPI application.

**Endpoints exposed:**

| Route | Method | Description |
|-------|--------|-------------|
| `/health` | `GET` | Returns `{"status": "ok"}` when the consumer thread is alive, `"degraded"` otherwise |
| `/receive_message` | `POST` | Accepts a JSON message from a remote gateway, deserializes it, resolves the destination topic via `get_topics_produce()`, and produces it to the local Kafka broker. Uses `X-Source-Topic` header for topic resolution with `message_type` as fallback |
| `/metrics` | `GET` | Prometheus metrics (auto-instrumented by `prometheus-fastapi-instrumentator`) |

---

##### `_forward_to_recievers(message, truck_id, source_topic)`

> POST a message to every receiver gateway's `/receive_message` endpoint.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `message` | `Message` | required | Message to forward |
| `truck_id` | `Optional[str]` | `None` | Truck identifier propagated as `X-Truck-ID` header |
| `source_topic` | `Optional[str]` | `None` | Originating Kafka topic propagated as `X-Source-Topic` header |

**Returns:** `None`

**Raises:**
- `httpx.HTTPError` — Caught and logged per-receiver; does not stop forwarding to remaining receivers.

> ⚠️ **Note:** The method name contains a typo (`recievers` instead of `receivers`); callers must use the misspelled name.

---

##### `_consumer_loop()`

> Main loop executed in the daemon thread. Consumes messages from local Kafka, deserializes them, passes them through `process_message()`, and forwards surviving messages to all receivers.

**Parameters**

> N/A

**Returns:** `None`

**Raises:**
- Any unhandled exception crashes the loop, sets `self.running = False`, and re-raises.

> ⚠️ **Note:** Calls `kafka_consumer.clear_stale_messages()` on entry to discard messages that arrived while the gateway was offline.

---

##### `start()`

> Start the gateway: spawn the Kafka consumer loop in a daemon thread, then run the FastAPI/uvicorn server on the main thread (blocking).

**Parameters**

> N/A

**Returns:** `None`

> ⚠️ **Note:** This method blocks until the uvicorn server exits (e.g. via `KeyboardInterrupt`). On exit it calls `stop()` automatically.

---

##### `stop()`

> Gracefully stop the gateway: set the running flag to `False`, join the consumer thread (5 s timeout), close the Kafka consumer and producer, and close the HTTP client.

**Parameters**

> N/A

**Returns:** `None`

---

## Standalone Functions

> N/A

---

## Configuration & Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `KAFKA_BOOTSTRAP` | ✅ | — | Kafka broker address (maps to `BaseGatewayConfig.kafka_bootstrap`) |
| `GATE_IDS` | ❌ | `["1"]` | JSON list of gate identifiers |
| `GATEWAY_PORT` | ❌ | `8000` | Port the FastAPI server listens on |
| `GATEWAY_HOST` | ❌ | `0.0.0.0` | Host address the FastAPI server binds to |
| `RECEIVERS` | ❌ | `[""]` | JSON list of receiver gateway addresses (`ip:port`) |

---

## Usage Example

```python
from shared.src.base_gateway import BaseGateway, BaseGatewayConfig
from shared.src.kafka_protocol import Message, KafkaTopicFactory
from typing import Optional


class MyGateway(BaseGateway):
    def get_topics_consume(self) -> list[str]:
        return [KafkaTopicFactory.agent_decision(gid) for gid in self.config.gate_ids]

    def get_topics_produce(self) -> dict[str, str]:
        return {
            KafkaTopicFactory.truck_detected(gid): KafkaTopicFactory.truck_detected(gid)
            for gid in self.config.gate_ids
        }

    def get_gateway_name(self) -> str:
        return "MyGateway"

    def get_receivers(self) -> list[str]:
        return self.config.receivers

    def process_message(self, message: Message) -> Optional[Message]:
        return message  # pass-through


config = BaseGatewayConfig(
    kafka_bootstrap="localhost:9092",
    gate_ids=["1", "2"],
    receivers=["10.0.0.5:8000"],
)
gateway = MyGateway(config=config)
gateway.start()  # blocks on uvicorn
```

---

## Error Handling

HTTP forwarding errors (`httpx.HTTPError` and generic `Exception`) are caught per-receiver inside `_forward_to_recievers`; a failure to reach one receiver does not prevent forwarding to others. The `/receive_message` endpoint returns `400` with a JSON body for invalid JSON payloads, unrecognisable messages, or unmapped topics. The consumer loop catches all exceptions at the top level, logs them with `logger.exception`, sets `self.running = False`, and re-raises to surface the error from the daemon thread. On `KeyboardInterrupt` during `start()`, `stop()` is called in a `finally` block to ensure clean shutdown of Kafka clients and the HTTP client.

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| — | — | No dedicated unit or integration tests for `base_gateway.py` exist in the repository |

> N/A

---

## Known Issues / TODOs

- [ ] Typo in method name `_forward_to_recievers` (should be `_forward_to_receivers`)

---

## Changelog

> N/A

---

## Related Docs

- [`kafka_wrapper.md`](kafka_wrapper.md)
- [`kafka_protocol.md`](kafka_protocol.md)
- [`ai_gateway.py`](../../src/AI_APP/gateway/ai_gateway.py) — Concrete subclass for the AI application
- [`v_gateway.py`](../../src/V_APP/gateway/v_gateway.py) — Concrete subclass for the V application
