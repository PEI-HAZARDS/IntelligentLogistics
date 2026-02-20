# `object_detector.py`

> Thin wrapper around Ultralytics YOLO for single-class or multi-class object detection with context-manager support.

---

## Overview

`ObjectDetector` encapsulates model loading, inference, result parsing, and resource cleanup for Ultralytics YOLO models. It provides a simple API where consumers call `detect()` on a frame and inspect results through `object_found()` and `get_boxes()`.

Within the IntelligentLogistics pipeline, `AgentA` uses this module with a truck-detection model (class ID `7`) to identify trucks in low-quality RTMP stream frames. `BaseAgent` also instantiates it as a shared dependency for agents that need YOLO inference. The module supports filtering detections to a single YOLO class ID and implements the context-manager protocol (`with` statement) for automatic resource cleanup.

It does **not** handle frame acquisition (see `stream_manager.py`), image storage (see `image_storage.py`), or result publishing (see `kafka_wrapper.py`).

---

## Location
```
src/shared/src/object_detector.py
```

## Dependencies

### Internal
> N/A

### External
| Package | Version | Why it's used |
|---------|---------|---------------|
| `ultralytics` | — | YOLO model loading and inference |
| `numpy` | — | Image array type (`np.ndarray`) for input frames |

> Standard library modules used: `os`, `logging`.

---

## Architecture & Flow

```
  AgentA / BaseAgent
       │
       │  detect(frame)
       ▼
 ┌────────────────┐
 │ ObjectDetector  │
 │                 │
 │  YOLO(model)    │──► Ultralytics inference
 │  get_boxes()    │──► [x1, y1, x2, y2, conf]
 │  object_found() │──► bool
 └────────────────┘
```

**Flow:**
1. Consumer instantiates `ObjectDetector` with a model path and optional class filter.
2. On each frame, `detect(image)` runs YOLO inference and returns raw result objects.
3. `object_found(results)` checks for any detections.
4. `get_boxes(results)` extracts bounding box coordinates and confidence scores.
5. `close()` (or context-manager exit) releases model resources.

---

## Classes

### `ObjectDetector`

> Wrapper around Ultralytics YOLO for object detection.

**Inherits from:** `None`

**Constructor**
```python
ObjectDetector(model_path: str, class_id: int = -1)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_path` | `str` | required | Path to the YOLO model weights file (`.pt`) |
| `class_id` | `int` | `-1` | YOLO class ID to filter detections; `-1` means no filter (all classes) |

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `self.model_path` | `str` | Path to the loaded model file |
| `self.model` | `YOLO` | Ultralytics YOLO model instance |
| `self.class_id` | `int` | Class ID filter (`-1` = all classes) |

**Constructor Raises:**
- `FileNotFoundError` — If `model_path` does not point to an existing file.
- `RuntimeError` — If the YOLO model fails to load (wraps the underlying exception).

---

#### Methods

##### `detect(image, suppress_output=True)`

> Runs YOLO inference on an image.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `image` | `np.ndarray` | required | Input image as a NumPy array (HWC, BGR) |
| `suppress_output` | `bool` | `True` | If `True`, suppresses YOLO console output |

**Returns:** `list` — List of YOLO result objects.

**Raises:**
- `ValueError` — If `image` is `None`.

**Example**
```python
from shared.src.object_detector import ObjectDetector

detector = ObjectDetector("/agentA/data/truck_model.pt", class_id=7)
results = detector.detect(frame)
```

> ⚠️ **Note:** When `class_id >= 0`, the `classes` filter is passed to YOLO so only detections of that class are returned by the model.

---

##### `get_boxes(results)`

> Extracts bounding boxes and confidence scores from YOLO results.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `results` | `list` | required | YOLO results list from `detect()` |

**Returns:** `list[list[float]]` — List of `[x1, y1, x2, y2, confidence]` lists with plain floats. Returns an empty list if no detections.

