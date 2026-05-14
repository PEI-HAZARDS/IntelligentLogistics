# `base_agent.py`

> Abstract base class implementing the common detection-and-consensus pipeline shared by all AI agents.

---

## Overview

`BaseAgent` encapsulates the full lifecycle of an AI detection agent: consuming trigger messages from Kafka, capturing video frames from an RTSP stream, running YOLO object detection, performing OCR on cropped regions, reaching consensus across multiple readings, uploading results to MinIO, and publishing detection outcomes back to Kafka.

The module also defines `BaseAgentConfig`, a Pydantic settings class that centralises all environment-driven configuration (Kafka, MediaMTX RTSP, MinIO, detection parameters). Concrete subclasses—`AgentA` (`src/AI_APP/agentA/src/agentA.py`), `AgentB` (`src/AI_APP/agentB/src/agentB.py`), and `AgentC` (`src/AI_APP/agentC/src/agentC.py`)—implement the abstract hooks to specialise detection targets (e.g. license plates, hazard plates), YOLO models, OCR initialization, bounding-box styling, Kafka topics, and Prometheus metrics.

`BaseAgent` does **not** manage gateway-level HTTP forwarding (see `base_gateway.py`) nor the consensus algorithm itself (see `consensus_algorithm.py`); it orchestrates these collaborators.

---

## Location
```
src/AI_APP/shared/src/base_agent.py
```

## Dependencies

### Internal
| Module | Why it's used |
|--------|---------------|
| `AI_APP/shared/src/stream_manager.py` | RTSP frame capture |
| `AI_APP/shared/src/object_detector.py` | YOLO-based object detection |
| `AI_APP/shared/src/paddle_ocr.py` | OCR text extraction from image crops |
| `AI_APP/shared/src/plate_classifier.py` | Plate type classification for detection validation |
| `AI_APP/shared/src/image_storage.py` | MinIO image upload (annotated frames and crops) |
| `AI_APP/shared/src/bounding_box_drawer.py` | Drawing bounding boxes on annotated frames |
| `shared/src/kafka_wrapper.py` | Kafka consuming and producing |
| `shared/src/consensus_algorithm.py` | Multi-reading consensus logic |
| `shared/src/kafka_protocol.py` | `Message` base dataclass |

### External
| Package | Version | Why it's used |
|---------|---------|---------------|
| `numpy` | — | Frame and crop array representation |
| `pydantic-settings` | — | `BaseSettings` subclass for environment-driven configuration |
| `pydantic` | — | `Field` and `SecretStr` for config validation and secret handling |

---

## Architecture & Flow

```
[Kafka trigger] ──consume──▶ BaseAgent.start()
                                │
                                ▼
                         _process_message()
                                │
                                ▼
                        process_detection()
                         ┌──────┴──────┐
                         ▼             │
                   _get_next_frame()   │  (loop up to max_frames)
                   (robust capture)    │
                         │             │
                         ▼             │
                   _process_frame()    │
                     ├─ _run_yolo_inference()
                     ├─ _extract_crop()
                     ├─ is_valid_detection()  ◄── subclass hook
                     └─ _process_ocr_result()
                          ├─ OCR extract_text()
                          └─ ConsensusAlgorithm
                                │
                         consensus / max_frames
                                │
                                ▼
                   _build_message_for_detection()  ◄── subclass hook
                                │
                                ▼
                     crop_storage.upload()
                     _publish_detection() ──produce──▶ [Kafka topic]
```

---

## Classes

### `BaseAgentConfig`

> Pydantic settings model holding agent configuration sourced from environment variables or constructor arguments.

**Inherits from:** `BaseSettings` (`pydantic_settings`)

