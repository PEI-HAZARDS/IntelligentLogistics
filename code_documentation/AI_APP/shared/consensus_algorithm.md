# `consensus_algorithm.py`

> Character-level voting algorithm that builds reliable OCR text from multiple noisy frame readings.

---

## Overview

`consensus_algorithm.py` implements a position-based character voting system to produce a single, high-confidence text result from many OCR readings across consecutive video frames. Because OCR on individual frames is often noisy — characters get misread, confidence varies, and text length may fluctuate — the algorithm aggregates votes for each character position across multiple readings and only "decides" a position once a character reaches a configurable vote threshold. Full consensus is considered reached only when **all expected positions** are decided.

When full consensus is not reached, partial results use a bounded confidence model that blends:
- completeness of decided positions, and
- quality signal (`agreement_score × average_ocr_confidence`).

The module is consumed exclusively by `base_agent.py`, which creates one `ConsensusAlgorithm` instance per detection cycle. When `AgentB` or `AgentC` detects a plate, the base agent calls `add_to_consensus()` on every OCR reading and `add_candidate_crop()` for every detected crop. After a maximum number of frames or when early consensus is reached, it calls `build_final_text()` to produce the result and `select_best_crop()` to pick the image whose OCR text most closely matches the consensus.

The algorithm does **not** perform OCR itself — that is the responsibility of `paddle_ocr.py`. It also does not handle plate detection (handled by `object_detector.py`) or image storage (handled by `image_storage.py`).

---

## Location
```
src/AI_APP/shared/src/consensus_algorithm.py
```

## Dependencies

### Internal
| Module | Why it's used |
|--------|---------------|
| `shared/src/utils.py` → `levenshtein_distance` | Measures edit distance between candidate crop texts and the final consensus text for best-crop selection |

### External
| Package | Version | Why it's used |
|---------|---------|---------------|
| _N/A_ | _N/A_ | No external packages are imported directly by this module |

---

## Architecture & Flow

```
Frame 1 OCR → add_to_consensus("AB12CD", 0.92)  ──┐
Frame 2 OCR → add_to_consensus("AB1ZCD", 0.88)  ──┤
Frame 3 OCR → add_to_consensus("AB12CD", 0.95)  ──┤  Character voting
Frame N OCR → add_to_consensus("AB12CD", 0.91)  ──┘  per position
                          │
                          ▼
              Position voting matrix:
              pos 0: {A:8}  → decided 'A'
              pos 1: {B:8}  → decided 'B'
              pos 2: {1:7, Z:1} → decided '1'
              pos 3: {2:8}  → decided '2'
              pos 4: {C:8}  → decided 'C'
              pos 5: {D:8}  → decided 'D'
                          │
                          ▼
              check_full_consensus() → True (6/6 = 100% of expected positions)
                          │
                          ▼
              build_final_text() → "AB12CD"
                          │
                          ▼
              compute_consensus_confidence()
              → agreement × avg_ocr_conf = 0.93 × 0.915 ≈ 0.85
                          │
                          ▼
              select_best_crop("AB12CD") → crop with highest
                                           similarity to final text
```

---

## Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `DECISION_THRESHOLD` | `8` | Number of votes a character needs at a position to be "decided" |
| `MIN_TEXT_LENGTH` | `4` | Minimum normalized text length for a reading to count |
| `MIN_CONFIDENCE_CONSENSUS` | `0.80` | Minimum OCR confidence for a reading to count |

---

## Classes

### `ConsensusAlgorithm`

> Character-level voting system that aggregates OCR readings to produce a consensus text result.

**Inherits from:** `None`

**Constructor**
```python
ConsensusAlgorithm()
```

