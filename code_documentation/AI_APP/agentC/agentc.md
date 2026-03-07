# `agentC.py`

> Performs hazard plate detection on truck frames, extracting UN and Kemler codes via OCR.

---

## Overview

`agentC.py` defines `AgentC`, a concrete implementation of `BaseAgent` that specialises the generic detection pipeline for hazard (ADR) plate recognition. On receiving a Kafka `truck_detected` event, it reads frames from an RTMP stream, runs YOLO inference using a dedicated hazard plate model, and applies PaddleOCR — restricted to digits, spaces, and `xX` — through the consensus algorithm to extract the plate text. Unlike `AgentB`, all YOLO detections pass the validity check without classification filtering. The raw OCR text is then parsed into a (Kemler, UN) code pair and published to Kafka as a `hazard_plate_results` message.

`AgentC` sits in parallel with `AgentB` as a downstream consumer of truck detection events and an upstream producer for any component that acts on hazardous material data, including the `AIGateway`. Frame capture, Kafka I/O, consensus logic, and MinIO uploads are fully handled by `BaseAgent`; `AgentC` only provides hazard-plate–specific configuration, validity, message building, and text parsing.

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
| `AI_APP/shared/src/plate_classifier.py` | `PlateClassifier` constant (`HAZARD_PLATE`) referenced in parent context |
| `AI_APP/shared/src/paddle_ocr.py` | `OCR` for text extraction with a restricted character set |
| `shared/src/kafka_protocol.py` | `KafkaMessageProto`, `Message`, `KafkaTopicFactory` for topic names and message construction |

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
          ├─► BaseAgent._run_yolo_inference()      (hazard_plate_model.pt)
          │         │  bbox crops
          │         ▼
          │   AgentC.is_valid_detection()          (always True — no filtering)
          │         │  valid crop
          │         ▼
          │   BaseAgent._process_ocr_result()      (ConsensusAlgorithm, digits/xX only)
          │
          ├─► annotated frames → MinIO (agentc-<gate_id> bucket)
          ▼
AgentC._build_message_for_detection()
          │  calls _parse_detection_result()
          ▼
