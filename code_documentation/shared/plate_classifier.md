# `plate_classifier.py`

> HSV color and aspect-ratio based classifier that distinguishes license plates from hazard plates.

---

## Overview

`plate_classifier.py` provides a rule-based classifier that categorises cropped plate images into **license plates** (wide, white/yellow) or **hazard plates** (square/vertical, orange/red). It combines shape analysis (aspect ratio) with dominant-color scoring in HSV space to make a deterministic decision without any machine learning model.

The module is consumed downstream by the AI agents after object detection has extracted plate crops. It receives a BGR NumPy array and returns one of three string labels: `license_plate`, `hazard_plate`, or `unknown`. An optional visualization helper draws a colored border and label onto the crop for debugging purposes.

---

## Location
```
src/shared/src/plate_classifier.py
```

## Dependencies

### Internal
> N/A

### External
| Package | Version | Why it's used |
|---------|---------|---------------|
| `opencv-python` | `4.x` | HSV conversion, `inRange` masking, border drawing, text overlay, and image I/O |
| `numpy` | — | Array construction for HSV bounds and image type annotations |

---

## Architecture & Flow

```
[Cropped plate image (BGR)] → classify()
                                 ↓
                          Shape Analysis      ← compute width / height aspect ratio
                                 ↓
                          _analyze_colors()   ← HSV masking for license & hazard color ranges
                                 ↓
                          Rule-Based Decision  ← combine aspect ratio + color scores
                                 ↓
                          "license_plate" | "hazard_plate" | "unknown"
```

### Classification Rules (priority order)

| Priority | Condition | Result |
|----------|-----------|--------|
| 1 | AR ≥ 1.5 **and** license color score > hazard color score | `LICENSE_PLATE` |
| 2 | AR ≥ 1.5 **and** hazard color score ≤ 0.3 | `LICENSE_PLATE` |
| 3 | AR ≤ 1.2 **and** hazard color score > license color score | `HAZARD_PLATE` |
| 4 | License color score > hazard color score × 1.5 | `LICENSE_PLATE` |
| 5 | Hazard color score > license color score × 1.5 | `HAZARD_PLATE` |
| 6 | AR ≥ 1.5 (fallback) | `LICENSE_PLATE` |
| 7 | None of the above | `UNKNOWN` |

---

## Classes

### `PlateClassifier`

> Classifies plate crops into license plates or hazard plates using aspect ratio and HSV color analysis.

**Inherits from:** `None`

**Constructor**
```python
PlateClassifier()
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| — | — | — | No parameters; all thresholds and color ranges are set internally |

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `self.min_aspect_ratio_license` | `float` | Minimum aspect ratio (width/height) to consider a crop as a license plate (`1.5`) |
| `self.max_aspect_ratio_hazard` | `float` | Maximum aspect ratio to consider a crop as a hazard plate (`1.2`) |
| `self.license_plate_colors` | `list[tuple[list, list]]` | HSV lower/upper bounds for license plate colors (white, yellow) |
| `self.hazard_plate_colors` | `list[tuple[list, list]]` | HSV lower/upper bounds for hazard plate colors (orange, red part 1, red part 2) |
| `self._license_np` | `list[tuple[np.ndarray, np.ndarray]]` | Precomputed NumPy arrays of `license_plate_colors` bounds |
| `self._hazard_np` | `list[tuple[np.ndarray, np.ndarray]]` | Precomputed NumPy arrays of `hazard_plate_colors` bounds |

**Class Constants**
| Constant | Value | Description |
|----------|-------|-------------|
| `LICENSE_PLATE` | `"license_plate"` | Return label for license plates |
| `HAZARD_PLATE` | `"hazard_plate"` | Return label for hazard plates |
| `UNKNOWN` | `"unknown"` | Return label when classification is inconclusive |
| `BORDER_WIDTH` | `5` | Border width in pixels used by `visualize_classification()` |

**HSV Color Ranges**
| Category | Color | Hue | Saturation | Value |
|----------|-------|-----|------------|-------|
| License — White | `[0, 0, 200]` – `[180, 30, 255]` | Full range | Very low | High |
| License — Yellow | `[15, 80, 80]` – `[35, 255, 255]` | 15–35 | Medium–High | Medium–High |
| Hazard — Orange | `[5, 100, 100]` – `[15, 255, 255]` | 5–15 | High | High |
| Hazard — Red (pt 1) | `[0, 100, 100]` – `[5, 255, 255]` | 0–5 | High | High |
| Hazard — Red (pt 2) | `[170, 100, 100]` – `[180, 255, 255]` | 170–180 | High | High |

---

#### Methods

##### `classify(crop)`

> Classifies a crop as `LICENSE_PLATE`, `HAZARD_PLATE`, or `UNKNOWN` using aspect ratio and HSV color scoring.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `crop` | `np.ndarray \| None` | required | Cropped plate image in BGR format, or `None` |

**Returns:** `str` — One of `PlateClassifier.LICENSE_PLATE`, `PlateClassifier.HAZARD_PLATE`, or `PlateClassifier.UNKNOWN`.

**Example**
```python
from shared.src.plate_classifier import PlateClassifier

