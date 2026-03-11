# `bounding_box_drawer.py`

> Draws bounding boxes with optional confidence-annotated labels on OpenCV images, with automatic text-color contrast and edge-aware label placement.

---

## Overview

`BoundingBoxDrawer` provides a configurable, reusable utility for annotating images with detection results. Given a list of bounding boxes (optionally with confidence scores), it draws colored rectangles and labels on a frame using OpenCV primitives.

Within the IntelligentLogistics pipeline, `AgentA` uses this module (configured green, label `"truck"`) to annotate detected trucks before uploading frames to MinIO via `ImageStorage`. `BaseAgent` also instantiates it as a shared dependency, allowing each agent subclass to configure its own box color and label. The module handles edge cases such as labels near image boundaries (repositioning above or below the box), unknown color names (defaulting to black), and malformed box entries (skipped with a warning).

It does **not** perform detection (see `object_detector.py`) or image storage (see `image_storage.py`).

---

## Location
```
src/shared/src/bounding_box_drawer.py
```

## Dependencies

### Internal
> N/A

### External
| Package | Version | Why it's used |
|---------|---------|---------------|
| `opencv-python` | `4.x` | Drawing rectangles, text, and computing text sizes |
| `numpy` | — | Image array type (`np.ndarray`) |

> Standard library modules used: `logging`, `typing`.

---

## Architecture & Flow

```
  AgentA / BaseAgent
       │
       │  draw_box(frame, boxes)
       ▼
 ┌───────────────────┐
 │ BoundingBoxDrawer  │
 │                    │
 │  cv2.rectangle()   │──► Box outline
 │  _draw_label()     │──► Background rect + text
 └───────────────────┘
       │
       ▼
   Annotated frame (in-place)
```

**Flow:**
1. Consumer creates a `BoundingBoxDrawer` with a color, thickness, and label.
2. After detection, `draw_box(frame, boxes)` is called with the frame and detection results.
3. For each valid box, a rectangle is drawn and an optional label (with confidence) is rendered.
4. Label placement automatically adapts to image boundaries.
5. Text color is auto-selected (white or black) for contrast against the label background.
6. The annotated frame is returned (modified in-place).

---

## Classes

### `BoundingBoxDrawer`

> Draws bounding boxes and labels on images using OpenCV.

**Inherits from:** `None`

**Constructor**
```python
BoundingBoxDrawer(color: str = "black", thickness: int = 1, label: str = "")
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `color` | `str` | `"black"` | Color name for boxes (case-insensitive). Supported: `red`, `orange`, `green`, `blue`, `white`, `black`, `yellow`. Falls back to black if unknown. |
| `thickness` | `int` | `1` | Line thickness in pixels. Must be ≥ 1. |
| `label` | `str` | `""` | Optional label text drawn alongside each box. |

**Constructor Raises:**
- `ValueError` — If `thickness < 1`.

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `self.color` | `str` | Configured color name |
| `self.thickness` | `int` | Line thickness in pixels |
| `self.label` | `str` | Label text prefix for each box |

**Class-level Constants**
| Constant | Type | Value | Description |
|----------|------|-------|-------------|
| `_COLOR_MAP` | `dict[str, tuple[int,int,int]]` | `{"red": (0,0,255), ...}` | BGR color lookup for 7 named colors |
| `_DARK_BG_THRESHOLD` | `int` | `400` | Sum-of-BGR threshold; below → white text, above → black text |

**Type Aliases**
| Name | Definition | Description |
|------|------------|-------------|
| `Box` | `Union[Tuple[float,float,float,float], Tuple[float,float,float,float,float]]` | A bounding box: `(x1, y1, x2, y2)` or `(x1, y1, x2, y2, confidence)` |

---

#### Methods

##### `draw_box(frame, boxes)`

> Draws bounding-box rectangles and optional confidence-annotated labels on an image.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `frame` | `np.ndarray` | required | Image (HWC, BGR) to draw on |
| `boxes` | `List[Box]` | required | List of bounding boxes, each `(x1, y1, x2, y2)` or `(x1, y1, x2, y2, confidence)` |

**Returns:** `np.ndarray` — The same frame with drawings applied (modified in-place).

**Raises:**

> N/A (invalid boxes are skipped with a warning log)

**Example**
```python
from shared.src.bounding_box_drawer import BoundingBoxDrawer

