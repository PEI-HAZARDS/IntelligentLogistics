# `agentB.py`

> Performs license plate detection on truck frames by extending the shared `BaseAgent` pipeline.

---

## Overview

`agentB.py` defines `AgentB`, a concrete implementation of `BaseAgent` that specialises the generic detection pipeline for license plate recognition. On receiving a Kafka `truck_detected` event, it reads frames from an MediaMTX RTSP stream, runs YOLO inference to locate license plates, and applies PaddleOCR through the consensus algorithm to extract the plate text. Detections classified as hazard plates by `PlateClassifier` are rejected and their crops are uploaded to a dedicated MinIO bucket (`failed-crops`) for later analysis; accepted plates are published as `license_plate_results` messages.

The module acts as a downstream consumer of the truck detection stage (Agent A or equivalent) and an upstream producer for any component that acts on license plate data — including the `AIGateway`. It does not handle stream acquisition, Kafka I/O, or model training; those concerns are managed by `BaseAgent`, `StreamManager`, `KafkaWrapper`, and `ObjectDetector` respectively.

---

## Location
```
src/AI_APP/agentB/src/agentB.py
```

## Dependencies

### Internal
| Module | Why it's used |
|--------|---------------|
| `AI_APP/shared/src/base_agent.py` | Base class (`BaseAgent`, `BaseAgentConfig`) providing the full detection lifecycle |
| `shared/src/kafka_protocol.py` | `KafkaMessageProto`, `Message`, `KafkaTopicFactory` for topic names and message construction |
| `AI_APP/shared/src/plate_classifier.py` | `PlateClassifier` to reject crops identified as hazard plates |
| `AI_APP/shared/src/image_storage.py` | `ImageStorage` to upload rejected crop images to MinIO |
| `AI_APP/shared/src/paddle_ocr.py` | `OCR` for text extraction from detected crops |

### External
| Package | Version | Why it's used |
|---------|---------|---------------|
| `prometheus_client` | — | Exposes `Counter` and `Histogram` metrics for monitoring |
| `typing` | stdlib | `Optional` type hint |
| `os` | stdlib | Reads `MODELS_PATH` environment variable |

---

## Architecture & Flow

```
[Kafka: truck_detected_<gate_id>]
          │
          ▼
       AgentB.start()
          │  consumes Kafka message
          ▼
   BaseAgent._process_message()
          │  captures RTMP frames
          ├─► BaseAgent._run_yolo_inference()   (license_plate_model.pt)
          │         │  bbox crops
          │         ▼
          │   AgentB.is_valid_detection()       (PlateClassifier — rejects HAZARD_PLATE)
          │         │  valid crop
          │         ▼
          │   BaseAgent._process_ocr_result()   (ConsensusAlgorithm)
          │
          ├─► rejected crops → MinIO (failed-crops bucket)
          ├─► annotated frames → MinIO (agentb-<gate_id> bucket)
          ▼
AgentB._build_message_for_detection()
          │
          ▼
[Kafka: license_plate_results_<gate_id>]
```

---

## Classes

### `AgentB`

> Concrete `BaseAgent` that detects vehicle license plates and publishes OCR results to Kafka.

**Inherits from:** `BaseAgent`

**Constructor**
```python
AgentB(**kwargs)
```