No parameters. All state is initialized to empty/default values.

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `self.consensus_reached` | `bool` | Whether full consensus has been reached |
| `self.counter` | `dict[int, dict[str, int]]` | Vote matrix — `{position: {character: vote_count}}` |
| `self.decided_chars` | `dict[int, str]` | Characters decided per position (votes ≥ `DECISION_THRESHOLD`) |
| `self.frames_processed` | `int` | Number of frames processed |
| `self.length_counter` | `dict[int, int]` | Frequency of text lengths seen — `{length: count}` |
| `self.best_crop` | `Any \| None` | Best crop image after `select_best_crop()` is called |
| `self.best_confidence` | `float` | Confidence of the best crop |
| `self.candidate_crops` | `list[dict]` | Candidate crops list, each `{"crop", "text", "confidence", "is_fallback"}` |
| `self.accepted_confidences` | `list[float]` | OCR confidence scores of readings that passed validation and contributed to the voting matrix |

---

#### Methods

##### `reset()`

> Reset all consensus state for a new detection cycle.

**Parameters:** None

**Returns:** `None`

---

##### `add_to_consensus(text, confidence)`

> Add an OCR reading to the voting matrix. Each character in the text votes for its position.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `text` | `str` | required | Raw OCR text from a single frame |
| `confidence` | `float` | required | OCR confidence score for this reading |

**Returns:** `None`

**Filtering (reading is silently skipped if):**
- Confidence < `MIN_CONFIDENCE_CONSENSUS` (0.80)
- Normalized text length < `MIN_TEXT_LENGTH` (4)
- Text length doesn't match the most common length seen so far (after 3+ samples)

**Vote weighting:**
- Confidence ≥ 0.95 → **2 votes** per character
- Confidence < 0.95 → **1 vote** per character

**Example**
```python
ca = ConsensusAlgorithm()
ca.add_to_consensus("AB12CD", 0.92)  # 1 vote per position
ca.add_to_consensus("AB12CD", 0.97)  # 2 votes per position (high confidence)
ca.add_to_consensus("XY99ZZ", 0.60)  # skipped (confidence < 0.80)
```

> ⚠️ **Note:** Text is normalized (uppercased, dashes removed) before voting. Length outliers after 3+ samples are discarded to prevent misaligned votes from corrupting the matrix.

---

##### `add_candidate_crop(crop, text, confidence, is_fallback)`

> Register a candidate crop image for later best-crop selection.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `crop` | `Any` | required | Cropped image (NumPy array) |
| `text` | `str` | required | OCR text for this crop (empty string for fallback) |
| `confidence` | `float` | required | OCR confidence (or YOLO confidence for fallback crops) |
| `is_fallback` | `bool` | `False` | `True` if crop has no OCR text (YOLO detection only) |

**Returns:** `None`

**Deduplication logic:**
- If a candidate with the same text already exists → replace only if the new one is better.
- If both are fallback crops → keep the one with higher confidence.
- Otherwise → add as a new candidate.

---

##### `update_position_decision(pos, char)`

> Mark a character as "decided" at a position if its vote count has reached the threshold.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `pos` | `int` | required | Character position index |
| `char` | `str` | required | Character to check |

**Returns:** `None`

> ⚠️ **Note:** If a position was already decided with a different character, it will be overridden. This handles cases where early votes favored one character but later evidence points to another.

---

##### `check_full_consensus()`

> Check if full consensus has been reached.

**Parameters:** None

**Returns:** `bool` — `True` only if all expected positions are decided.

Expected positions are inferred by `_get_expected_positions()`:
- Prefer the most common observed OCR length in `length_counter`
: `length_counter` is updated before mismatch rejection, so it may include lengths later skipped from position voting.
- Fallback to `max(counter.keys()) + 1` when no length history exists

Counting logic uses only the expected range (`0..expected_positions-1`) to avoid out-of-range decided positions causing false positives.

State consistency rule:
- `check_full_consensus()` also keeps `self.consensus_reached` synchronized with the current evaluation result. If consensus is not met, the flag is explicitly kept `False` (useful when internal state was mutated without `reset()`).

**Example**
```python
# With expected_positions = 6
# Need all 6 positions decided
ca.check_full_consensus()  # True only when 6/6 are decided
```

---

##### `build_final_text()`

> Build the final consensus text from decided characters.

**Parameters:** None

**Returns:** `str`
- Returns `""` if no positions are decided.
- If expected length is known, returns `""` until **every** expected position is decided.
- When complete, returns characters in expected position order.
- If expected length cannot be inferred, falls back to concatenating decided positions sorted by index.