**Constructor**
```python
BaseAgentConfig(
    kafka_bootstrap: str = "10.255.32.107:9092",
    mediamtx_host: str = "10.255.32.56",
    mediamtx_port: int = 8554,
    minio_host: str = "10.255.32.82",
    minio_port: int = 9000,
    minio_user: str,            # required
    minio_password: SecretStr,   # required
    minio_secure: bool = False,
    gate_id: str = "1",
    models_path: str = "/app/AI_APP",
    max_frames: int = 40,
    min_detection_confidence: float = 0.4,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `kafka_bootstrap` | `str` | `"10.255.32.107:9092"` | Kafka broker address |
| `mediamtx_host` | `str` | `"10.255.32.56"` | MediaMTX RTSP server host |
| `mediamtx_port` | `int` | `8554` | MediaMTX RTSP server port |
| `minio_host` | `str` | `"10.255.32.82"` | MinIO server host |
| `minio_port` | `int` | `9000` | MinIO server port |
| `minio_user` | `str` | required | MinIO access key |
| `minio_password` | `SecretStr` | required | MinIO secret key (stored securely) |
| `minio_secure` | `bool` | `False` | Whether to use TLS for MinIO |
| `gate_id` | `str` | `"1"` | Gate identifier this agent is assigned to |
| `models_path` | `str` | `"/app/AI_APP"` | Base path for ML model files |
| `max_frames` | `int` | `40` | Maximum frames to process before returning partial result |
| `min_detection_confidence` | `float` | `0.4` | Minimum YOLO confidence to accept a detection box |

**Attributes**

| Attribute | Type | Description |
|-----------|------|-------------|
| *(all parameters above)* | | |
| `stream_url` | `str` | (property) Computed RTSP URL: `rtsp://{mediamtx_host}:{mediamtx_port}/streams_high/gate{gate_id}` |
| `minio_config` | `Dict[str, Any]` | (property) Computed MinIO connection dict with endpoint, credentials, and TLS flag |

---

### `BaseAgent`

> Abstract base class implementing the common detection-and-consensus pipeline for all AI agents.

**Inherits from:** `ABC` (`abc`)

