# `agentC.py`

> Performs hazard plate detection on truck frames by extending the shared `BaseAgent` pipeline.

---

## Overview

`agentC.py` defines `AgentC`, a concrete implementation of `BaseAgent` that specialises the generic detection pipeline for hazard plate recognition. On receiving a Kafka `truck_detected` event, it reads frames from a MediaMTX RTSP stream, runs YOLO inference to locate hazard plates, and applies PaddleOCR through the consensus algorithm to extract UN and Kemler codes. Results are published to Kafka as `hazard_plate_results` messages.

The module acts as a downstream consumer of the truck detection stage (Agent A or equivalent) and an upstream producer for any component that acts on hazard plate data — including the `AIGateway` and the `InfractionEngine`. It does not handle stream acquisition, Kafka I/O, or model training; those concerns are managed by `BaseAgent`, `StreamManager`, `KafkaWrapper`, and `ObjectDetector` respectively.

---

## Location
```
src/AI_APP/agentC/src/agentC.py
```

## Dependencies

### Internal
| Module | Why it's used |
|--------|---------------|
| `AI_APP/shared/src/base_agent.py` | Base class (`BaseAgent`, `BaseAgentConfig`) providing the full detection lifecycle |
| `shared/src/kafka_protocol.py` | `KafkaMessageProto`, `Message`, `KafkaTopicFactory` for topic names and message construction |
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
       AgentC.start()
          │  consumes Kafka message
          ▼
   BaseAgent._process_message()
          │  captures RTMP frames
          ├─► BaseAgent._run_yolo_inference()   (hazard_plate_model.pt)
          │         │  bbox crops
          │         ▼
          │   AgentC.is_valid_detection()       (Always returns True)
          │         │
          │         ▼
          │   BaseAgent._process_ocr_result()   (ConsensusAlgorithm)
          │
          ├─► annotated frames → MinIO (agentc-<gate_id> bucket)
          ▼
AgentC._build_message_for_detection()
          │  parses text into UN/Kemler
          ▼
