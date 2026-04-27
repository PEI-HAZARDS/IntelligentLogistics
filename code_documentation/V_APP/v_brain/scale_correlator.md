# `scale_correlator.py`

> Tracks per-truck state across multiple detection events to decide when a truck's processing is complete.

---

## Overview

`ScaleCorrelator` is a state-management utility used exclusively by `VBrain`. Because the detection pipeline uses multiple asynchronous agents (`AgentA` for trucks, `AgentB` for license plates, `AgentC` for hazard plates), `VBrain` needs to track the progress of a specific truck. The correlator maintains a dictionary keyed by `truck_id`, keeping track of which results have been received. When both LP and HZ results are available, or a final decision is made, the truck is considered "complete", enabling `VBrain` to scale down streams and clean up tracking state. It also provides a timeout mechanism to clear stale entries.

---

## Location
```
src/V_APP/v_brain/src/scale_correlator.py
```

## Dependencies

### Internal
> N/A

### External
> N/A

> Standard library modules used: `time`, `logging`, `typing`.

---

## Architecture & Flow

```
[VBrain]
   ├─ truck_detected(truck_id)   → Initializes state {lp: False, hz: False, decided: False, ts: time.time()}
   ├─ lp_received(truck_id)      → Sets lp: True, returns True if both LP and HZ are complete
   ├─ hz_received(truck_id)      → Sets hz: True, returns True if both LP and HZ are complete
   ├─ decision_received(truck_id)→ Sets decided: True, returns True
   └─ check_timeouts()           → Scans state for expired timestamps and returns stale truck_ids
```

---

## Classes

### `ScaleCorrelator`

> Tracks per-truck state to decide when to scale down and reset.

**Inherits from:** `None`

**Constructor**
```python
ScaleCorrelator(timeout_seconds: int = 30)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timeout_seconds` | `int` | `30` | Number of seconds before a truck is considered timed out |

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `self._state` | `dict[str, dict]` | Map of `truck_id` to its state dict |
| `self._timeout` | `int` | Timeout threshold |

---

#### Methods

##### `truck_detected(truck_id, gate_id)`

> Registers a new truck. Called when a truck-detected message arrives.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `truck_id` | `str` | required | Truck ID |
| `gate_id` | `str` | required | Gate ID |

**Returns:** `None`

---

##### `lp_received(truck_id)`

> Marks LP results as received.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `truck_id` | `str` | required | Truck ID |

**Returns:** `bool` — `True` if both LP and HZ are now complete.

---

##### `hz_received(truck_id)`

> Marks HZ results as received.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `truck_id` | `str` | required | Truck ID |

**Returns:** `bool` — `True` if both LP and HZ are now complete.

---

##### `decision_received(truck_id)`

> Marks that an agent-decision was received for this truck.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `truck_id` | `str` | required | Truck ID |

**Returns:** `bool` — Always returns `True` (ready to scale down after a decision).

---

##### `check_timeouts()`

> Returns a list of `truck_id`s that have exceeded the timeout without completing results or receiving a decision.

**Parameters**
> N/A

**Returns:** `list[str]` — List of timed-out truck IDs.

---

##### `remove(truck_id)`

> Removes a truck from tracking.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `truck_id` | `str` | required | Truck ID |

**Returns:** `None`

---

## Standalone Functions

> N/A

---

## Configuration & Environment Variables

> N/A. Configurations like timeout are passed through the constructor by `VBrain`.

---

## Usage Example

```python
from v_brain.src.scale_correlator import ScaleCorrelator

correlator = ScaleCorrelator(timeout_seconds=30)
correlator.truck_detected("TRK-1", "gate-1")
ready = correlator.lp_received("TRK-1") # False
ready = correlator.hz_received("TRK-1") # True
correlator.remove("TRK-1")
```

---

## Error Handling

Invalid `truck_id`s passed to methods log a warning but do not throw exceptions. Timeouts are checked safely using the current system time.

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| `scale_correlator_unit_test.py` | Unit | State transitions, timeouts, missing truck handling, gate extraction |

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

- [`v_brain.md`](./v_brain.md)
