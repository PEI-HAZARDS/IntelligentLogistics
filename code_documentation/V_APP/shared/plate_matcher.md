# `plate_matcher.py`

> License plate fuzzy-matching utilities reconciling OCR-read plates against database candidates using Levenshtein distance and/or a confusion matrix.

---

## Overview

`PlateMatcher` provides robust matching logic to align noisy OCR license plate strings against an expected list of database candidates (e.g., from scheduled appointments). It corrects common OCR optical confusions (like reading an 'O' as a '0' or an 'I' as a '1') without rejecting valid trucks. 

It supports three operating modes:
1. `CONFUSION_MATRIX`: Structurally exact match using a character substitution matrix for visually similar characters.
2. `LEVENSHTEIN`: Standard Levenshtein edit distance up to a configurable threshold.
3. `HYBRID`: Attempts a confusion-matrix match first (preferred for accuracy), and falls back to Levenshtein.

---

## Location
```
src/V_APP/shared/src/plate_matcher.py
```

## Dependencies

### Internal
| Module | Why it's used |
|--------|---------------|
| `shared/src/utils.py` | `levenshtein_distance` helper |

### External
> N/A

---

## Architecture & Flow

```
[OCR Text: "AB1ZCD"] 
        │
        ▼
   PlateMatcher.match_plate(..., db_plates=["AB12CD"])
        │
        ├─ Exact Match? (No)
        ├─ Confusion Matrix Expansion? (Generates 'AB12CD', 'AB17CD') -> Matches!
        └─ Returns "AB12CD"
```

---

## Classes

### `PlateMatcherMode` (Enum)

> Enumeration of the matching strategies.

- `HYBRID`: Tries confusion matrix, then Levenshtein.
- `LEVENSHTEIN`: Only uses edit distance.
- `CONFUSION_MATRIX`: Only uses exact substitution matches.

---

### `PlateMatcher`

> Matches license plates against a database list, tolerating OCR errors.

**Inherits from:** `None`

**Constructor**
```python
PlateMatcher(mode: PlateMatcherMode = PlateMatcherMode.HYBRID, max_distance: int = 2)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mode` | `PlateMatcherMode` | `HYBRID` | Matching strategy |
| `max_distance` | `int` | `2` | Maximum edit distance |

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `self.confusion_matrix` | `dict` | Maps characters to visually similar alternatives |

---

#### Methods

##### `match_plate(ocr_text, db_plates)`

> Matches an OCR-read plate string against a list of database candidates using the configured mode.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `ocr_text` | `str` | required | OCR string |
| `db_plates` | `list` | required | List of appointment candidates |

**Returns:** `str | None` — The best matching original database string, or `None`.

---

##### `_generate_plate_candidates(ocr_text, max_substitutions)`

> Generates plate variants by substituting visually similar characters up to `max_substitutions`.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `ocr_text` | `str` | required | Normalised OCR text |
| `max_substitutions` | `int` | `0` | Max character changes allowed |

**Returns:** `list[str]` — Possible structural variants.

---

## Standalone Functions

> N/A

---

## Configuration & Environment Variables

> N/A

---

## Usage Example

```python
from V_APP.shared.src.plate_matcher import PlateMatcher, PlateMatcherMode

matcher = PlateMatcher(mode=PlateMatcherMode.HYBRID, max_distance=2)

# Exact match with padding
result = matcher.match_plate("AB 12 CD", ["AB12CD", "XY99ZZ"]) # returns "AB12CD"

# Fuzzy match (Z instead of 2)
result = matcher.match_plate("AB1ZCD", ["AB12CD", "XY99ZZ"]) # returns "AB12CD"
```

---

## Error Handling

Missing or empty database lists immediately return `None` with a warning log. Normalization ensures case/hyphen formatting issues don't crash or false-fail the matching logic.

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| `plate_matcher_unitTest.py` | Unit | Exact matches, confusion matrix scenarios, Levenshtein scenarios, Hybrid fallback, and invalid inputs |

To run:
```bash
pytest src/V_APP/shared/tests/plate_matcher_unitTest.py
```

---

## Known Issues / TODOs

> N/A

---

## Changelog

> N/A

---

## Related Docs

- [`base_decision_engine.md`](./base_decision_engine.md)