[Kafka: hazard_plate_results_<gate_id>]
```

---

## Classes

### `AgentC`

> Concrete `BaseAgent` that detects hazardous material plates and publishes OCR results (UN/Kemler) to Kafka.

**Inherits from:** `BaseAgent`

**Constructor**
```python
AgentC(**kwargs)
```

All keyword arguments are forwarded to `BaseAgent.__init__`.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `BaseAgentConfig` | `None` | Agent configuration; loaded from environment if omitted |
| `stream_manager` | `StreamManager` | `None` | RTMP/RTSP stream reader; created from config if omitted |
| `object_detector` | `ObjectDetector` | `None` | YOLO wrapper; instantiated with model path if omitted |
| `ocr` | `OCR` | `None` | PaddleOCR instance; created via `initialize_ocr()` if omitted |
| `classifier` | `PlateClassifier` | `None` | Plate classifier (unused by Agent C) |
| `drawer` | `BoundingBoxDrawer` | `None` | Bounding box drawer; defaults to orange "Hazard Plate" style |
| `annotated_frames_storage` | `ImageStorage` | `None` | MinIO storage for annotated frames |
| `crop_storage` | `ImageStorage` | `None` | MinIO storage for detection crops |
| `kafka_producer` | `KafkaProducerWrapper` | `None` | Kafka producer; created from config if omitted |
| `kafka_consumer` | `KafkaConsumerWrapper` | `None` | Kafka consumer; created from config if omitted |
| `consensus_algorithm` | `ConsensusAlgorithm` | `None` | Consensus algorithm instance |

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `self.inference_latency` | `Histogram` | Prometheus histogram: YOLO inference duration (seconds) |
| `self.frames_processed_metric` | `Counter` | Prometheus counter: total frames processed by Agent C |
| `self.hazards_detected` | `Counter` | Prometheus counter: total hazardous plates detected |
| `self.ocr_confidence` | `Histogram` | Prometheus histogram: OCR confidence score distribution |

---

#### Methods

##### `get_agent_name() -> str`

> Returns the agent's string identifier.

**Parameters**

> N/A

**Returns:** `str` — The fixed string `"AgentC"`.

---

##### `initialize_ocr() -> OCR`

> Instantiates and returns the OCR engine with a character set restricted to digits, spaces, and 'X' (hazard plate standard).

**Parameters**

> N/A

**Returns:** `OCR` — `OCR(allowed_chars='0123456789xX ')`.

---

##### `get_bbox_color() -> str`

> Returns the bounding box colour used by `BoundingBoxDrawer`.

**Parameters**

> N/A

**Returns:** `str` — `"orange"`.

---

##### `get_bbox_label() -> str`

> Returns the label drawn on detected bounding boxes.

**Parameters**

> N/A

**Returns:** `str` — `"Hazard Plate"`.

---

##### `get_yolo_model_path() -> str`

> Constructs the path to the hazard plate YOLO model file.

**Parameters**

> N/A

**Returns:** `str` — `<MODELS_PATH>/hazard_plate_model.pt`, where `MODELS_PATH` defaults to `/agentC/data`.

---

##### `get_bucket() -> str`

> Returns the MinIO bucket name for annotated frames and crops.

**Parameters**

> N/A

**Returns:** `str` — `"agentc-<gate_id>"`.

---

##### `get_consume_topic() -> str`

> Returns the Kafka topic from which truck detection events are consumed.

**Parameters**

> N/A

**Returns:** `str` — Result of `KafkaTopicFactory.truck_detected(self.config.gate_id)`.

---

##### `get_produce_topic() -> str`

> Returns the Kafka topic to which hazard plate results are published.

**Parameters**

> N/A

**Returns:** `str` — Result of `KafkaTopicFactory.hazard_plate_results(self.config.gate_id)`.

---

##### `get_object_type() -> str`

> Returns the human-readable object type name used in log messages.

**Parameters**

> N/A

**Returns:** `str` — `"hazard plate"`.

---

##### `is_valid_detection(crop, confidence, box_index) -> bool`

> Validates a detected crop. Agent C accepts all hazard plate detections without additional classification.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `crop` | `np.ndarray` | required | Cropped image region from the detected bounding box |
| `confidence` | `float` | required | YOLO confidence score for this box |
| `box_index` | `int` | required | 1-based index of the bounding box (used in logs) |

**Returns:** `bool` — Always `True`.

---

##### `_build_message_for_detection(text, confidence, crop_url) -> Message`

> Parses the extracted OCR text into UN and Kemler codes and constructs the Kafka result message.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `text` | `str` | required | OCR-extracted text (normalized) |
| `confidence` | `float` | required | Final detection confidence |
| `crop_url` | `Optional[str]` | required | MinIO URL of the crop image |

**Returns:** `Message` — A `KafkaMessageProto.hazard_plate_result` message object.

---

##### `_parse_detection_result(text) -> tuple[str, str]`

> Internal helper to split consensus text into UN and Kemler components. Expected format is "KEMLER UN".

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `text` | `str` | required | Space-separated result string |

**Returns:** `tuple[str, str]` — `(un, kemler)`. Returns `("N/A", "N/A")` if parsing fails.

---

##### `init_metrics() -> None`

> Registers Prometheus metrics for Agent C. Called once during `__init__`.

---

##### `get_detection_metric() -> Optional[object]`

> Returns the `hazards_detected` counter to be incremented for every valid detection.

**Parameters**

> N/A

**Returns:** `Counter` — `self.hazards_detected`.

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
| `MODELS_PATH` | ❌ | `/agentC/data` | Directory containing `hazard_plate_model.pt` |
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
from agentC import AgentC

# All config is read from environment variables
agent = AgentC()
agent.start()  # Blocks: consumes Kafka events and runs detection loop
```

---

## Error Handling

All exceptions raised during the main Kafka loop are caught by `BaseAgent.start()`, logged via `self.logger.exception()`, and followed by a 1-second sleep before retrying. OCR failures on individual crops are caught in `BaseAgent._process_frame()`, logged as warnings, and processing continues with the next crop. Parsing errors in `_parse_detection_result` result in `"N/A"` values. Resource cleanup (`StreamManager`, Kafka producer/consumer) is performed in `BaseAgent._cleanup()` on `stop()`.

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| `agentC_unitTest.py` | Unit | Configuration methods, `_parse_detection_result`, result message building, metric registration |

To run:
```bash
pytest src/AI_APP/agentC/tests/
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
- [`image_storage.md`](../../shared/image_storage.md)
- [`kafka_wrapper.md`](../../../shared/kafka_wrapper.md)
- [Architecture Overview](../../../docs/sketch_arquitetura/arquitetura_intelligent_logistics.md)
