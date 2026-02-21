# `agentA.py`

> Continuously monitors a low-quality RTMP stream, detects trucks using YOLO, and publishes detection events to a gate-specific Kafka topic.

---

## Overview

`agentA.py` implements the first stage of the intelligent logistics pipeline. It connects to a low-bitrate RTMP stream (sourced from NGINX) for a specific gate, runs per-frame truck detection using a YOLO model via `ObjectDetector`, and emits a Kafka event whenever a truck is confirmed present and the configurable debounce interval has elapsed.

The module pairs `StreamManager` (frame acquisition), `ObjectDetector` (YOLO inference), `BoundingBoxDrawer` (annotation), `ImageStorage` (MinIO upload of annotated frames), and `KafkaProducerWrapper` (event publishing). Configuration is handled entirely through `AgentAConfig`, a Pydantic `BaseSettings` subclass that reads values from environment variables. Prometheus metrics are registered at module level and exposed on the container's metrics port.

Agent A does **not** perform license plate recognition, hazard classification, or any downstream decision logic — those responsibilities belong to Agent B, Agent C, and the decision engine respectively.

---

## Location
```
src/AI_APP/agentA/src/agentA.py
```

## Dependencies

### Internal
| Module | Why it's used |
|--------|---------------|
| `shared/src/stream_manager.py` | Acquires video frames from the RTMP stream |
| `shared/src/object_detector.py` | Runs YOLO inference to detect trucks |
| `shared/src/bounding_box_drawer.py` | Draws annotated bounding boxes on detected frames |
| `shared/src/image_storage.py` | Uploads annotated frames to MinIO |
| `shared/src/kafka_wrapper.py` | Publishes detection events to Kafka |
| `shared/src/kafka_protocol.py` | Constructs typed Kafka messages and resolves topic names |

### External
| Package | Version | Why it's used |
|---------|---------|---------------|
| `ultralytics` | `>=8.3.0` | YOLO model loading and inference (via `ObjectDetector`) |
| `opencv-python-headless` | `>=4.12.0.88` | Frame decoding and image operations |
| `confluent_kafka` | `2.12.2` | Underlying Kafka client used by `KafkaProducerWrapper` |
| `prometheus_client` | latest | Exposes inference latency, frame count, and detection metrics |
| `pydantic-settings` | latest | Environment-variable-based configuration via `AgentAConfig` |
| `minio` | latest | Object storage client used by `ImageStorage` |
| `pillow` | `12.0.0` | Image encoding for MinIO uploads |
| `torch` | `2.4.1+cpu` | PyTorch CPU runtime required by YOLO |

---

## Architecture & Flow

```
[NGINX RTMP stream]
        │
        ▼
  StreamManager.read()
        │  frame
        ▼
  ObjectDetector.detect()   ←── truck_model.pt
        │  results
        ▼
  object_found()?
   ├─ No  → discard frame
   └─ Yes → debounce check
                │ elapsed >= message_interval
                ▼
         BoundingBoxDrawer.draw_box()
                │  annotated frame
                ▼
         ImageStorage.upload_memory_image()  →  [MinIO]
                │
                ▼
         KafkaProducerWrapper.produce()      →  [truck-detected-<GATE_ID>]
```

---

## Classes

### `AgentAConfig`

> Pydantic `BaseSettings` subclass that defines all runtime configuration for Agent A, reading values from environment variables.

**Inherits from:** `BaseSettings` (`pydantic_settings`)

**Constructor**
```python
AgentAConfig()
```