[Kafka: hazard_plate_results_<gate_id>]
```

---

## Classes

### `AgentC`

> Concrete `BaseAgent` that detects ADR hazard plates and publishes UN and Kemler codes to Kafka.

**Inherits from:** `BaseAgent`

**Constructor**
```python
AgentC(**kwargs)
```

All keyword arguments are forwarded directly to `BaseAgent.__init__`. No additional attributes are set beyond what `BaseAgent` initialises.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `BaseAgentConfig` | `None` | Agent configuration; loaded from environment if omitted |
| `stream_manager` | `StreamManager` | `None` | RTMP stream reader; created from config if omitted |
| `object_detector` | `ObjectDetector` | `None` | YOLO wrapper; instantiated with model path if omitted |
| `ocr` | `OCR` | `None` | PaddleOCR instance; created via `initialize_ocr()` if omitted |
| `classifier` | `PlateClassifier` | `None` | Plate classifier (unused in validation, but initialised by base) |
| `drawer` | `BoundingBoxDrawer` | `None` | Bounding box drawer; defaults to orange "Hazard Plate" style |
| `annotated_frames_storage` | `ImageStorage` | `None` | MinIO storage for annotated frames |
| `crop_storage` | `ImageStorage` | `None` | MinIO storage for accepted crops |
| `kafka_producer` | `KafkaProducerWrapper` | `None` | Kafka producer; created from config if omitted |
| `kafka_consumer` | `KafkaConsumerWrapper` | `None` | Kafka consumer; created from config if omitted |
| `consensus_algorithm` | `ConsensusAlgorithm` | `None` | Consensus algorithm instance |

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `self.inference_latency` | `Histogram` | Prometheus histogram: YOLO inference duration (seconds) |
| `self.frames_processed_metric` | `Counter` | Prometheus counter: total frames processed by Agent C |
| `self.hazards_detected` | `Counter` | Prometheus counter: total hazard plates detected |
| `self.ocr_confidence` | `Histogram` | Prometheus histogram: OCR confidence score distribution for hazard plates |

---

#### Methods

##### `get_agent_name() -> str`

> Returns the agent's string identifier.

**Parameters**

> N/A

**Returns:** `str` — The fixed string `"AgentC"`.

**Raises:**

> N/A

**Example**
```python
agent = AgentC(**mock_deps)
assert agent.get_agent_name() == "AgentC"
```

---

##### `initialize_ocr() -> OCR`

> Instantiates and returns the OCR engine with a character set restricted to digits, spaces, and `xX`.

**Parameters**

> N/A

**Returns:** `OCR` — `OCR(allowed_chars='0123456789xX ')` instance.

**Raises:**

> N/A

**Example**
```python
ocr = agent.initialize_ocr()
```

> ⚠️ **Note:** The restricted character set prevents OCR from producing alphabetic characters, which are not valid in UN/Kemler codes.

---

##### `get_bbox_color() -> str`

> Returns the bounding box colour used by `BoundingBoxDrawer`.

**Parameters**

> N/A

**Returns:** `str` — `"orange"`.

**Raises:**

> N/A

---

##### `get_bbox_label() -> str`

> Returns the label drawn on detected bounding boxes.

**Parameters**

> N/A

**Returns:** `str` — `"Hazard Plate"`.

**Raises:**

> N/A

---

##### `get_yolo_model_path() -> str`

> Constructs the path to the hazard plate YOLO model file.

**Parameters**

> N/A

**Returns:** `str` — `<MODELS_PATH>/hazard_plate_model.pt`, where `MODELS_PATH` defaults to `/agentC/data`.

**Raises:**

> N/A

---

##### `get_bucket() -> str`

> Returns the MinIO bucket name for annotated frames and crops.

**Parameters**

> N/A

**Returns:** `str` — `"agentc-<gate_id>"`.

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

> Returns the Kafka topic to which hazard plate results are published.

**Parameters**

> N/A

**Returns:** `str` — Result of `KafkaTopicFactory.hazard_plate_results(self.config.gate_id)`.

**Raises:**

> N/A

---

##### `get_object_type() -> str`

> Returns the human-readable object type name used in log messages.

**Parameters**

> N/A

**Returns:** `str` — `"hazard plate"`.

**Raises:**

> N/A

---

##### `is_valid_detection(crop, confidence, box_index) -> bool`

> Accepts all detections unconditionally; increments `hazards_detected` counter.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `crop` | `np.ndarray` | required | Cropped image region from the detected bounding box |
| `confidence` | `float` | required | YOLO confidence score for this box |
| `box_index` | `int` | required | 1-based index of the bounding box (used in log messages) |

**Returns:** `bool` — Always `True`.

**Raises:**

> N/A

**Example**
```python
assert agent.is_valid_detection(MagicMock(), 0.9, 0) is True
```

---

##### `_build_message_for_detection(text, confidence, crop_url) -> Message`

> Parses OCR text into UN/Kemler codes and constructs the Kafka result message.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `text` | `str` | required | Raw OCR-extracted text (e.g., `"33 1203"`) or `"N/A"` |
| `confidence` | `float` | required | Final detection confidence |
| `crop_url` | `Optional[str]` | required | MinIO URL of the crop image; empty string if `None` |

**Returns:** `Message` — A `KafkaMessageProto.hazard_plate_result` message object containing `un`, `kemler`, `crop_url`, and `confidence`.

**Raises:**

> N/A

---

##### `init_metrics() -> None`

> Registers Prometheus metrics for Agent C. Called once during `__init__`.

**Parameters**

> N/A

**Returns:** `None`

**Raises:**

> N/A

---

##### `get_detection_metric() -> Optional[object]`

> Returns the `hazards_detected` counter, which `BaseAgent` increments per detected bounding box.

**Parameters**

> N/A

**Returns:** `Counter` — `self.hazards_detected`.

**Raises:**

> N/A

---

##### `_parse_detection_result(text) -> tuple[str, str]`

> Splits OCR text into Kemler and UN codes; returns `("N/A", "N/A")` for malformed input.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `text` | `str` | required | Space-separated string expected in `"KEMLER UN"` format (e.g., `"33 1203"`) |

**Returns:** `tuple[str, str]` — `(un, kemler)`. Returns `("N/A", "N/A")` if the input does not split into exactly two parts.

**Raises:**

> N/A

**Example**
```python
un, kemler = agent._parse_detection_result("33 1203")
# un → "1203", kemler → "33"

un, kemler = agent._parse_detection_result("1203")
# un → "N/A", kemler → "N/A"
```

> ⚠️ **Note:** Text with more than two space-separated parts (e.g., `"33 1203 EXTRA"`) is treated as malformed and both codes are set to `"N/A"`.

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
| `NGINX_HOST` | ❌ | `10.255.32.56` | RTMP server host |
| `NGINX_PORT` | ❌ | `1935` | RTMP server port |
| `MINIO_HOST` | ❌ | `10.255.32.82` | MinIO server host |
| `MINIO_PORT` | ❌ | `9000` | MinIO server port |
| `MINIO_SECURE` | ❌ | `False` | Whether to use TLS for MinIO |
| `MAX_FRAMES` | ❌ | `40` | Maximum frames to process per detection cycle |
| `MIN_DETECTION_CONFIDENCE` | ❌ | `0.4` | Minimum YOLO confidence threshold |
| `FRAMES_BATCH_SIZE` | ❌ | `5` | Number of frames captured per batch from the RTMP stream |

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

All exceptions raised during the main Kafka loop are caught by `BaseAgent.start()`, logged via `self.logger.exception()`, and followed by a 1-second sleep before retrying. OCR failures on individual crops are caught in `BaseAgent._process_frame()`, logged as warnings, and processing continues with the next crop. Crop upload errors are caught in `BaseAgent._process_message()` and logged as errors; a result message is still published. When `_parse_detection_result` receives unexpected input (fewer or more than two tokens), both codes are set to `"N/A"` without raising an exception.

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| `agentC_unitTest.py` | Unit | Configuration methods, `is_valid_detection` (always accepts), `_parse_detection_result` (valid format, missing parts, extra parts), metric counters |

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
- [`paddle_ocr.md`](../../shared/paddle_ocr.md)
- [`kafka_wrapper.md`](../../../shared/kafka_wrapper.md)
- [Architecture Overview](../../../docs/sketch_arquitetura/arquitetura_intelligent_logistics.md)