drawer = BoundingBoxDrawer(color="green", thickness=2, label="truck")

# boxes from ObjectDetector.get_boxes()
boxes = [[120.5, 80.3, 450.2, 310.7, 0.92]]
annotated = drawer.draw_box(frame, boxes)
# annotated has green rectangles with "truck 0.92" labels
```

> ⚠️ **Note:** The frame is modified **in-place** — the returned reference points to the same array. Boxes with fewer than 4 elements are silently skipped. If a box has a 5th element, it is displayed as a confidence score in the label.

---

##### `_bgr()`

> Returns the BGR tuple for the configured color name.

**Parameters**

> N/A

**Returns:** `Tuple[int, int, int]` — BGR color tuple. Falls back to `(0, 0, 0)` if the color is not in the map.

**Raises:**

> N/A

---

##### `_draw_label(frame, x1_i, y1_i, label_text, color, font, font_scale, text_thickness)`

> Draws a filled background rectangle and text label for a single bounding box. Handles edge-aware placement: labels are placed above the box by default, or below if there is insufficient room at the top of the image. Horizontal position is clamped to prevent overflow on the right edge.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `frame` | `np.ndarray` | required | Image array to draw on (modified in-place) |
| `x1_i` | `int` | required | Left x-coordinate of the bounding box (pixels) |
| `y1_i` | `int` | required | Top y-coordinate of the bounding box (pixels) |
| `label_text` | `str` | required | Text string to render |
| `color` | `Tuple[int, int, int]` | required | BGR background color for the label rectangle |
| `font` | `int` | `cv2.FONT_HERSHEY_SIMPLEX` | OpenCV font constant |
| `font_scale` | `float` | `0.5` | Font scale factor |
| `text_thickness` | `int` | `1` | Thickness of the rendered text |

**Returns:** `None`

**Raises:**

> N/A

> ⚠️ **Note:** Text color is automatically chosen for contrast: white text on dark backgrounds (BGR sum < 400), black text on light backgrounds. If the frame lacks a `shape` attribute, bounds-checking is skipped with a warning.

---

## Standalone Functions

> N/A

---

## Configuration & Environment Variables

> N/A

---

## Usage Example

End-to-end usage as seen in `AgentA`:
```python
from shared.src.bounding_box_drawer import BoundingBoxDrawer
from shared.src.object_detector import ObjectDetector
from shared.src.image_storage import ImageStorage

drawer = BoundingBoxDrawer(color="green", thickness=2, label="truck")
detector = ObjectDetector("/agentA/data/truck_model.pt", class_id=7)

# Detect and annotate
results = detector.detect(frame)
if detector.object_found(results):
    boxes = detector.get_boxes(results)
    annotated_frame = drawer.draw_box(frame, boxes)
    # Upload annotated frame to MinIO
    storage.upload_memory_image(annotated_frame, "detection.jpg", image_type="annotated_frames")
```

---

## Error Handling

- **Invalid thickness** — `ValueError` raised in the constructor if `thickness < 1`.
- **Unknown color** — Defaults to `"black"` with a `WARNING` log. No exception raised.
- **Malformed boxes** — Boxes with fewer than 4 elements are silently skipped via `continue`. Any exception during individual box drawing is caught, logged at `WARNING`, and the loop continues to the next box.
- **Missing frame shape** — If `frame.shape` raises `AttributeError` in `_draw_label`, bounds-checking is skipped and drawing proceeds without image-boundary clamping.

Logging uses a named logger (`BoundingBoxDrawer`) at `DEBUG` and `WARNING` levels.

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| `bounding_box_drawer_unit_test.py` | Unit | Initialization (defaults, custom params, invalid thickness, unknown color, case-insensitivity), BGR color mapping for all 7 colors, drawing boxes (with/without confidence, with labels), empty box lists, malformed boxes, label contrast (dark vs light backgrounds), edge-aware label placement |

To run:
```bash
pytest src/shared/tests/bounding_box_drawer_unit_test.py
```

---

## Known Issues / TODOs

> N/A

---

## Changelog

> N/A

---

## Related Docs

- [object_detector.md](./object_detector.md) — Produces the bounding boxes consumed by this module
- [image_storage.md](./image_storage.md) — Stores the annotated frames after drawing
- [base_agent.md](./base_agent.md) — Base class that instantiates `BoundingBoxDrawer` for agents