**Example**
```python
# decided_chars = {0: 'A', 1: 'B', 2: '1', 3: '2', 4: 'C', 5: 'D'}
ca.build_final_text()  # → "AB12CD"
```

---

##### `compute_consensus_confidence()`

> Compute a composite confidence score for the consensus result, combining position dominance with average OCR confidence.

**Parameters:** None

**Returns:** `float` — Confidence score between 0.0 and 1.0, computed as:

```
confidence = mean(position_dominances) × mean(accepted_ocr_confidences)
```

Where `position_dominance(pos) = winner_votes / total_votes` for each decided position.

**Returns `0.0`** if no positions are decided or no readings were accepted.

**Example — Plate `AC124D`, 15 frames, noisy OCR**

The character `1` is often confused with `I`/`L`, the `2` with `Z`, the `4` with `A`, and the `D` with `0`:

| Frame | OCR Text | Conf. | Accepted? | Weight | Errors |
|:-----:|----------|:-----:|:---------:|:------:|--------|
| 1 | `AC124D` | 0.91 | ✅ | 1 | — |
| 2 | `ACI2AD` | 0.87 | ✅ | 1 | pos2=I, pos4=A |
| 3 | `ACL24D` | 0.84 | ✅ | 1 | pos2=L |
| 4 | `AC124D` | 0.96 | ✅ | **2** | — |
| 5 | `ACI240` | 0.88 | ✅ | 1 | pos2=I, pos5=0 |
| 6 | `AC1Z4D` | 0.92 | ✅ | 1 | pos3=Z |
| 7 | `AC12AD` | 0.85 | ✅ | 1 | pos4=A |
| 8 | *(empty)* | 0.30 | ❌ | — | conf < 0.80 |
| 9 | `AC1` | 0.89 | ❌ | — | len < 4 |
| 10 | `AC124D` | 0.95 | ✅ | **2** | — |
| 11 | `ACI24D` | 0.90 | ✅ | 1 | pos2=I |
| 12 | `AC124DA` | 0.88 | ❌ | — | len=7 ≠ 6 (outlier) |
| 13 | `ACL240` | 0.86 | ✅ | 1 | pos2=L, pos5=0 |
| 14 | `AC124D` | 0.97 | ✅ | **2** | — |
| 15 | `AC1Z4D` | 0.83 | ✅ | 1 | pos3=Z |

**12 readings accepted, 3 filtered.** Final voting matrix:

| Position | Votes | Winner | Total | Dominance |
|:--------:|-------|:------:|:-----:|:---------:|
| 0 | A:**15** | A | 15 | 15/15 = **1.000** |
| 1 | C:**15** | C | 15 | 15/15 = **1.000** |
| 2 | 1:**10**, I:3, L:2 | 1 | 15 | 10/15 = **0.667** |
| 3 | 2:**13**, Z:2 | 2 | 15 | 13/15 = **0.867** |
| 4 | 4:**13**, A:2 | 4 | 15 | 13/15 = **0.867** |
| 5 | D:**13**, 0:2 | D | 15 | 13/15 = **0.867** |

> **Why is the total 15 and not 12?** The 3 filtered frames (8, 9, 12) don't count at all — zero votes, zero confidence contribution. Of the 12 accepted frames, 3 have confidence ≥ 0.95 (frames 4, 10, 14) and receive **2 votes each** instead of 1 (`_get_vote_weight()`). So: `9 × 1 + 3 × 2 = 15` weighted votes per position.

```python
# agreement_score = mean([1.000, 1.000, 0.667, 0.867, 0.867, 0.867]) = 0.878
# avg_ocr_confidence = mean([0.91, 0.87, 0.84, 0.96, 0.88, 0.92,
#                            0.85, 0.95, 0.90, 0.86, 0.97, 0.83]) = 0.895
# confidence = 0.878 × 0.895 = 0.786 (≈ 79%)
conf = ca.compute_consensus_confidence()
```
Position 2 (`1` misread as `I`/`L`) pulls the agreement down, and the final
confidence (≈ 79%) accurately reflects the difficulty of reading that character.

