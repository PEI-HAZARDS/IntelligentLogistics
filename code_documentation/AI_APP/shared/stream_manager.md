# `stream_manager.py`

> Self-healing video stream manager that continuously reads frames from RTSP/RTMP sources via FFmpeg and automatically reconnects on stream loss.

---

## Overview

`StreamManager` provides a thread-safe, resilient abstraction over OpenCV's `VideoCapture` for consuming live video streams. It runs a background daemon thread that continuously reads frames and exposes them to consumers via a lock-protected `read()` method.

The module is designed for the IntelligentLogistics pipeline, where AI agents (e.g. `AgentA`) need a steady supply of video frames from MediaMTX RTSP streams. `StreamManager` decouples frame acquisition from frame processing: agents simply call `read()` and receive the latest frame (or `None` while reconnecting), while the manager handles all connection lifecycle concerns — initial connection, retry-with-backoff, reconnection after stream loss, and graceful shutdown.

It does **not** perform any frame processing, detection, or publishing. Those responsibilities belong to the consuming agents and their supporting modules (`object_detector`, `kafka_wrapper`, etc.).

---

## Location
```
src/AI_APP/shared/src/stream_manager.py
```

## Dependencies

### Internal
> N/A

### External
| Package | Version | Why it's used |
|---------|---------|---------------|
| `opencv-python` | `4.x` | Video capture via `cv2.VideoCapture` with the FFmpeg backend |

> Standard library modules used: `threading`, `time`, `logging`.

---

## Architecture & Flow

Illustrates the internal lifecycle of a `StreamManager` instance and its relationship to consuming agents.

```
  AgentA / Consumer
       │
       │  read()  (thread-safe, returns latest frame or None)
       ▼
 ┌─────────────┐
 │StreamManager │
 │              │
 │  .frame      │◄──── update thread (daemon)
 │  .lock       │         │
 └─────────────┘         │
                          ▼
                 ┌──────────────────┐
                 │ cv2.VideoCapture  │
                 │ (CAP_FFMPEG)      │
                 └──────────────────┘
                          │
                          ▼
                 RTMP / RTSP Source
```

**Flow:**
1. On instantiation, a daemon thread starts and calls `_connect_with_retry()` to open the stream.
2. The thread enters the `update()` loop, continuously calling `cap.read()`.
3. Successful reads update the shared `self.frame` under a lock.
4. On consecutive read failures (default 10), `_reconnect()` releases old resources, clears the frame, and retries the connection.
5. Consumers call `read()` at any time to get a thread-safe copy of the latest frame.
6. `release()` signals the thread to stop and cleans up the capture.

---

## Classes

### `StreamManager`

> Generic, self-healing video stream manager. Supports RTSP, RTMP, and other protocols via FFmpeg. Automatically reconnects in the background if the stream is lost.

**Inherits from:** `None`

**Constructor**
```python
StreamManager(url: str, max_retries: int = 10, retry_delay: int = 5)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | `str` | required | Stream URL (e.g. `rtsp://host:port/streams_low/gate1`) |
| `max_retries` | `int` | `10` | Maximum connection attempts before giving up |
| `retry_delay` | `int` | `5` | Seconds to wait between retry attempts |

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `self.url` | `str` | The stream URL to connect to |
| `self.max_retries` | `int` | Maximum connection retry attempts |
| `self.retry_delay` | `int` | Delay in seconds between retries |
| `self.cap` | `cv2.VideoCapture \| None` | Current OpenCV video capture instance |
| `self.frame` | `numpy.ndarray \| None` | Latest frame read from the stream |
| `self.lock` | `threading.Lock` | Lock guarding access to `self.frame` |
| `self.running` | `bool` | Flag controlling the background thread loop |
| `self.thread` | `threading.Thread` | Daemon thread running `update()` |

> ⚠️ **Note:** The constructor immediately starts the background thread. The initial stream connection is handled by the thread, not by the constructor itself.

---

#### Methods

##### `read()`

> Returns a thread-safe copy of the most recent frame, or `None` if the stream is connecting/reconnecting.

**Parameters**

> N/A

**Returns:** `numpy.ndarray | None` — A copy of the latest frame, or `None` if no frame is available.

**Raises:**

> N/A

**Example**
```python
from shared.src.stream_manager import StreamManager

manager = StreamManager("rtsp://10.255.32.56:8554/streams_low/gate1")

frame = manager.read()
if frame is not None:
    # Process the frame
    pass
```

> ⚠️ **Note:** Returns a `.copy()` of the internal frame to prevent race conditions. Callers should handle the `None` case (stream connecting or reconnecting).

---

##### `release()`

> Stops the background thread and releases the video capture resources.

**Parameters**

> N/A

**Returns:** `None`

**Raises:**

> N/A

**Example**
```python
manager = StreamManager("rtsp://host:8554/streams_low/gate1")
# ... use manager ...
manager.release()
```

> ⚠️ **Note:** Joins the background thread with a 1-second timeout. After calling `release()`, the instance should not be reused.

---

##### `update()`

> Background thread entry point. Reads frames continuously and handles reconnection on failure.

**Parameters**

> N/A

**Returns:** `None`

**Raises:**

> N/A

