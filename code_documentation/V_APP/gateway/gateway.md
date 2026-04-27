# `v_gateway.py`

> V_APP-side gateway that bridges the V_APP Kafka broker with the AI_APP Kafka broker over HTTP.

---

## Overview

`VGateway` is the V_APP half of the inter-app bridge between the V_APP and AI_APP microservices. It extends `BaseGateway` to consume reset commands produced locally by `V_Brain` on the V_APP Kafka broker and forward them over HTTP to the AI-side gateway (`AI_Gateway`), which then republishes them on the AI_APP broker for consumption by `AgentA`. In the opposite direction, it declares the AI-originated topics (`truck-detected`, `lp-results`, `hz-results`) that `AI_Gateway` forwards to it, which `VGateway` then republishes onto the V_APP broker for `V_Brain`, the Decision Engine, and the Infraction Engine.

The module itself only defines the per-gateway configuration hooks required by `BaseGateway`: which topics to consume, which topics to produce, the gateway's name, its downstream HTTP receivers, and an optional message-transformation hook. All Kafka I/O, HTTP forwarding, and lifecycle management live in `BaseGateway`.

Boundaries: this file does not perform Kafka connection setup, HTTP calls, retries, threading, or payload serialization — those responsibilities belong to `BaseGateway` and the shared Kafka wrappers.

---

## Location
```
src/V_APP/gateway/src/v_gateway.py
```

## Dependencies

### Internal
| Module | Why it's used |
|--------|---------------|
| `shared/src/base_gateway.py` | Base class implementing Kafka consumption, HTTP forwarding, and lifecycle |
| `shared/src/kafka_protocol.py` | `Message` base type and `KafkaTopicFactory` for per-gate topic names |

### External
> N/A

---

## Architecture & Flow

```
V_Brain → [reset-agentA-{gate_id}] → VGateway → HTTP → AI_Gateway → [reset-agentA-{gate_id}] → AgentA

AgentA/B/C → [truck-detected / lp-results / hz-results] → AI_Gateway → HTTP → VGateway
          → [truck-detected / lp-results / hz-results] → V_Brain / Decision Engine / Infraction Engine
```

---

## Classes

### `VGateway`

> Concrete gateway for the V_APP side of the AI_APP ↔ V_APP HTTP bridge.

**Inherits from:** `BaseGateway`

**Constructor**

> N/A — inherited from `BaseGateway`; no constructor override is defined in this module.

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `self.config` | gateway config object | Provides `gate_ids` and `receivers`; supplied by `BaseGateway` |
| `self.logger` | `Logger` | Logger supplied by `BaseGateway` |

---

#### Methods

##### `get_topics_consume()`

> Returns the list of V_APP-broker topics this gateway consumes.

**Parameters**
> N/A

**Returns:** `list[str]` — One `reset-agentA-{gate_id}` topic per configured gate, produced by `V_Brain` and destined for `AgentA` via `AI_Gateway`.

**Raises:**
> N/A

**Example**
```python
gw = VGateway(config)
gw.get_topics_consume()
# → ["reset-agentA-1", "reset-agentA-2"]
```

---

##### `get_gateway_name()`

> Returns the human-readable name of this gateway.

**Parameters**
> N/A

**Returns:** `str` — The literal `"V_Gateway"`.

**Example**
```python
VGateway(config).get_gateway_name()  # → "V_Gateway"
```

---

##### `get_topics_produce()`

> Returns the mapping from source (AI-broker) topic to destination (V-broker) topic used when republishing messages received over HTTP from `AI_Gateway`.

**Parameters**
> N/A

**Returns:** `dict[str, str]` — Keys are source topic names on the AI broker, values are the destination topic names on the V broker. For each configured gate, maps `truck-detected`, `lp-results`, and `hz-results` identically.

**Example**
```python
VGateway(config).get_topics_produce()
# → {
#     "truck-detected-1": "truck-detected-1",
#     "lp-results-1":     "lp-results-1",
#     "hz-results-1":     "hz-results-1",
#   }
```

> ⚠️ **Note:** Keys include the full per-gate topic name so routing remains unambiguous when multiple gates are configured.

---

##### `get_receivers()`

> Returns the list of downstream HTTP endpoints (typically `AI_Gateway`) that consumed messages should be forwarded to.

**Parameters**
> N/A

**Returns:** `list[str]` — Value of `self.config.receivers`.

**Example**
```python
VGateway(config).get_receivers()
# → ["http://AI_Gateway:8001/forward"]
```

---

##### `process_message(message)`

> Hook for transforming messages before forwarding. Currently a no-op that only logs.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `message` | `Message` | required | Decoded Kafka message from one of the consumed topics |

**Returns:** `Message` — The input message, unchanged.

**Example**
```python
out = gw.process_message(msg)
assert out is msg
```

> ⚠️ **Note:** Override point; any future enrichment, filtering, or redaction should be implemented here.

---

## Standalone Functions

> N/A

---

## Configuration & Environment Variables

> N/A — configuration is read by `BaseGateway`/the gateway config class, not this module. Relevant fields accessed here are `config.gate_ids` and `config.receivers`.

---

## Usage Example

```python
from V_APP.gateway.src.v_gateway import VGateway
from V_APP.gateway.src.config import VGatewayConfig

config = VGatewayConfig()  # reads gate_ids, receivers, Kafka, HTTP from env
gateway = VGateway(config)
gateway.start()
```

---

## Error Handling

No error handling is implemented in this module. All Kafka consumption, HTTP forwarding, and exception containment are delegated to `BaseGateway`. `process_message` performs only a log call and returns the message unchanged.

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| `src/V_APP/gateway/tests/` | Unit | Gateway hook returns (topics, name, receivers, passthrough) |

To run:
```bash
pytest src/V_APP/gateway/tests/
```

---

## Known Issues / TODOs

- [ ] `process_message` currently logs and returns the message unchanged ("For now, we just log the message and return it unchanged.") — reserved for future pre-forward processing.

---

## Changelog

> N/A

---

## Related Docs

- [`base_gateway.md`](../../shared/base_gateway.md)
- [`kafka_protocol.md`](../../../shared/kafka_protocol.md)
- [Architecture Overview](../../../docs/sketch_arquitetura/arquitetura_intelligent_logistics.md)
