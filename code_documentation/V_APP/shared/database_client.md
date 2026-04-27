# `database_client.py`

> HTTP client for the V_APP scheduling REST API that queries appointment candidates.

---

## Overview

`DatabaseClient` is a thin wrapper around the Python `requests` library. It interacts with the Data Module (`/api/v1/decisions/query-appointments`) to fetch truck appointment candidates for a specific gate. By wrapping the HTTP calls, it guarantees that all network errors or non-200 responses are caught internally and surfaced as structured, consistent error payloads `{"found": False, "candidates": [], "message": ...}`. This prevents network errors from bubbling up as exceptions and crashing the decision engines that rely on it.

---

## Location
```
src/V_APP/shared/src/database_client.py
```

## Dependencies

### Internal
> N/A

### External
| Package | Version | Why it's used |
|---------|---------|---------------|
| `requests` | — | Synchronous HTTP calls |

---

## Architecture & Flow

```
[DecisionEngine / InfractionEngine] 
             │
             ▼
  DatabaseClient.get_appointments()
             │
             ├─ HTTP POST → Data Module (/decisions/query-appointments)
             │
             └─ Parses response and returns standard payload dictionary
```

---

## Classes

### `DatabaseClient`

> HTTP client for querying scheduled truck appointments from the API.

**Inherits from:** `None`

**Constructor**
```python
DatabaseClient(api_url: str, gate_id: str = "")
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `api_url` | `str` | required | Base URL of the scheduling REST API |
| `gate_id` | `str` | `""` | Gate ID for the appointment query |

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `self.api_url` | `str` | Base API URL |
| `self.gate_id` | `str` | Gate ID |

---

#### Methods

##### `get_appointments()`

> Query the API for all appointment candidates in the current time window for `self.gate_id`.

**Parameters**
> N/A

**Returns:** `dict` — Parsed JSON body on success, or a standardized error dictionary `{"found": False, "candidates": [], "message": ...}` on failure.

---

##### `is_api_unavailable(api_message)`

> Determine whether an error message indicates a connectivity failure.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `api_message` | `str` | required | The `message` field from `get_appointments()` |

**Returns:** `bool` — `True` if it contains "Connection refused" or "Max retries".

---

## Standalone Functions

> N/A

---

## Configuration & Environment Variables

`api_url` is typically provided by `BaseDecisionEngineConfig.api_url` (default: `http://localhost:8080/api/v1`).

---

## Usage Example

```python
from V_APP.shared.src.database_client import DatabaseClient

client = DatabaseClient(api_url="http://api-gateway:8080/api/v1", gate_id="1")
result = client.get_appointments()

if result.get("found"):
    candidates = result.get("candidates", [])
```

---

## Error Handling

The client catches all `requests.exceptions.RequestException` and generic `Exception` types internally. Instead of raising, it returns a standard error dictionary to the caller, mapping network failures smoothly into business logic rejections (e.g. `MANUAL_REVIEW`).

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| `database_client_unitTest.py` | Unit | Successful responses, non-200 responses, network connection errors, and `is_api_unavailable` logic |

To run:
```bash
pytest src/V_APP/shared/tests/database_client_unitTest.py
```

---

## Known Issues / TODOs

> N/A

---

## Changelog

> N/A

---

## Related Docs

- [`base_decision_engine.md`](./base_decision_engine.md)