**Constructor**
```python
BaseAgent(
    config: Optional[BaseAgentConfig] = None,
    stream_manager: Optional[StreamManager] = None,
    object_detector: Optional[ObjectDetector] = None,
    ocr: Optional[OCR] = None,
    classifier: Optional[PlateClassifier] = None,
    drawer: Optional[BoundingBoxDrawer] = None,
    annotated_frames_storage: Optional[ImageStorage] = None,
    crop_storage: Optional[ImageStorage] = None,
    kafka_producer: Optional[KafkaProducerWrapper] = None,
    kafka_consumer: Optional[KafkaConsumerWrapper] = None,
    consensus_algorithm: Optional[ConsensusAlgorithm] = None,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `Optional[BaseAgentConfig]` | `None` | Agent configuration; loaded from environment if not provided |
| `stream_manager` | `Optional[StreamManager]` | `None` | RTMP/RTSP frame reader; created from `config.stream_url` if not provided |
| `object_detector` | `Optional[ObjectDetector]` | `None` | YOLO detector; created from `get_yolo_model_path()` if not provided |
| `ocr` | `Optional[OCR]` | `None` | OCR engine; created via `initialize_ocr()` if not provided |
| `classifier` | `Optional[PlateClassifier]` | `None` | Plate classifier; default-constructed if not provided |
| `drawer` | `Optional[BoundingBoxDrawer]` | `None` | Bounding box drawer; created with subclass color/label if not provided |
| `annotated_frames_storage` | `Optional[ImageStorage]` | `None` | MinIO storage for annotated frames; created from config if not provided |
| `crop_storage` | `Optional[ImageStorage]` | `None` | MinIO storage for crops; defaults to `annotated_frames_storage` |
| `kafka_producer` | `Optional[KafkaProducerWrapper]` | `None` | Kafka producer; created from `config.kafka_bootstrap` if not provided |
| `kafka_consumer` | `Optional[KafkaConsumerWrapper]` | `None` | Kafka consumer; created with agent-specific group and topic if not provided |
| `consensus_algorithm` | `Optional[ConsensusAlgorithm]` | `None` | Consensus algorithm; default-constructed if not provided |

> ⚠️ **Note:** All optional dependencies follow a dependency-injection pattern designed for testability. When `None`, production instances are created automatically.

**Attributes**

| Attribute | Type | Description |
|-----------|------|-------------|
| `self.agent_name` | `str` | Agent identifier from `get_agent_name()` |
| `self.logger` | `logging.Logger` | Logger named after the agent |
| `self.config` | `BaseAgentConfig` | Stored configuration |
| `self.yolo` | `ObjectDetector` | YOLO object detector |
| `self.ocr` | `OCR` | OCR engine |
| `self.classifier` | `PlateClassifier` | Plate type classifier |
| `self.drawer` | `BoundingBoxDrawer` | Bounding box drawing utility |
| `self.image_storage` | `ImageStorage` | MinIO storage for annotated frames |
| `self.crop_storage` | `ImageStorage` | MinIO storage for detection crops |
| `self.stream_manager` | `StreamManager` | RTMP/RTSP frame reader |
| `self.kafka_producer` | `KafkaProducerWrapper` | Kafka producer |
| `self.kafka_consumer` | `KafkaConsumerWrapper` | Kafka consumer (group = `{agent_name}-group`) |
| `self.consensus_algorithm` | `ConsensusAlgorithm` | Multi-reading consensus tracker |
| `self.running` | `bool` | Lifecycle flag controlling the main loop |
| `self.truck_id` | `str` | Current truck identifier (set per consumed message) |
| `self.frames_processed_metric` | `Optional[object]` | Prometheus counter for frames processed (set by `init_metrics()`) |
| `self.inference_latency` | `Optional[object]` | Prometheus histogram for YOLO inference latency (set by `init_metrics()`) |
| `self.ocr_confidence` | `Optional[object]` | Prometheus histogram for OCR confidence (set by `init_metrics()`) |
| `self.frames_processed` | `int` | Frame counter for the current detection cycle |

---

#### Methods

##### `get_agent_name()` *(abstract)*

> Return agent identifier (e.g. `"AgentB"`, `"AgentC"`).

**Parameters**

> N/A

**Returns:** `str` — Agent name.

---

##### `initialize_ocr()` *(abstract)*

> Initialize and return an OCR engine instance.

**Parameters**

> N/A

**Returns:** `OCR` — Configured OCR instance.

---

##### `get_bbox_color()` *(abstract)*

> Return bounding box colour string (e.g. `"Red"`, `"Green"`).

**Parameters**

> N/A

**Returns:** `str` — Colour name.

---

##### `get_bbox_label()` *(abstract)*

> Return bounding box label string (e.g. `"truck"`, `"car"`).

**Parameters**

> N/A

**Returns:** `str` — Label text.

---

##### `get_yolo_model_path()` *(abstract)*

> Return filesystem path to the YOLO model weights.

**Parameters**

> N/A

**Returns:** `str` — Model file path.

---

##### `get_bucket()` *(abstract)*

> Return the MinIO bucket name for this agent.

**Parameters**

> N/A

**Returns:** `str` — Bucket name.

---

##### `get_consume_topic()` *(abstract)*

> Return the Kafka topic this agent subscribes to.

**Parameters**

> N/A

**Returns:** `str` — Topic name.

---

##### `get_produce_topic()` *(abstract)*

> Return the Kafka topic this agent publishes results to.

**Parameters**

> N/A

**Returns:** `str` — Topic name.

---

##### `is_valid_detection(crop, confidence, box_index)` *(abstract)*

> Validate a detection box (e.g. check plate classification). Subclasses use this to apply domain-specific filtering.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `crop` | `np.ndarray` | required | Cropped image of the detected region |
| `confidence` | `float` | required | YOLO detection confidence |
| `box_index` | `int` | required | 1-based index of the box within the frame |

**Returns:** `bool` — `True` if the detection should be processed, `False` to skip.

---

##### `_build_message_for_detection(text, confidence, crop_url)` *(abstract)*

> Build the agent-specific Kafka message for a detection result. Bridges the generic pipeline output to the typed `Message` subclass.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `text` | `str` | required | Detected text from OCR |
| `confidence` | `float` | required | Detection confidence |
| `crop_url` | `Optional[str]` | required | MinIO URL of the uploaded crop, or `None` |

**Returns:** `Message` — Typed message object for Kafka publishing.

---

##### `init_metrics()` *(abstract)*

> Initialize Prometheus metrics specific to this agent. Must set `self.frames_processed_metric`, `self.inference_latency`, and `self.ocr_confidence`.

**Parameters**

> N/A

**Returns:** `None`

---

##### `get_object_type()` *(abstract)*

> Return the detected object type name for logging (e.g. `"license plate"`, `"hazard plate"`).

**Parameters**

> N/A

**Returns:** `str` — Object type label.

---

##### `get_detection_metric()` *(abstract)*

> Return the Prometheus counter to increment per detected bounding box, or `None` if no such metric is defined.

**Parameters**

> N/A

**Returns:** `Optional[object]` — Prometheus counter or `None`.

---

##### `start()`

> Main processing loop. Consumes typed messages from Kafka, extracts the truck ID, and delegates to `_process_message()`. Runs indefinitely until `self.running` is set to `False`. Exceptions are logged and recovered from with a 1-second backoff.

**Parameters**

> N/A

**Returns:** `None`

> ⚠️ **Note:** Clears stale Kafka messages on entry via `kafka_consumer.clear_stale_messages()`.

---

##### `stop()`

> Gracefully stop the agent by setting `self.running = False` and calling `_cleanup()`.

**Parameters**

> N/A

**Returns:** `None`

---

##### `_process_message(message_obj)`

> Orchestrate a full detection cycle for one incoming Kafka message. Runs the detection pipeline, uploads the best crop to MinIO, builds the agent-specific result message, and publishes it to Kafka. Always produces a message (text defaults to `"N/A"` when no detection is made).

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `message_obj` | `Any` | required | Typed message object received from the Kafka consumer |

**Returns:** `None`

---

##### `process_detection()`

> Main detection pipeline. Captures frames, runs YOLO + OCR, and accumulates consensus readings. Returns on consensus or when the frame limit is reached (falls back to partial result).

**Parameters**

> N/A

**Returns:** `Tuple[Optional[str], Optional[float], Optional[Any]]` — `(text, confidence, crop_image)` or `(None, None, None)`.

---

##### `_should_continue_processing()`

> Check whether frame processing should continue based on `self.running`, consensus state, and frame count.

**Parameters**

> N/A

**Returns:** `bool` — `True` if more frames should be processed.

---

##### `_get_next_frame()`

> Robustly retrieve the next frame from the stream manager. Retries for several seconds to allow the stream to connect and returns a **copy** of the frame to ensure thread safety and prevent memory corruption.

**Parameters**

> N/A

**Returns:** `Optional[np.ndarray]` — A **copy** of the video frame, or `None` if no frame is available.

---

##### `_process_frame(frame)`

> Process a single video frame: run YOLO inference, extract and validate crops, run OCR, and check consensus.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `frame` | `np.ndarray` | required | Video frame to process |

**Returns:** `Optional[Tuple[str, float, np.ndarray]]` — `(text, confidence, crop)` if consensus is reached, else `None`.

**Raises:**
- Re-raises any exception from frame processing after logging.

---

##### `_run_yolo_inference(frame)`

> Run YOLO detection on a frame, draw bounding boxes on an annotated copy, upload the annotated frame to MinIO, and increment detection metrics.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `frame` | `np.ndarray` | required | Video frame to detect objects in |

**Returns:** `Optional[List[Any]]` — List of bounding boxes `[x1, y1, x2, y2, conf]`, or `None` if nothing detected.

---

##### `_extract_crop(box, frame, box_index)`

> Extract and validate a crop from a detection bounding box. Rejects boxes below `min_detection_confidence` and delegates domain-specific validation to `is_valid_detection()`.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `box` | `Any` | required | Bounding box `[x1, y1, x2, y2, conf]` |
| `frame` | `np.ndarray` | required | Source video frame |
| `box_index` | `int` | required | 1-based box index for logging |

**Returns:** `Tuple[Optional[np.ndarray], Optional[float]]` — `(crop, confidence)` or `(None, None)` if invalid.

---

##### `_process_ocr_result(crop)`

> Run OCR on a crop, normalize the text, add the result to the consensus algorithm, and check for full consensus.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `crop` | `np.ndarray` | required | Cropped detection image |

**Returns:** `Optional[Tuple[str, float, np.ndarray]]` — `(final_text, 1.0, best_crop)` if consensus reached, else `None`.

---

##### `_publish_detection(message)`

> Publish a detection result message to Kafka on the topic returned by `get_produce_topic()`, with `self.truck_id` as a header.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `message` | `Message` | required | Message object to publish |

**Returns:** `None`

---

##### `_cleanup()`

> Release all resources: stream manager, Kafka producer (flush + close), and Kafka consumer.

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
| `KAFKA_BOOTSTRAP` | ❌ | `10.255.32.107:9092` | Kafka broker address |
| `MEDIAMTX_HOST` | ❌ | `10.255.32.56` | MediaMTX RTSP server host |
| `MEDIAMTX_PORT` | ❌ | `8554` | MediaMTX RTSP server port |
| `MINIO_HOST` | ❌ | `10.255.32.82` | MinIO server host |
| `MINIO_PORT` | ❌ | `9000` | MinIO server port |
| `MINIO_USER` | ✅ | — | MinIO access key |
| `MINIO_PASSWORD` | ✅ | — | MinIO secret key |
| `MINIO_SECURE` | ❌ | `False` | Use TLS for MinIO |
| `GATE_ID` | ❌ | `"1"` | Gate identifier |
| `MODELS_PATH` | ❌ | `"/app/AI_APP"` | Base path for ML model files |
| `MAX_FRAMES` | ❌ | `40` | Maximum frames per detection cycle |
| `MIN_DETECTION_CONFIDENCE` | ❌ | `0.4` | Minimum YOLO confidence threshold |

Deployment reference (April 2026):
- `GPU_AI_APP` host: `10.255.32.107` (Agent A/B/C, AI Gateway, Kafka)
- `Streaming Middleware` host: `10.255.32.56` (MediaMTX RTSP)
- `V_APP` host: `10.255.32.70` (receiver gateway and downstream services)
- `UI` host: `10.255.32.108`

---

## Usage Example

```python
from shared.src.base_agent import BaseAgent, BaseAgentConfig
from shared.src.paddle_ocr import OCR
from shared.src.kafka_protocol import Message
from typing import Optional
import numpy as np