All keyword arguments are forwarded to `BaseAgent.__init__`. The constructor additionally creates a second `ImageStorage` instance pointing to the `failed-crops` MinIO bucket for rejected-plate crops.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `BaseAgentConfig` | `None` | Agent configuration; loaded from environment if omitted |
| `stream_manager` | `StreamManager` | `None` | RTMP/RTSP stream reader; created from config if omitted |
| `object_detector` | `ObjectDetector` | `None` | YOLO wrapper; instantiated with model path if omitted |
| `ocr` | `OCR` | `None` | PaddleOCR instance; created via `initialize_ocr()` if omitted |
| `classifier` | `PlateClassifier` | `None` | Plate classifier; default instance created if omitted |
| `drawer` | `BoundingBoxDrawer` | `None` | Bounding box drawer; defaults to blue "License Plate" style |
| `annotated_frames_storage` | `ImageStorage` | `None` | MinIO storage for annotated frames |
| `crop_storage` | `ImageStorage` | `None` | MinIO storage for accepted crops |
| `kafka_producer` | `KafkaProducerWrapper` | `None` | Kafka producer; created from config if omitted |
| `kafka_consumer` | `KafkaConsumerWrapper` | `None` | Kafka consumer; created from config if omitted |
| `consensus_algorithm` | `ConsensusAlgorithm` | `None` | Consensus algorithm instance |

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `self.crop_fails` | `ImageStorage` | Separate MinIO storage pointing to the `failed-crops` bucket for rejected hazard-plate crops |
| `self.inference_latency` | `Histogram` | Prometheus histogram: YOLO inference duration (seconds) |
| `self.frames_processed_metric` | `Counter` | Prometheus counter: total frames processed by Agent B |
| `self.plates_detected` | `Counter` | Prometheus counter: total accepted license plates |
| `self.ocr_confidence` | `Histogram` | Prometheus histogram: OCR confidence score distribution |

---

#### Methods

##### `get_agent_name() -> str`

> Returns the agent's string identifier.

**Parameters**

> N/A

**Returns:** `str` — The fixed string `"AgentB"`.

**Raises:**

> N/A

**Example**
```python
agent = AgentB(**mock_deps)
assert agent.get_agent_name() == "AgentB"
```

---

##### `initialize_ocr() -> OCR`

> Instantiates and returns the OCR engine with unrestricted character set.

**Parameters**

> N/A

**Returns:** `OCR` — Default `OCR()` instance (no character restriction).

**Raises:**

> N/A

**Example**
```python
ocr = agent.initialize_ocr()
```

---

##### `get_bbox_color() -> str`

> Returns the bounding box colour used by `BoundingBoxDrawer`.

**Parameters**

> N/A

**Returns:** `str` — `"blue"`.

**Raises:**

> N/A

---

##### `get_bbox_label() -> str`

> Returns the label drawn on detected bounding boxes.

**Parameters**

> N/A

**Returns:** `str` — `"License Plate"`.

**Raises:**

> N/A

---

##### `get_yolo_model_path() -> str`

> Constructs the path to the license plate YOLO model file.

**Parameters**

> N/A

**Returns:** `str` — `<MODELS_PATH>/license_plate_model.pt`, where `MODELS_PATH` defaults to `/agentB/data`.

**Raises:**

> N/A

---

##### `get_bucket() -> str`

> Returns the MinIO bucket name for annotated frames and accepted crops.

**Parameters**

> N/A

**Returns:** `str` — `"agentb-<gate_id>"`.

**Raises:**

> N/A

---

##### `get_consume_topic() -> str`

> Returns the Kafka topic from which truck detection events are consumed.

**Parameters**

> N/A

**Returns:** `str` — Result of `KafkaTopicFactory.truck_detected(self.config.gate_id)`.

**Raises:**

> N/A

---

##### `get_produce_topic() -> str`

> Returns the Kafka topic to which license plate results are published.

**Parameters**

> N/A

**Returns:** `str` — Result of `KafkaTopicFactory.license_plate_results(self.config.gate_id)`.

**Raises:**

> N/A

---

##### `get_object_type() -> str`

> Returns the human-readable object type name used in log messages.

**Parameters**

> N/A

**Returns:** `str` — `"license plate"`.

**Raises:**

> N/A

---

##### `is_valid_detection(crop, confidence, box_index) -> bool`

> Validates a detected crop by running `PlateClassifier`; rejects hazard plates.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `crop` | `np.ndarray` | required | Cropped image region from the detected bounding box |
| `confidence` | `float` | required | YOLO confidence score for this box |
| `box_index` | `int` | required | 1-based index of the bounding box (used in log messages) |

**Returns:** `bool` — `False` if classified as `PlateClassifier.HAZARD_PLATE`; `True` otherwise.

