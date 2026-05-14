# `api_gateway.py`

> FastAPI-based API Gateway for the V_APP, bridging Kafka events, WebSocket clients, and REST routers for operators, managers, and drivers.

---

## Overview

The API Gateway is the public-facing entry point of the V_APP business-logic service. It exposes a REST API (under `/api`) composed of modular routers (auth, arrivals, manual_review, alerts, drivers, stream, workers, statistics, realtime) and a unified WebSocket channel for real-time updates to gate operators, managers, and drivers. It integrates with Keycloak for authentication/authorization via `KeycloakClient` and `TokenValidator`.

In the broader architecture, the gateway consumes Kafka topics produced by the Decision Engine (`agent-decision-{gate_id}`), the Infraction Engine (`infraction-decision-{gate_id}`), and V_Brain (`scale-up`/`scale-down`), then fans them out to the appropriate WebSocket subscribers via `WebSocketManager`. For ACCEPTED decisions and infractions, it resolves the associated driver by calling the Data Module (`/api/v1/arrivals/query/license-plate/{plate}`) to push targeted notifications to the driver's WebSocket.

It does NOT perform business-logic decisions itself (that is the Decision/Infraction engines' responsibility), nor does it persist data directly — all persistence is delegated to the Data Module over HTTP.

---

## Location
```
src/V_APP/api_gateway/src/api_gateway.py
```

## Dependencies

### Internal
| Module | Why it's used |
|--------|---------------|
| `web_socket_manager.WebSocketManager` | Unified WebSocket broadcasting to gates and drivers |
| `shared.src.kafka_wrapper` | `KafkaConsumerWrapper` / `KafkaProducerWrapper` for Kafka I/O |
| `shared.src.kafka_protocol` | `deserialize_message`, `KafkaTopicFactory`, `Message` |
| `routers.*` | FastAPI routers (arrivals, auth, manual_review, alerts, drivers, stream, realtime, workers, statistics) |
| `auth.keycloak_client.KeycloakClient` | Keycloak admin/client integration |
| `auth.token_validator.TokenValidator` | JWT validation against Keycloak JWKS |

### External
| Package | Version | Why it's used |
|---------|---------|---------------|
| `fastapi` | — | Web framework |
| `uvicorn` | — | ASGI server |
| `httpx` | — | Async HTTP client for Data Module lookups |
| `pydantic-settings` | — | Environment-based configuration |
| `pydantic` | — | Field validation |
| `prometheus-fastapi-instrumentator` | — | Metrics exposition |
| `opentelemetry-*` | — | Distributed tracing via OTLP |

---

## Architecture & Flow

```
[Kafka: agent-decision-{g}]      ─┐
[Kafka: infraction-decision-{g}] ─┤→ _consumer_loop → _handle_decision / _handle_infraction
[Kafka: scale-up | scale-down]   ─┘                         │
                                                            ├→ WebSocketManager.broadcast (gate)
                                                            └→ Data Module lookup → broadcast_to_driver

[REST clients] ──→ FastAPI (/api/*) ──→ routers.* ──→ Data Module / Keycloak
[WebSocket clients] ──→ realtime router ──→ WebSocketManager
```

---

## Classes

### `APIGatewayConfig`

> Pydantic `BaseSettings` holding all runtime configuration for the gateway.

**Inherits from:** `BaseSettings`

**Constructor**
```python
APIGatewayConfig()  # Values loaded from environment variables
```

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `kafka_bootstrap` | `str` | Kafka bootstrap servers (default `localhost:9092`) |
| `gate_ids` | `str` | JSON array string of all known gate IDs |
| `decision_gate_ids` | `str` | JSON array string of inbound/entry gate IDs |
| `infraction_gate_ids` | `str` | JSON array string of highway/approach gate IDs |
| `gateway_port` | `int` | Port the HTTP server listens on (default `8000`) |
| `data_module_url` | `str` | Base URL of the Data Module service |
| `stream_base_url` | `str` | Base URL for HLS streams (MediaMTX) |
| `stream_webrtc_base_url` | `str` | Base URL for WebRTC streams |
| `api_prefix` | `str` | Prefix under which routers are mounted (default `/api`) |
| `env` | `str` | Environment label (e.g. `dev`) |
| `cors_allow_origins` | `list[str]` | CORS allowed origins |
| `cors_allow_credentials` | `bool` | CORS allow credentials flag |
| `cors_allow_methods` | `list[str]` | CORS allowed methods |
| `cors_allow_headers` | `list[str]` | CORS allowed headers |
| `keycloak_url` | `str` | Keycloak server URL |
| `keycloak_realm` | `str` | Keycloak realm name |
| `keycloak_client_id` | `str` | Keycloak client ID |
| `keycloak_client_secret` | `str` | Keycloak client secret |

---

#### Methods

##### `_parse_gate_ids(v)`

> Field validator ensuring gate ID fields are valid non-empty JSON arrays.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `v` | `str` | required | Raw field value |

**Returns:** `str` — The original value if valid.

**Raises:**
- `ValueError` — If the value is not valid JSON or is not a non-empty list.

---

##### `_to_list(json_str)`

> Parse a JSON array string into a list of string IDs.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `json_str` | `str` | required | JSON array string |

**Returns:** `list[str]` — Gate IDs as strings.

---

##### `gate_id_list` / `decision_gate_id_list` / `infraction_gate_id_list`

> Property accessors returning the corresponding `*_gate_ids` field parsed as `list[str]`.

**Returns:** `list[str]`

---

### `APIGateway`

> Top-level orchestrator composing the FastAPI app, Kafka consumer/producer, and WebSocket manager.

**Inherits from:** `None`

**Constructor**
```python
APIGateway(
    config: APIGatewayConfig | None = None,
    kafka_producer: KafkaProducerWrapper | None = None,
    kafka_consumer: KafkaConsumerWrapper | None = None,
    ws_manager: WebSocketManager | None = None,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `APIGatewayConfig \| None` | `None` | Configuration; defaults to env-loaded instance |
| `kafka_producer` | `KafkaProducerWrapper \| None` | `None` | Injected producer; built from config if omitted |
| `kafka_consumer` | `KafkaConsumerWrapper \| None` | `None` | Injected consumer subscribed to scale/decision/infraction topics |
| `ws_manager` | `WebSocketManager \| None` | `None` | Injected WebSocket manager |

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `self.config` | `APIGatewayConfig` | Active configuration |
| `self.consume_topics` | `list[str]` | Topics subscribed to (scale-up/down, agent/infraction decisions per gate) |
| `self.kafka_producer` | `KafkaProducerWrapper` | Kafka producer instance |
| `self.kafka_consumer` | `KafkaConsumerWrapper` | Kafka consumer (group `api-gateway-group`) |
| `self.ws_manager` | `WebSocketManager` | Unified WebSocket manager |
| `self.app` | `FastAPI` | Configured FastAPI application |
| `self.running` | `bool` | Consumer loop run flag |
| `self._loop` | `asyncio.AbstractEventLoop` | Event loop used for scheduling async broadcasts |
| `self._consumer_thread` | `threading.Thread` | Background Kafka consumer thread |

---

#### Methods

##### `_resolve_target_gate(payload, topic)`

> Determine the target gate from the payload or by parsing the Kafka topic suffix.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `payload` | `dict` | required | Deserialized message payload |
| `topic` | `str` | required | Kafka topic name |

**Returns:** `str | None` — Gate ID if resolvable, else `None`.

---

##### `_handle_infraction(payload, target_gate)`

> Broadcast infraction to source gate, notify other operational gates via `status_changed`, and alert the driver if `infraction` is true.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `payload` | `dict` | required | Infraction decision payload |
| `target_gate` | `str` | required | Gate ID to target |

**Returns:** `None`

---

##### `_handle_decision(payload, target_gate)`

> Broadcast a decision to its gate; if `decision_results` with `ACCEPTED`, notify the driver.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `payload` | `dict` | required | Decision payload |
| `target_gate` | `str` | required | Gate ID to target |

**Returns:** `None`

---

##### `_consumer_loop()`

> Background thread loop: consume messages, deserialize, skip `SKIPPED` decisions, and dispatch to infraction/decision handlers.

**Returns:** `None`

> ⚠️ **Note:** Exceptions inside deserialization are logged and skipped; the loop only exits on `self.running = False` or a fatal error.

---

##### `_broadcast_async(message, target_gates)`

> Thread-safe scheduling of `ws_manager.broadcast` onto the gateway's asyncio loop.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `message` | `dict` | required | Payload to broadcast |
| `target_gates` | `str \| list[str]` | required | Gate(s) to target |

**Returns:** `None`

---

##### `_notify_driver_of_infraction(license_plate, gate_id)`

> Schedule `_resolve_and_notify_driver_infraction` from the consumer thread.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `license_plate` | `str` | required | Plate to look up |
| `gate_id` | `str` | required | Source gate ID |

**Returns:** `None`

---

##### `_resolve_and_notify_driver_infraction(license_plate, gate_id)`

> Async: look up appointment by plate via Data Module, then broadcast `infraction_warning` to the driver WS.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `license_plate` | `str` | required | Plate to look up |
| `gate_id` | `str` | required | Source gate ID |

**Returns:** `None` — Logs and returns early on HTTP error, empty results, or missing `driver_license`.

---

##### `_notify_driver_of_acceptance(license_plate)`

> Schedule `_resolve_and_notify_driver` from the consumer thread.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `license_plate` | `str` | required | Plate to look up |

**Returns:** `None`

---

##### `_resolve_and_notify_driver(license_plate)`

> Async: resolve the first appointment for the plate and broadcast `status_changed` with `new_status="in_process"` to the driver WS.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `license_plate` | `str` | required | Plate to look up |

**Returns:** `None`

---

##### `_create_app()`

> Factory constructing the FastAPI app: app state, Keycloak client, token validator, CORS middleware, routers, `/health` endpoint, and Prometheus instrumentation.

**Returns:** `FastAPI` — Fully configured application.

---

##### `start()`

> Start the asyncio event loop, spawn the Kafka consumer thread, and run the uvicorn server on `0.0.0.0:{gateway_port}`.

**Returns:** `None`

> ⚠️ **Note:** Calls `self.stop()` on `KeyboardInterrupt` or exit via `finally`.

---

##### `stop()`

> Signal the consumer thread to exit, join it (timeout 5s), close the Kafka consumer, and flush the producer.

**Returns:** `None`

---

## Standalone Functions

> N/A

---

## Configuration & Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `KAFKA_BOOTSTRAP` | ❌ | `localhost:9092` | Kafka bootstrap servers |
| `GATE_IDS` | ❌ | `["1"]` | Master JSON array of gate IDs |
| `DECISION_GATE_IDS` | ❌ | `["1"]` | Entry/inbound gate IDs |
| `INFRACTION_GATE_IDS` | ❌ | `["1"]` | Highway/approach gate IDs |
| `GATEWAY_PORT` | ❌ | `8000` | HTTP listen port |
| `DATA_MODULE_URL` | ❌ | `http://data-module:8000` | Data Module base URL |
| `STREAM_BASE_URL` | ❌ | `http://mediamtx:8888` | HLS stream base URL |
| `STREAM_WEBRTC_BASE_URL` | ❌ | `http://mediamtx:8889` | WebRTC stream base URL |
| `API_PREFIX` | ❌ | `/api` | Router prefix |
| `ENV` | ❌ | `dev` | Environment label |
| `CORS_ALLOW_ORIGINS` | ❌ | `["*"]` | CORS origins |
| `CORS_ALLOW_CREDENTIALS` | ❌ | `True` | CORS credentials flag |
| `CORS_ALLOW_METHODS` | ❌ | `["*"]` | CORS methods |
| `CORS_ALLOW_HEADERS` | ❌ | `["*"]` | CORS headers |
| `KEYCLOAK_URL` | ❌ | `http://keycloak:8080` | Keycloak base URL |
| `KEYCLOAK_REALM` | ❌ | `intelligent-logistics` | Keycloak realm |
| `KEYCLOAK_CLIENT_ID` | ❌ | `api-gateway` | Keycloak client ID |
| `KEYCLOAK_CLIENT_SECRET` | ❌ | `api-gateway-secret` | Keycloak client secret |

---

## Usage Example

```python
from api_gateway import APIGateway, APIGatewayConfig

config = APIGatewayConfig()  # loaded from env
gateway = APIGateway(config=config)
gateway.start()  # Blocks on uvicorn; consumer thread runs in background
```

---

## Error Handling

- Kafka message deserialization errors raise `ValueError`, which is caught and logged as a warning; the consumer loop continues.
- Unexpected exceptions in `_consumer_loop` are caught, logged as errors, and cause the loop to exit via `finally`.
- HTTP lookups to the Data Module (`_resolve_and_notify_driver*`) are wrapped in try/except; non-200 responses, empty result sets, and missing `driver_license` are logged as warnings and return early without raising.
- Messages with undetermined `target_gate` (for non-infraction topics) or missing gate on infraction topics are logged and skipped.
- `stop()` is called from `start()`'s `finally` to guarantee cleanup on interruption.

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| `api_gateway_unit_test.py` | Unit | Configuration loading, topic resolution, HTTP client interactions, message dispatching/broadcasting, and initialization errors |
| `test_gateway.py` | Unit | Core routing functionality and component isolation tests |
| `web_socket_manager_unit_test.py` | Unit | WebSocket connections, disconnections, subscription to gates, role-based driver routing, and broadcast error handling |

To run:
```bash
pytest src/V_APP/api_gateway/tests/
```

---

## Known Issues / TODOs

> N/A

---

## Changelog

> N/A

---

## Related Docs

- [`web_socket_manager.md`](./web_socket_manager.md)
- [`kafka_wrapper.md`](../../shared/kafka_wrapper.md)
- [`kafka_protocol.md`](../../shared/kafka_protocol.md)
- [`keycloak_client.md`](./auth/keycloak_client.md)
- [`token_validator.md`](./auth/token_validator.md)
- [Architecture Overview](../../../docs/sketch_arquitetura/arquitetura_intelligent_logistics.md)