class MyAgent(BaseAgent):
    def get_agent_name(self) -> str:
        return "MyAgent"

    def initialize_ocr(self) -> OCR:
        return OCR(lang="en")

    def get_bbox_color(self) -> str:
        return "Green"

    def get_bbox_label(self) -> str:
        return "plate"

    def get_yolo_model_path(self) -> str:
        return f"{self.config.models_path}/models/my_model.pt"

    def get_bucket(self) -> str:
        return "my-agent-bucket"

    def get_consume_topic(self) -> str:
        return f"gate{self.config.gate_id}_truck_detected"

    def get_produce_topic(self) -> str:
        return f"gate{self.config.gate_id}_my_results"

    def is_valid_detection(self, crop: np.ndarray, confidence: float, box_index: int) -> bool:
        return confidence > 0.5

    def _build_message_for_detection(self, text: str, confidence: float, crop_url: Optional[str]) -> Message:
        ...  # return agent-specific Message subclass

    def init_metrics(self) -> None:
        self.frames_processed_metric = None
        self.inference_latency = None
        self.ocr_confidence = None

    def get_object_type(self) -> str:
        return "plate"

    def get_detection_metric(self):
        return None


config = BaseAgentConfig(minio_user="admin", minio_password="secret")
agent = MyAgent(config=config)
agent.start()  # blocks on main loop
```

---

## Error Handling

The main loop in `start()` catches all exceptions per iteration, logs them with `logger.exception`, and retries after a 1-second sleep—preventing a single bad message from crashing the agent. Frame capture errors in `_get_next_frame` are caught and retried with a robust backoff. OCR failures on individual crops are caught in `_process_frame` so remaining crops in the same frame are still processed. Annotated-frame upload and crop upload errors are caught and logged without aborting the pipeline. The `_process_frame` method re-raises non-OCR exceptions to surface unexpected errors. Resource cleanup in `_cleanup` is called by `stop()` to release the stream, flush/close Kafka, and free connections.

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| `base_agent_unit_test.py` | Unit | Initialization, config loading, main loop, frame management, detection pipeline, OCR processing, publishing, cleanup |

To run:
```bash
pytest src/AI_APP/shared/tests/base_agent_unit_test.py
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

- [`stream_manager.md`](stream_manager.md)
- [`object_detector.md`](object_detector.md)
- [`paddle_ocr.md`](paddle_ocr.md)
- [`image_storage.md`](image_storage.md)
- [`bounding_box_drawer.md`](bounding_box_drawer.md)
- [`kafka_wrapper.md`](kafka_wrapper.md)
- [`consensus_algorithm.md`](consensus_algorithm.md)
- [`agentA.py`](../../../src/AI_APP/agentA/src/agentA.py) — Concrete subclass for truck detection
- [`agentB.py`](../../../src/AI_APP/agentB/src/agentB.py) — Concrete subclass for license plate detection
- [`agentC.py`](../../../src/AI_APP/agentC/src/agentC.py) — Concrete subclass for hazard plate detection
