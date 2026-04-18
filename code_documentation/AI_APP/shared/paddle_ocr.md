# `paddle_ocr.py`

> PaddleOCR-based text extraction optimized for license and hazard plate recognition.

---

## Overview

`paddle_ocr.py` provides OCR (Optical Character Recognition) capabilities for the Intelligent Logistics pipeline, specifically tuned for reading short text lines found on license plates and hazard plates. It wraps the PaddleOCR engine with a preprocessing pipeline that resizes, pads, and converts images to grayscale before inference, improving accuracy on small, noisy plate crops.

The module is consumed by `base_agent.py` in the shared library, which exposes the OCR instance to all AI agents. `agentB.py` and `agentC.py` import the `OCR` class directly as well. It accepts images in multiple formats (file path, PIL `Image`, or NumPy array), normalizes them to OpenCV BGR, and returns a `(text, confidence)` tuple. It does not handle plate detection or localization — those responsibilities belong to `object_detector.py` and `bounding_box_drawer.py`.

---

## Location
```
src/AI_APP/shared/src/paddle_ocr.py
```

## Dependencies

### Internal
> N/A

### External
| Package | Version | Why it's used |
|---------|---------|---------------|
| `opencv-python` | `4.x` | Image reading, resizing, color conversion, and padding |
| `numpy` | — | Array operations and image type checking |
| `Pillow` | — | PIL `Image` input support |
| `paddleocr` | — | Core OCR inference engine |

---

## Architecture & Flow

```
[Cropped plate image] → OCR.extract_text()
                            ↓
                     _to_cv_image()        ← normalize input format
                            ↓
                     _preprocess_plate()   ← resize, pad, grayscale
                            ↓
                     PaddleOCR.predict()   ← inference
                            ↓
                     _parse_result()       ← extract text + confidence
                            ↓
                     _filter_text()        ← strip disallowed characters
                            ↓
                     (text, confidence)
```

---

## Classes

### `OCR`

> PaddleOCR-based OCR class optimized for license/hazard plate recognition.

**Inherits from:** `None`

**Constructor**
```python
OCR(allowed_chars: str | None = None)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `allowed_chars` | `str \| None` | `None` | Character whitelist for filtering OCR output. Defaults to `ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-` when `None` or empty. |

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `self.paddle_ocr` | `PaddleOCR` | Underlying PaddleOCR engine instance configured with angle classification and English language |
| `self.allowed_chars` | `str` | Character whitelist used by `_filter_text()` to strip invalid characters from OCR output |

**Class Constants**
| Constant | Value | Description |
|----------|-------|-------------|
| `MIN_HEIGHT` | `10` | Minimum image height in pixels; images below this are rejected |
| `MIN_WIDTH` | `20` | Minimum image width in pixels; images below this are rejected |
| `DEFAULT_TARGET_HEIGHT` | `64` | Target height in pixels for the resize step |
| `DEFAULT_PADDING` | `10` | Padding in pixels added on all sides after resizing |
| `DEFAULT_CONFIDENCE` | `0.5` | Fallback confidence score when PaddleOCR does not provide one |

---

#### Methods

##### `extract_text(cv_img)`

> Extract text from a license/hazard plate crop image.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `cv_img` | `str \| Image.Image \| np.ndarray` | required | Cropped plate image as a file path, PIL Image, or OpenCV BGR array |

**Returns:** `tuple[str, float]` — A tuple of `(text, confidence)` where `text` is the filtered OCR output and `confidence` is the average confidence score. Returns `("", 0.0)` on failure.

**Raises:**
- Does not raise; all exceptions are caught internally and logged. Returns `("", 0.0)` on error.

**Example**
```python
from shared.src.paddle_ocr import OCR

ocr = OCR()
text, confidence = ocr.extract_text(cropped_plate_array)
# text → "AB12CD", confidence → 0.92
```

> ⚠️ **Note:** `TypeError` from unsupported input types and `ValueError` from undersized images are caught and logged as warnings. `RuntimeError` from PaddleOCR inference failures is caught and logged as an error. All return `("", 0.0)`.

---

##### `_to_cv_image(image)`

> Convert various image formats to OpenCV BGR format.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `image` | `str \| Image.Image \| np.ndarray` | required | Input image as a file path, PIL Image, or NumPy array |

**Returns:** `np.ndarray | None` — OpenCV BGR image, or `None` if `cv2.imread` fails for a file path.

**Raises:**
- `TypeError` — If the input type is not `str`, `Image.Image`, or `np.ndarray`.

**Example**
```python
img = ocr._to_cv_image("/path/to/plate.jpg")
# img → numpy BGR array