**Raises:**

> N/A

**Example**
```python
results = detector.detect(frame)
boxes = detector.get_boxes(results)
# boxes → [[120.5, 80.3, 450.2, 310.7, 0.92], ...]
```

> ⚠️ **Note:** Only processes `results[0].boxes` — assumes single-image inference (batch size 1).

---

##### `object_found(results)`

> Checks whether any objects were detected.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `results` | `list` | required | YOLO results list from `detect()` |

**Returns:** `bool` — `True` if at least one bounding box was found.

**Raises:**

> N/A

**Example**
```python
results = detector.detect(frame)
if detector.object_found(results):
    boxes = detector.get_boxes(results)
```

---

##### `close()`

> Releases YOLO model resources.

**Parameters**

> N/A

**Returns:** `None`

**Raises:**

> N/A

---

##### `__enter__()`

> Returns `self` for context-manager usage.

**Parameters**

> N/A

**Returns:** `ObjectDetector` — The instance itself.

---

##### `__exit__(exc_type, exc_val, exc_tb)`

> Calls `close()` and returns `False` (does not suppress exceptions).

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `exc_type` | `type \| None` | required | Exception type, if any |
| `exc_val` | `BaseException \| None` | required | Exception value, if any |
| `exc_tb` | `TracebackType \| None` | required | Traceback, if any |

**Returns:** `bool` — Always `False` (exceptions are not suppressed).

---

## Standalone Functions

> N/A

---

## Configuration & Environment Variables

> N/A

> `ObjectDetector` does not read environment variables. The model path is passed by the caller. `AgentA` resolves it via `os.getenv("MODELS_PATH", "/agentA/data") + "/truck_model.pt"`.

---

## Usage Example

End-to-end usage as seen in `AgentA`:
```python
from shared.src.object_detector import ObjectDetector

# Load a truck detection model, filtering to class ID 7
detector = ObjectDetector("/agentA/data/truck_model.pt", class_id=7)

# Run detection
results = detector.detect(frame)

if detector.object_found(results):
    boxes = detector.get_boxes(results)
    for x1, y1, x2, y2, conf in boxes:
        print(f"Truck at ({x1:.0f},{y1:.0f})-({x2:.0f},{y2:.0f}), conf={conf:.2f}")

# Cleanup
detector.close()
```

Using the context manager:
```python
with ObjectDetector("/agentA/data/truck_model.pt", class_id=7) as detector:
    results = detector.detect(frame)
    if detector.object_found(results):
        boxes = detector.get_boxes(results)
# Model resources released automatically
```

---

## Error Handling

Errors are **propagated** to the caller — this module does not silently swallow exceptions:

- **Model not found** — `FileNotFoundError` raised in the constructor if the model file does not exist.
- **Model load failure** — `RuntimeError` raised in the constructor, wrapping the underlying Ultralytics exception.
- **None image** — `ValueError` raised in `detect()` if the input image is `None`.
- **Empty results** — `get_boxes()` and `object_found()` handle empty/missing results gracefully by returning `[]` and `False` respectively.

Logging uses a named logger (`ObjectDetector`). The `ultralytics` library logger is suppressed to `WARNING` level at module load to reduce noise.

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| `object_detector_unit_test.py` | Unit | Initialization (with/without class filter, file-not-found, load failure), detection (normal, with class filter, None image), box extraction (normal, empty, no boxes), object-found checks, resource cleanup |

To run:
```bash
pytest src/shared/tests/object_detector_unit_test.py
```

---

## Known Issues / TODOs

> N/A

---

## Changelog

> N/A

---

## Related Docs

- [`stream_manager.md`](./stream_manager.md) — Provides frames consumed by `ObjectDetector`
- [`image_storage.md`](./image_storage.md) — Stores annotated frames after detection
- [`base_agent.md`](./base_agent.md) — Base class that instantiates `ObjectDetector` for agents