> ⚠️ **Note:** This method is intended to run on the daemon thread started in `__init__`. It loops indefinitely until `self.running` is set to `False`. It uses an internal consecutive-failure counter (max 10) to decide when to trigger a full reconnect.

---

##### `_connect_with_retry()`

> Attempts to connect to the stream URL with automatic retry logic. Blocks until connected or max retries exhausted.

**Parameters**

> N/A

**Returns:** `cv2.VideoCapture | None` — A connected capture object, or `None` if all retries failed.

**Raises:**

> N/A (exceptions during connection are caught and logged internally)

> ⚠️ **Note:** Uses `cv2.CAP_FFMPEG` backend and sets `CAP_PROP_BUFFERSIZE` to `1` for low-latency capture. Respects `self.running` — exits early if the manager is stopped during retries.

---

##### `_reconnect()`

> Releases the current capture, clears the shared frame, and attempts a new connection via `_connect_with_retry()`.

**Parameters**

> N/A

**Returns:** `None`

**Raises:**

> N/A

> ⚠️ **Note:** Sets `self.frame = None` under the lock so that consumers calling `read()` will receive `None` during the reconnection window.

---

##### `_ensure_connection_active()`

> Checks if the current connection is alive. Triggers `_reconnect()` if the capture is `None` or not opened.

**Parameters**

> N/A

**Returns:** `bool` — `True` if a valid connection exists after the check, `False` otherwise.

**Raises:**

> N/A

---

##### `_handle_read_success(frame)`

> Updates the shared frame under the thread lock.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `frame` | `numpy.ndarray` | required | The successfully read video frame |

**Returns:** `None`

**Raises:**

> N/A

---

##### `_handle_read_failure(current_failures, max_failures)`

> Handles a failed frame read. Increments the failure counter, and triggers a full reconnect if the maximum threshold is reached.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `current_failures` | `int` | required | Current consecutive failure count |
| `max_failures` | `int` | required | Threshold to trigger reconnection |

**Returns:** `int` — Updated failure count (reset to `0` after a reconnect, otherwise `current_failures + 1`).

**Raises:**

> N/A

> ⚠️ **Note:** Sleeps for 0.1 seconds on a transient glitch (below max threshold) to avoid busy-spinning.

---

## Standalone Functions

> N/A

---

## Configuration & Environment Variables

> N/A

> `StreamManager` itself does not read environment variables. The stream URL and connection parameters are passed in by the caller. Consuming modules like `agentA.py` resolve environment variables (`MEDIAMTX_HOST`, `MEDIAMTX_PORT`, `GATE_ID`) to construct the URL before instantiating `StreamManager`.

---

## Usage Example

End-to-end usage as seen in `AgentA`:
```python
import os
from AI_APP.shared.src.stream_manager import StreamManager

# Build the stream URL from environment
MEDIAMTX_HOST = os.getenv("MEDIAMTX_HOST", "10.255.32.56")
MEDIAMTX_PORT = os.getenv("MEDIAMTX_PORT", "8554")
GATE_ID = os.getenv("GATE_ID", "1")
STREAM_URL = f"rtsp://{MEDIAMTX_HOST}:{MEDIAMTX_PORT}/streams_low/gate{GATE_ID}"

# Create the manager (background thread starts immediately)
manager = StreamManager(STREAM_URL, max_retries=10, retry_delay=5)

# Main processing loop
try:
    while True:
        frame = manager.read()
        if frame is None:
            continue
        # ... process frame (detection, OCR, etc.) ...
finally:
    manager.release()
```

Deployment reference (April 2026):
- `GPU_AI_APP` host: `10.255.32.107`
- `Streaming Middleware` host: `10.255.32.56` (MediaMTX)
- `V_APP` host: `10.255.32.70`
- `UI` host: `10.255.32.108`

---

## Error Handling

All exceptions during the stream lifecycle are caught and logged internally — the module never propagates exceptions to the caller:

- **Connection errors** in `_connect_with_retry()` are caught per-attempt and logged at `ERROR` level. After exhausting `max_retries`, the method returns `None`.
- **Read errors** in the `update()` loop are caught and trigger `_reconnect()`. The exception is logged via `logger.exception()`.
- **Release errors** when calling `cap.release()` during reconnection are silently caught (`except Exception: pass`) to ensure cleanup proceeds.
- **Frame availability** — consumers are expected to handle `None` returns from `read()` (the module does not raise on missing frames).

Logging uses a named logger (`StreamManager`) at `INFO`, `WARNING`, `DEBUG`, and `ERROR` levels.

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| `stream_manager_unit_test.py` | Unit | Initialization, connection retry logic, reconnection handling, frame reading, resource cleanup, internal helper methods |

To run:
```bash
pytest src/AI_APP/shared/tests/stream_manager_unit_test.py
```

---

## Known Issues / TODOs

> N/A

---

## Changelog

| Version / Date | Change |
|----------------|--------|
| `2026-04-18` | Reviewed AI_APP documentation for consistency, aligned paths/test commands, and validated deployment host mapping (AI_APP `10.255.32.107`, Streaming `10.255.32.56`, UI `10.255.32.108`, V_APP `10.255.32.70`). |

---

## Related Docs

- [`agentA.md`](../agentA/agentA.md) — Primary consumer of `StreamManager`
- [`template.md`](../../template.md) — Documentation template