img = ocr._to_cv_image(pil_image)
# img → numpy BGR array converted from RGB
```

---

##### `_resize_and_pad(img, target_height)`

> Resize image to a target height maintaining aspect ratio, then add border padding.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `img` | `np.ndarray` | required | Input OpenCV image |
| `target_height` | `int` | `64` | Target height in pixels for resizing |

**Returns:** `np.ndarray` — Resized and padded image using Lanczos resampling and replicate border padding.

**Example**
```python
padded = ocr._resize_and_pad(img, target_height=64)
# padded.shape → (84, new_w + 20, channels)  # 64 + 2*10 padding
```

---

##### `_preprocess_plate(cv_img)`

> Preprocess a license/hazard plate image for OCR by resizing, padding, converting to grayscale, and back to BGR.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `cv_img` | `np.ndarray \| None` | required | Input OpenCV image |

**Returns:** `np.ndarray` — Preprocessed BGR image ready for PaddleOCR inference.

**Raises:**
- `ValueError` — If `cv_img` is `None` or dimensions are below `MIN_WIDTH` / `MIN_HEIGHT`.

**Example**
```python
processed = ocr._preprocess_plate(cropped_plate)
result = ocr.paddle_ocr.predict(processed)
```

---

##### `_filter_text(text)`

> Filter and clean OCR output to only allowed characters.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `text` | `str` | required | Raw OCR text output |

**Returns:** `str` — Uppercased text containing only characters in `self.allowed_chars`, with leading/trailing whitespace and hyphens stripped.

**Example**
```python
ocr._filter_text("ab-12!cd-")
# → "AB-12CD"
```

---

##### `_parse_dict_item(item, texts, confidences)`

> Parse a dictionary-format result item from the new PaddleOCR API. Mutates `texts` and `confidences` in place.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `item` | `dict` | required | Single result item with `rec_texts`/`rec_scores` or `text`/`score` keys |
| `texts` | `list[str]` | required | Accumulator list for recognized text strings |
| `confidences` | `list[float]` | required | Accumulator list for confidence scores |

**Returns:** `None`

---

##### `_parse_list_item(item, texts, confidences)`

> Parse a list/tuple-format result item from the old PaddleOCR API. Mutates `texts` and `confidences` in place.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `item` | `list \| tuple` | required | Single result item where the last element is a `(text, confidence)` pair or a bare string |
| `texts` | `list[str]` | required | Accumulator list for recognized text strings |
| `confidences` | `list[float]` | required | Accumulator list for confidence scores |

**Returns:** `None`

> ⚠️ **Note:** Items with fewer than 2 elements are silently skipped with a debug log. Bare string items use `DEFAULT_CONFIDENCE` (0.5) as the confidence score.

---

##### `_parse_result(result)`

> Parse the full PaddleOCR prediction result and extract concatenated text with an average confidence score.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `result` | `list` | required | Raw PaddleOCR prediction output |

**Returns:** `tuple[str, float]` — Space-joined text from all detected regions and the average confidence across regions. Returns `("", 0.0)` if no text is found or parsing fails.

**Raises:**
- Does not raise; `TypeError`, `KeyError`, and `IndexError` are caught internally and logged as warnings.

**Example**
```python
result = ocr.paddle_ocr.predict(processed_image)
text, conf = ocr._parse_result(result)
# text → "AB 12CD", conf → 0.89
```

---

## Standalone Functions

> N/A

---

## Configuration & Environment Variables

> N/A

---

## Usage Example

```python
from shared.src.paddle_ocr import OCR

# Default character set (A-Z, 0-9, -)
ocr = OCR()

# Custom character set for numeric-only hazard plates
hazard_ocr = OCR(allowed_chars="0123456789")

# Extract text from a cropped plate image (NumPy array)
text, confidence = ocr.extract_text(cropped_plate_bgr)
print(f"Plate: {text}, Confidence: {confidence:.2f}")

# Extract text from a file path
text, confidence = ocr.extract_text("/path/to/plate_crop.jpg")

# Extract text from a PIL Image
from PIL import Image
pil_img = Image.open("/path/to/plate_crop.jpg")
text, confidence = ocr.extract_text(pil_img)
```

---

## Error Handling

All errors in `extract_text()` are caught internally — the method never raises exceptions to callers. The strategy is:

- **`TypeError`** (unsupported image type): logged as a warning, returns `("", 0.0)`.
- **`ValueError`** (image too small or `None`): logged as a warning, returns `("", 0.0)`.
- **`RuntimeError`** (PaddleOCR inference failure): logged as an error, returns `("", 0.0)`.
- **Constructor failure** (`__init__`): if PaddleOCR cannot load, a `RuntimeError` is raised with a critical log, propagating to the caller.
- **Result parsing** (`_parse_result`): `TypeError`, `KeyError`, and `IndexError` are caught and logged as warnings, returning `("", 0.0)`.

Logging uses the `"PlateOCR"` logger name.

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| `paddle_ocr_unit_test.py` | Unit | Initialization, image conversion, preprocessing, text filtering, result parsing, extract_text end-to-end with mocked PaddleOCR |

To run:
```bash
pytest src/AI_APP/shared/tests/paddle_ocr_unit_test.py
```

---

## Known Issues / TODOs

> Improve pre-processing options also allowing for selection of wich methods to apply for the given image.

---

## Changelog

| Version / Date | Change |
|----------------|--------|
| `2026-04-18` | Reviewed AI_APP documentation for consistency, aligned paths/test commands, and validated deployment host mapping (AI_APP `10.255.32.107`, Streaming `10.255.32.56`, UI `10.255.32.108`, V_APP `10.255.32.70`). |

---

## Related Docs

- [`base_agent.md`](.././base_agent.md)
- [`object_detector.md`](./object_detector.md)
- [`bounding_box_drawer.md`](./bounding_box_drawer.md)
