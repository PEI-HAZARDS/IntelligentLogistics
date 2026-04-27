# `web_socket_manager.py`

> Manages WebSocket registries and broadcasts real-time messages to gate operators and specific driver apps.

---

## Overview

`WebSocketManager` handles active WebSocket connections for the API Gateway. It maintains two distinct registries: one for gate operators (keyed by `gate_id`) and one for drivers (keyed by `drivers_license`). This separation allows the gateway to broadcast general gate state changes and alerts to kiosk UIs, while sending private push-notifications (like acceptance or infraction warnings) directly to individual drivers via their mobile apps.

---

## Location
```
src/V_APP/api_gateway/src/web_socket_manager.py
```

## Dependencies

### Internal
> N/A

### External
| Package | Version | Why it's used |
|---------|---------|---------------|
| `fastapi` | — | `WebSocket` object handling |

---

## Architecture & Flow

```
[API Gateway REST/Kafka Consumers] 
             │
             ├─ broadcast() ──> [Gate 1 WebSocket Clients]
             │
             └─ broadcast_to_driver() ──> [Driver 'AB1234' WebSocket Client]
```

---

## Classes

### `WebSocketManager`

> Maintains two WebSocket registries: `_connections` for gates, and `_driver_connections` for drivers.

**Inherits from:** `None`

**Constructor**
```python
WebSocketManager()
```

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `self._connections` | `Dict[str, Set[WebSocket]]` | Gate operators / kiosk UIs |
| `self._driver_connections` | `Dict[str, Set[WebSocket]]` | Driver mobile apps |

---

#### Methods

##### `connect(gate_id, websocket)`

> Registers a WebSocket as connected to a specific gate.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `gate_id` | `str` | required | The gate ID |
| `websocket` | `WebSocket` | required | FastAPI websocket object |

**Returns:** `None` (async)

---

##### `disconnect(gate_id, websocket)`

> Removes a WebSocket from the gate registry when the client closes the connection.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `gate_id` | `str` | required | The gate ID |
| `websocket` | `WebSocket` | required | FastAPI websocket object |

**Returns:** `None`

---

##### `connect_driver(drivers_license, websocket)`

> Registers a driver WebSocket keyed by their drivers_license.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `drivers_license` | `str` | required | Driver's license string |
| `websocket` | `WebSocket` | required | FastAPI websocket object |

**Returns:** `None` (async)

---

##### `disconnect_driver(drivers_license, websocket)`

> Removes a driver WebSocket.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `drivers_license` | `str` | required | Driver's license string |
| `websocket` | `WebSocket` | required | FastAPI websocket object |

**Returns:** `None`

---

##### `broadcast_to_driver(drivers_license, message)`

> Sends a JSON message to a specific driver.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `drivers_license` | `str` | required | Driver's license string |
| `message` | `dict` | required | JSON payload |

**Returns:** `None` (async)

---

##### `broadcast(gate_ids, message)`

> Sends a JSON message to one or multiple gates.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `gate_ids` | `str \| list[str]` | required | Gate(s) to target |
| `message` | `dict` | required | JSON payload |

**Returns:** `None` (async)

---

## Standalone Functions

> N/A

---

## Configuration & Environment Variables

> N/A

---

## Usage Example

```python
manager = WebSocketManager()

@app.websocket("/ws/gate/{gate_id}")
async def gate_endpoint(websocket: WebSocket, gate_id: str):
    await manager.connect(gate_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(gate_id, websocket)
```

---

## Error Handling

Failed sends internally catch exceptions, log the error, and automatically forcefully disconnect the offending socket, cleaning up the registry.

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| `web_socket_manager_unit_test.py` | Unit | Connection management, driver connections, broadcasting behavior, exception safety |

To run:
```bash
pytest src/V_APP/api_gateway/tests/web_socket_manager_unit_test.py
```

---

## Known Issues / TODOs

> N/A

---

## Changelog

> N/A

---

## Related Docs

- [`api_gateway.md`](./api_gateway.md)