> ⚠️ **Note:** The multiplicative formula means both high agreement AND high OCR confidence are needed for a high score. If the OCR consistently reads the same wrong text (high agreement, moderate OCR confidence), the score will reflect the OCR uncertainty.

---

##### `select_best_crop(final_text)`

> Select the candidate crop whose OCR text is most similar to the final consensus text.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `final_text` | `str` | required | The consensus text to match against |

**Returns:** `Any | None` — The best crop image, or `None` if no candidates exist.

**Selection logic:**
1. If `final_text` is empty → return crop with highest confidence **and update** `self.best_crop` / `self.best_confidence`.
2. Otherwise → compute Levenshtein similarity (`1 - distance/max_len`) for each candidate.
3. Sort by similarity (desc), then confidence (desc) as tiebreaker.
4. Return the top-ranked crop.

**Example**
```python
# Candidates: [{"text": "AB12CD", "confidence": 0.9}, {"text": "AB1ZCD", "confidence": 0.85}]
best = ca.select_best_crop("AB12CD")
# → returns crop with text "AB12CD" (similarity=1.0)
```

---

##### `get_best_partial_result(object_type)`

> Return the best available result when full consensus was NOT reached.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `object_type` | `str` | required | Type label for logging (e.g. `"license plate"`, `"hazard plate"`) |

**Returns:** `tuple[str | None, float | None, Any | None]` — `(text, confidence, crop)`:

| Scenario | text | confidence | crop |
|----------|------|------------|------|
| Partial consensus data exists | Partial text (undecided positions filled with best guess or `_`) | Blended score: `((decided_count/total_positions) + (agreement_score × avg_ocr_confidence)) / 2`, capped at `0.95` (falls back to completeness-only when OCR confidence history is empty) | Best matching crop |
| No text consensus, but crops exist | `"N/A"` | Highest-candidate confidence reused from `select_best_crop("")` state update | Highest confidence crop |
| No crops at all | `None` | `None` | `None` |

`total_positions` is derived from `_get_expected_positions()`; if unavailable, it falls back to `max(counter.keys()) + 1`.

**Example**
```python
text, conf, crop = ca.get_best_partial_result("license plate")
# text → "AB_2CD" (position 2 undecided, filled with best guess)
# conf → blended partial confidence (<= 0.95)
# crop → best matching crop image
```

**Partial confidence details**

For partial results:

```python
completeness = decided_count / total_positions
quality = agreement_score * average_ocr_confidence
partial_confidence = min((completeness + quality) / 2, 0.95)
```

If there are no accepted OCR confidences yet, the algorithm uses only:

```python
partial_confidence = min(completeness, 0.95)
```

---

##### Internal Helper Methods

These helper methods are internal (`_`-prefixed) and are used by the public API above:

| Method | Purpose |
|--------|---------|
| `_normalize_text(text)` | Normalizes OCR text before voting (uppercase, removes dashes). |
| `_is_valid_for_consensus(text_normalized, confidence)` | Applies basic validation gates (`MIN_CONFIDENCE_CONSENSUS`, `MIN_TEXT_LENGTH`). |
| `_track_text_length(text_len)` | Tracks observed text lengths and rejects outliers once length consensus stabilizes (after at least 3 observed readings). |
| `_get_vote_weight(confidence)` | Returns vote weight per reading (`2` if confidence >= `0.95`, otherwise `1`). |
| `_get_expected_positions()` | Determines expected text length for full-consensus and text building logic (prefers most common observed length in `length_counter`). |
| `_get_most_common_length()` | Returns the most frequent observed text length; ties prefer shorter length to reduce outlier impact. |
| `_average_ocr_confidence()` | Returns the arithmetic mean of accepted OCR confidence values (or `0.0` if none). |
| `_compute_agreement_score(positions, use_decided_chars)` | Computes average per-position dominance (`winner_votes/total_votes`) for a target set of positions. |
| `_compute_partial_confidence(total_positions, decided_count)` | Computes bounded partial confidence by blending completeness and quality signal. |