No explicit constructor parameters — all fields are populated from environment variables (see [Configuration & Environment Variables](#configuration--environment-variables)).

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `kafka_bootstrap` | `str` | Kafka broker address. Default: `"10.255.32.143:9092"` |
| `nginx_host` | `str` | NGINX RTMP server hostname. Default: `"10.255.32.56"` |
| `nginx_port` | `int` | NGINX RTMP server port. Default: `1935` |
| `minio_host` | `str` | MinIO server hostname. Default: `"10.255.32.82"` |
| `minio_port` | `int` | MinIO server port. Default: `9000` |
| `minio_user` | `str` | MinIO access key (required) |
| `minio_password` | `str` | MinIO secret key (required) |
| `minio_secure` | `bool` | Whether MinIO connection uses TLS. Default: `False` |
| `gate_id` | `str` | Gate identifier used for topic naming and bucket naming. Default: `"1"` |
| `models_path` | `str` | Filesystem path to the directory containing model files. Default: `"/app/AI_APP/agentA/data"` |
| `message_interval` | `float` | Minimum seconds between consecutive Kafka publish events (debounce). Default: `35.0` |

---

#### Methods

##### `stream_low` *(property)*

> Returns the RTMP stream URL for the low-quality feed of the configured gate.

**Parameters**

> N/A

**Returns:** `str` — URL in the form `rtmp://<nginx_host>:<nginx_port>/streams_low/gate<gate_id>`.

**Raises:**

> N/A

**Example**
```python
config = AgentAConfig()
print(config.stream_low)
# → "rtmp://10.255.32.56:1935/streams_low/gate1"
```

---

##### `minio_bucket_name` *(property)*

> Returns the MinIO bucket name scoped to the configured gate.

**Parameters**

> N/A

**Returns:** `str` — Bucket name in the form `agenta-<gate_id>`.

**Raises:**

> N/A

**Example**
```python
config = AgentAConfig()
print(config.minio_bucket_name)
# → "agenta-1"
```

---

##### `minio_config` *(property)*

> Returns a dict suitable for constructing an `ImageStorage` instance.

**Parameters**

> N/A

**Returns:** `dict` — `{"endpoint": str, "access_key": str, "secret_key": str, "secure": bool}`.

**Raises:**

> N/A

**Example**
```python
config = AgentAConfig()
storage = ImageStorage(config.minio_config, config.minio_bucket_name)
```

---

##### `kafka_topic_produce` *(property)*

> Returns the Kafka topic name on which Agent A publishes truck-detected events.

**Parameters**

> N/A

**Returns:** `str` — Topic name produced by `KafkaTopicFactory.truck_detected(gate_id)`.

**Raises:**

> N/A

**Example**
```python
config = AgentAConfig()
print(config.kafka_topic_produce)
# → "truck-detected-1"
```

---

##### `kafka_topic_consume` *(property)*

> Returns the list of Kafka topics Agent A is configured to consume (agent-decision topic for the gate).

**Parameters**

> N/A

**Returns:** `List[str]` — Single-element list produced by `KafkaTopicFactory.agent_decision(gate_id)`.

**Raises:**

> N/A

**Example**
```python
config = AgentAConfig()
print(config.kafka_topic_consume)
# → ["agent-decision-1"]
```

---

### `AgentA`

> Orchestrates the truck detection loop: reads frames, runs YOLO inference, uploads annotated images, and publishes Kafka events.

**Inherits from:** `None`

**Constructor**
```python
AgentA(
    config: AgentAConfig,
    object_detector: Optional[ObjectDetector] = None,
    stream_manager: Optional[StreamManager] = None,
    kafka_producer: Optional[KafkaProducerWrapper] = None,
    image_storage: Optional[ImageStorage] = None,
    drawer: Optional[BoundingBoxDrawer] = None,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `AgentAConfig` | required | Full runtime configuration |
| `object_detector` | `Optional[ObjectDetector]` | `None` | YOLO detector; instantiated from `config.models_path/truck_model.pt` if not provided |
| `stream_manager` | `Optional[StreamManager]` | `None` | Frame source; instantiated from `config.stream_low` if not provided |
| `kafka_producer` | `Optional[KafkaProducerWrapper]` | `None` | Kafka producer; instantiated from `config.kafka_bootstrap` if not provided |
| `image_storage` | `Optional[ImageStorage]` | `None` | MinIO client; instantiated from `config.minio_config` and `config.minio_bucket_name` if not provided |
| `drawer` | `Optional[BoundingBoxDrawer]` | `None` | Bounding box annotator; defaults to green box labelled `"truck"` with thickness 2 |

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `config` | `AgentAConfig` | Runtime configuration |
| `yolo` | `ObjectDetector` | YOLO inference wrapper |
| `drawer` | `BoundingBoxDrawer` | Annotates frames with bounding boxes |
| `image_storage` | `ImageStorage` | Uploads annotated frames to MinIO |
| `stream_manager` | `StreamManager` | Reads frames from the RTMP stream |
| `kafka_producer` | `KafkaProducerWrapper` | Publishes events to Kafka |
| `running` | `bool` | Loop control flag; `True` on init |
| `last_message_time` | `float` | Unix timestamp of the last published Kafka event; `0` on init |
| `inference_latency` | `Histogram` | Prometheus histogram for per-frame YOLO inference duration |
| `frames_processed` | `Counter` | Prometheus counter for total frames processed |
| `trucks_detected` | `Counter` | Prometheus counter for total trucks detected |
| `detection_confidence` | `Histogram` | Prometheus histogram for detection confidence scores |

---

#### Methods

##### `start()`

> Runs the main frame-acquisition and detection loop until `self.running` is `False`.

**Parameters**

> N/A

**Returns:** `None`

**Raises:**
- Any unhandled exception within the loop is caught, logged with `logger.exception`, and the loop sleeps 1 second before retrying.

**Example**
```python
config = AgentAConfig()
agent = AgentA(config)
agent.start()  # blocks indefinitely
```

> ⚠️ **Note:** `None` frames from `StreamManager.read()` cause a 0.1 s sleep and loop continuation without calling `_process_detection`.

---

##### `stop()`

> Sets `running = False` and calls `_cleanup()` to release all resources.

**Parameters**

> N/A

**Returns:** `None`

**Raises:**

> N/A

**Example**
```python
agent.stop()
```

---

##### `_cleanup()`

> Releases the stream, flushes, and closes the Kafka producer.

**Parameters**

> N/A

**Returns:** `None`

**Raises:**

> N/A

**Example**
```python
agent._cleanup()
```

---

##### `_process_detection(frame)`

> Runs YOLO inference on a single frame; if a truck is detected and the debounce interval has elapsed, uploads an annotated image and publishes a Kafka event.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `frame` | `unknown` (numpy array expected) | required | Raw video frame from `StreamManager.read()` |

**Returns:** `None`

**Raises:**
- Internal exceptions (inference errors, Kafka publish errors) are caught and logged with `logger.exception`; drawing/upload errors are caught separately and do not suppress the Kafka publish.

**Example**
```python
import numpy as np
frame = np.zeros((480, 640, 3), dtype=np.uint8)
agent._process_detection(frame)
```

> ⚠️ **Note:** If `ObjectDetector.detect()` returns `None`, the method logs a warning and returns early without publishing. Drawing/upload failures are isolated — a Kafka event is still attempted even if image annotation fails.

---

## Standalone Functions

> N/A

---

## Configuration & Environment Variables

All variables are read by `AgentAConfig` via Pydantic `BaseSettings` (env var names are uppercased field names).

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `KAFKA_BOOTSTRAP` | ❌ | `10.255.32.143:9092` | Kafka broker address |
| `NGINX_HOST` | ❌ | `10.255.32.56` | NGINX RTMP server hostname |
| `NGINX_PORT` | ❌ | `1935` | NGINX RTMP server port |
| `MINIO_HOST` | ❌ | `10.255.32.82` | MinIO server hostname |
| `MINIO_PORT` | ❌ | `9000` | MinIO server port |
| `MINIO_USER` | ✅ | — | MinIO access key |
| `MINIO_PASSWORD` | ✅ | — | MinIO secret key |
| `MINIO_SECURE` | ❌ | `False` | Enable TLS for MinIO connection |
| `GATE_ID` | ❌ | `1` | Gate identifier; scopes Kafka topics and MinIO bucket |
| `MODELS_PATH` | ❌ | `/app/AI_APP/agentA/data` | Directory containing `truck_model.pt` |
| `MESSAGE_INTERVAL` | ❌ | `35.0` | Minimum seconds between Kafka publish events (debounce) |

---

## Usage Example

```python
from agentA import AgentA, AgentAConfig

config = AgentAConfig()  # reads from environment
agent = AgentA(config)
agent.start()
```

For dependency injection (e.g. in tests):
```python
from unittest.mock import MagicMock
from agentA import AgentA

agent = AgentA(
    object_detector=MagicMock(),
    stream_manager=MagicMock(),
    kafka_producer=MagicMock(),
    image_storage=MagicMock(),
    drawer=MagicMock(),
)
agent.running = False
```

---

## Error Handling

- **Model load failure** (`FileNotFoundError`, `RuntimeError` during `ObjectDetector` construction): logged as `CRITICAL` and re-raised as `SystemExit(1)` — the process terminates immediately.
- **Frame loop exceptions**: caught by a broad `except Exception` in `start()`; logged with `logger.exception` and the loop sleeps 1 second before resuming.
- **Drawing / upload errors** inside `_process_detection`: caught by an inner `except Exception`; logged with `logger.exception`; Kafka publish is still attempted.
- **Kafka publish errors** (outer `except Exception` in `_process_detection`): caught and logged with `logger.exception`; the loop continues.

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| `agentA_unitTest.py` | Unit | Initialization, truck detection logic, throttling/debounce, Kafka publish, image upload, drawing error isolation, Kafka error isolation, loop frame handling |

To run:
```bash
pytest src/AI_APP/agentA/tests/
```

---

## Known Issues / TODOs

> Consume agent/operator messages instead of hardcoded 35 seconds intervals

---

## Changelog

> N/A

---

## Related Docs

- [`stream_manager.md`](./stream_manager.md)
- [`object_detector.md`](./object_detector.md)
- [`bounding_box_drawer.md`](./bounding_box_drawer.md)
- [`image_storage.md`](./image_storage.md)
- [`kafka_wrapper.md`](./kafka_wrapper.md)
- [`kafka_protocol.md`](./kafka_protocol.md)
- [Architecture Overview](../docs/sketch_arquitetura/arquitetura_intelligent_logistics.md)