**Raises:**

> N/A

**Example**
```python
agent.classifier.classify.return_value = PlateClassifier.HAZARD_PLATE
assert agent.is_valid_detection(crop, 0.9, 1) is False
```

> ⚠️ **Note:** Rejected crops are NOT uploaded to MinIO inside this method. Crop upload is handled by `BaseAgent._process_message()`.

---

##### `_build_message_for_detection(license_plate, confidence, crop_url) -> Message`

> Constructs the Kafka message payload for a validated license plate detection.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `license_plate` | `str` | required | OCR-extracted plate text (or `"N/A"`) |
| `confidence` | `float` | required | Final detection confidence |
| `crop_url` | `Optional[str]` | required | MinIO URL of the crop image; empty string if `None` |

**Returns:** `Message` — A `KafkaMessageProto.license_plate_result` message object.

**Raises:**

> N/A

---

##### `init_metrics() -> None`

> Registers Prometheus metrics for Agent B. Called once during `__init__`.

**Parameters**

> N/A

**Returns:** `None`

**Raises:**

> N/A

---

##### `get_detection_metric() -> Optional[object]`

> Returns `None` because `plates_detected` is incremented directly in `is_valid_detection`.

**Parameters**

> N/A

**Returns:** `None`

**Raises:**

> N/A

---

## Standalone Functions

> N/A

---

## Configuration & Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `KAFKA_BOOTSTRAP` | ✅ | — | Kafka broker address (`BaseAgentConfig.kafka_bootstrap`) |
| `MINIO_USER` | ✅ | — | MinIO access key |
| `MINIO_PASSWORD` | ✅ | — | MinIO secret key |
| `GATE_ID` | ❌ | `"1"` | Gate identifier; used to namespace Kafka topics and MinIO bucket |
| `MODELS_PATH` | ❌ | `/agentB/data` | Directory containing `license_plate_model.pt` |
| `MEDIAMTX_HOST` | ❌ | `10.255.32.56` | MediaMTX RTSP server host |
| `MEDIAMTX_PORT` | ❌ | `8554` | MediaMTX RTSP server port |
| `MINIO_HOST` | ❌ | `10.255.32.82` | MinIO server host |
| `MINIO_PORT` | ❌ | `9000` | MinIO server port |
| `MINIO_SECURE` | ❌ | `False` | Whether to use TLS for MinIO |
| `MAX_FRAMES` | ❌ | `40` | Maximum frames to process per detection cycle |
| `MIN_DETECTION_CONFIDENCE` | ❌ | `0.4` | Minimum YOLO confidence threshold |

---

## Usage Example

```python
from agentB import AgentB

# All config is read from environment variables
agent = AgentB()
agent.start()  # Blocks: consumes Kafka events and runs detection loop
```

---

## Error Handling

All exceptions raised during the main Kafka loop are caught by `BaseAgent.start()`, logged via `self.logger.exception()`, and followed by a 1-second sleep before retrying. OCR failures on individual crops are caught in `BaseAgent._process_frame()`, logged as warnings, and processing continues with the next crop. Crop upload errors are caught in `BaseAgent._process_message()` and logged as errors; a result message is still published. Resource cleanup (`StreamManager`, Kafka producer/consumer) is performed in `BaseAgent._cleanup()` on `stop()`.

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| `agentB_unitTest.py` | Unit | Configuration methods, `is_valid_detection` (hazard reject / license accept), `_parse_detection_result`, metric counters |

To run:
```bash
pytest src/AI_APP/agentB/tests/
```

---

## Known Issues / TODOs

> N/A

---

## Changelog

> N/A

---

## Related Docs

- [`base_agent.md`](../../shared/base_agent.md)
- [`plate_classifier.md`](../../shared/plate_classifier.md)
- [`image_storage.md`](../../shared/image_storage.md)
- [`kafka_wrapper.md`](../../../shared/kafka_wrapper.md)
- [Architecture Overview](../../../docs/sketch_arquitetura/arquitetura_intelligent_logistics.md)