---

## Standalone Functions

> N/A

---

## Configuration & Environment Variables

> N/A — All configuration is through module-level constants (`DECISION_THRESHOLD`, `MIN_TEXT_LENGTH`, `MIN_CONFIDENCE_CONSENSUS`).

---

## Usage Example

Typical usage within `base_agent.py` during a detection cycle:

```python
from AI_APP.shared.src.consensus_algorithm import ConsensusAlgorithm

ca = ConsensusAlgorithm()

# During frame processing loop:
for frame in frames:
    crop = detect_plate(frame)          # YOLO detection
    text, confidence = ocr.extract_text(crop)  # PaddleOCR

    ca.add_candidate_crop(crop, text, confidence)
    ca.add_to_consensus(text, confidence)

    if ca.check_full_consensus():
        break  # Early exit

# After loop:
if ca.consensus_reached:
    final_text = ca.build_final_text()
    confidence = ca.compute_consensus_confidence()
    best_crop = ca.select_best_crop(final_text)
else:
    final_text, confidence, best_crop = ca.get_best_partial_result("license plate")

# Reset for next detection cycle
ca.reset()
```

---

## Error Handling

The `ConsensusAlgorithm` class does not raise exceptions to callers. Its strategy is defensive:

- **Invalid OCR readings** (low confidence, short text, length mismatch) are silently skipped with debug logging.
- **No candidates available** in `select_best_crop()` → returns `None` with a warning log.
- **No consensus data** in `get_best_partial_result()` → returns `(None, None, None)` or `("N/A", confidence, crop)` depending on crop availability.
- **Empty voting matrix** in `check_full_consensus()` → returns `False`.

Logging uses the `"ConsensusAlgorithm"` logger name.

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| `consensus_algorithm_unit_test.py` | Unit | Initialization, reset, voting mechanics, consensus checking, text building, crop selection, partial results, length tracking, confidence weighting, helper-method calculations, and noisy real-world OCR scenarios |

To run:
```bash
pytest src/AI_APP/shared/tests/consensus_algorithm_unit_test.py
```

---

## Known Issues / TODOs

- [ ] `DECISION_THRESHOLD`, `MIN_TEXT_LENGTH`, and `MIN_CONFIDENCE_CONSENSUS` are module-level globals — consider making them configurable via constructor parameters or environment variables for different use cases (e.g., highway camera vs. gate camera may need different thresholds).
- [ ] The length tracking rejects outliers after 3 samples, which may discard valid readings if the first few frames had OCR errors that set a wrong "most common length".

---

## Changelog

| Version / Date | Change |
|----------------|--------|
| `2026-04-17` | Hardened `check_full_consensus()` state consistency: method now explicitly clears stale `consensus_reached=True` when current state does not satisfy full consensus. |
| `2026-04-17` | Refactored partial-confidence logic with internal helper methods (`_average_ocr_confidence`, `_compute_agreement_score`, `_compute_partial_confidence`). Updated partial fallback documentation with blended confidence formula and documented noisy real-world test scenarios. |
| `2026-04-17` | Synchronized fallback crop state: `select_best_crop("")` now updates both `best_crop` and `best_confidence`; `get_best_partial_result()` reuses that state to avoid duplicate candidate scans. |
| `2026-04-15` | Updated full-consensus semantics: now requires 100% of expected positions (inferred from most common observed text length). Removed percentage-threshold documentation and `math.ceil()` references. Clarified `build_final_text()` and partial fallback behavior. |
| `2025-02-22` | Added `compute_consensus_confidence()` method and `accepted_confidences` tracking. Replaced hardcoded `1.0` confidence in `base_agent.py` with composite score based on position dominance × average OCR confidence. |

---

## Related Docs

- [`base_agent.md`](./base_agent.md) — Primary consumer of this module
- [`paddle_ocr.md`](./paddle_ocr.md) — OCR engine that produces the readings fed into consensus
- [`object_detector.md`](./object_detector.md) — YOLO detection that produces crops
- [`image_storage.md`](./image_storage.md) — Storage for the selected best crop