classifier = PlateClassifier()
label = classifier.classify(cropped_bgr_image)
# label → "license_plate" | "hazard_plate" | "unknown"
```

> ⚠️ **Note:** Returns `UNKNOWN` immediately if `crop` is `None`, empty, or has zero-dimension height/width.

---

##### `_analyze_colors(crop)`

> Converts the crop to HSV and computes the fraction of pixels matching license plate colors vs. hazard plate colors.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `crop` | `np.ndarray` | required | BGR image of the crop |

**Returns:** `dict[str, float]` — `{'license': score, 'hazard': score}` where each score is normalized to `0.0`–`1.0`. Returns `{'license': 0.0, 'hazard': 0.0}` if the image has zero total pixels.

**Example**
```python
scores = classifier._analyze_colors(cropped_bgr_image)
# scores → {'license': 0.42, 'hazard': 0.05}
```

---

##### `visualize_classification(crop, classification, save_path)`

> Creates a debug visualization of the crop with a colored border and text label indicating the classification result.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `crop` | `np.ndarray` | required | Original BGR image |
| `classification` | `str` | required | Classification result (`LICENSE_PLATE`, `HAZARD_PLATE`, or `UNKNOWN`) |
| `save_path` | `str \| None` | `None` | File path to save the visualization image; `None` skips saving |

**Returns:** `np.ndarray` — Copy of the image with a colored border and text overlay.

| Classification | Border Color | Label |
|----------------|-------------|-------|
| `LICENSE_PLATE` | Green `(0, 255, 0)` | `"LICENSE PLATE"` |
| `HAZARD_PLATE` | Red `(0, 0, 255)` | `"HAZARD PLATE"` |
| `UNKNOWN` | Gray `(128, 128, 128)` | `"UNKNOWN"` |

**Example**
```python
vis = classifier.visualize_classification(crop, "license_plate", save_path="/tmp/debug.jpg")
```

> ⚠️ **Note:** If `save_path` is provided and `cv2.imwrite` fails, a warning is logged but no exception is raised.

---

## Standalone Functions

> N/A

---

## Configuration & Environment Variables

> N/A

---

## Usage Example

```python
from shared.src.plate_classifier import PlateClassifier

classifier = PlateClassifier()

# Classify a cropped plate image (NumPy BGR array)
label = classifier.classify(cropped_plate_bgr)
print(f"Classification: {label}")

# Visualize and optionally save
vis = classifier.visualize_classification(
    cropped_plate_bgr,
    label,
    save_path="/tmp/plate_debug.jpg"
)
```

---

## Error Handling

The `classify()` method never raises exceptions — it returns `UNKNOWN` for any invalid input. The strategy is:

- **`None` or empty crop**: logged at debug level, returns `UNKNOWN`.
- **Zero-dimension crop** (height or width is 0): logged at debug level, returns `UNKNOWN`.
- **`visualize_classification` save failure**: `cv2.imwrite` return value is checked; failure is logged as a warning but does not raise.

Logging uses the `"PlateClassifier"` logger name.

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| `plate_classifier_unit_test.py` | Unit | Classification logic, color analysis, edge cases |
| `plate_classifier_integration_test.py` | Integration | End-to-end classification with real or representative images |

To run:
```bash
pytest src/shared/tests/plate_classifier_unit_test.py
pytest src/shared/tests/plate_classifier_integration_test.py
```

---

## Known Issues / TODOs

> N/A

---

## Changelog

> N/A

---

## Related Docs

- [`object_detector.md`](./object_detector.md)
- [`paddle_ocr.md`](./paddle_ocr.md)
- [`bounding_box_drawer.md`](./bounding_box_drawer.md)
