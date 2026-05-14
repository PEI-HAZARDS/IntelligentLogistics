# `agentA.py`

> Continuously monitors a low-quality RTSP stream, detects trucks using YOLO, and publishes detection events to a gate-specific Kafka topic.

---

## Overview

`agentA.py` implements the first stage of the intelligent logistics pipeline. It connects to a low-bitrate RTSP stream (sourced from MediaMTX) for a specific gate, runs per-frame truck detection using a YOLO model via `ObjectDetector`, and emits a Kafka event whenever a truck is confirmed present.

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
| `AI_APP/shared/src/stream_manager.py` | Acquires video frames from the RTSP stream |
| `AI_APP/shared/src/object_detector.py` | Runs YOLO inference to detect trucks |
| `AI_APP/shared/src/bounding_box_drawer.py` | Draws annotated bounding boxes on detected frames |
| `AI_APP/shared/src/image_storage.py` | Uploads annotated frames to MinIO |
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
[MediaMTX RTSP stream]
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
   └─ Yes → publish detection
              │
              ▼
        BoundingBoxDrawer.draw_box()
              │  annotated frame
              ▼
        ImageStorage.upload_memory_image()  →  [MinIO]
              │
              ▼
        KafkaProducerWrapper.produce()      →  [truck-detected-<GATE_ID>]
              │
              ▼
        Wait for reset-agentA or `decision_timeout`
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
| `kafka_bootstrap` | `str` | Kafka broker address. Default: `"10.255.32.107:9092"` |
| `mediamtx_host` | `str` | MediaMTX RTSP server hostname. Default: `"10.255.32.56"` |
| `mediamtx_port` | `int` | MediaMTX RTSP server port. Default: `8554` |
| `minio_host` | `str` | MinIO server hostname. Default: `"10.255.32.82"` |
| `minio_port` | `int` | MinIO server port. Default: `9000` |
| `minio_user` | `str` | MinIO access key (required) |
| `minio_password` | `str` | MinIO secret key (required) |
| `minio_secure` | `bool` | Whether MinIO connection uses TLS. Default: `False` |
| `gate_id` | `str` | Gate identifier used for topic naming and bucket naming. Default: `"1"` |
| `models_path` | `str` | Filesystem path to the directory containing model files. Default: `"/app/AI_APP/agentA/data"` |
| `decision_timeout` | `int` | Maximum seconds to wait for `reset-agentA` before resuming detection. Default: `60` |

---

#### Methods

##### `stream_low` *(property)*

> Returns the RTSP stream URL for the low-quality feed of the configured gate.

**Parameters**

> N/A

**Returns:** `str` — URL in the form `rtsp://<mediamtx_host>:<mediamtx_port>/streams_low/gate<gate_id>`.

**Raises:**

> N/A

**Example**
```python
config = AgentAConfig()
print(config.stream_low)
# → "rtsp://10.255.32.56:8554/streams_low/gate1"
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

**Returns:** `List[str]` — Single-element list produced by `KafkaTopicFactory.reset_agent_a(gate_id)`.

**Raises:**

> N/A

**Example**
```python
config = AgentAConfig()
print(config.kafka_topic_consume)
# → ["reset-agentA-1"]
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
| `stream_manager` | `StreamManager` | Reads frames from the RTSP stream |
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

##### `_process_detection()`

> Runs the internal detection loop; on truck detection, uploads an annotated image and publishes a Kafka event.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
> N/A

**Returns:** `None`

**Raises:**
- Internal exceptions (inference errors, Kafka publish errors) are caught and logged with `logger.exception`; drawing/upload errors are caught separately and do not suppress the Kafka publish.

**Example**
```python
agent._process_detection()
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
| `KAFKA_BOOTSTRAP` | ❌ | `10.255.32.107:9092` | Kafka broker address |
| `MEDIAMTX_HOST` | ❌ | `10.255.32.56` | MediaMTX RTSP server hostname |
| `MEDIAMTX_PORT` | ❌ | `8554` | MediaMTX RTSP server port |
| `MINIO_HOST` | ❌ | `10.255.32.82` | MinIO server hostname |
| `MINIO_PORT` | ❌ | `9000` | MinIO server port |
| `MINIO_USER` | ✅ | — | MinIO access key |
| `MINIO_PASSWORD` | ✅ | — | MinIO secret key |
| `MINIO_SECURE` | ❌ | `False` | Enable TLS for MinIO connection |
| `GATE_ID` | ❌ | `1` | Gate identifier; scopes Kafka topics and MinIO bucket |
| `MODELS_PATH` | ❌ | `/app/AI_APP/agentA/data` | Directory containing `truck_model.pt` |
| `DECISION_TIMEOUT` | ❌ | `60` | Maximum seconds waiting for `reset-agentA` before resuming detection |

Deployment reference (April 2026):
- `GPU_AI_APP` host: `10.255.32.107` (Agent A/B/C, AI Gateway, Kafka)
- `Streaming Middleware` host: `10.255.32.56` (MediaMTX)
- `V_APP` host: `10.255.32.70` (receiver gateway and downstream services)
- `UI` host: `10.255.32.108`

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
from agentA import AgentA, AgentAConfig

config = AgentAConfig(minio_user="test", minio_password="test")
agent = AgentA(
    config=config,
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

> N/A

---

## Changelog

| Version / Date | Change |
|----------------|--------|
| `2026-04-18` | Reviewed AI_APP documentation for consistency, aligned paths/test commands, and validated deployment host mapping (AI_APP `10.255.32.107`, Streaming `10.255.32.56`, UI `10.255.32.108`, V_APP `10.255.32.70`). |
| `2026-02-21` | Constructor refactored to accept `AgentAConfig` as a required first parameter instead of reading env vars inline. Kafka topic names now resolved via `KafkaTopicFactory` (`kafka_topic_produce`, `kafka_topic_consume` properties). |

---

## Related Docs

- [`stream_manager.md`](../shared/stream_manager.md)
- [`object_detector.md`](../shared/object_detector.md)
- [`bounding_box_drawer.md`](../shared/bounding_box_drawer.md)
- [`image_storage.md`](../shared/image_storage.md)
- [`kafka_wrapper.md`](../../shared/kafka_wrapper.md)
- [`kafka_protocol.md`](../../shared/kafka_protocol.md)
- [Architecture Overview](../../../docs/sketch_arquitetura/arquitetura_intelligent_logistics.md)
