"""
License-plate format validation and detection consensus checks for the Data Module.

Primary format (PT current): XX-99-XX  (^[A-Z]{2}-\\d{2}-[A-Z]{2}$)
Relaxed validation also accepts other PT series and strips hyphens/spaces
for OCR-normalised inputs from the AI pipeline.
"""

import re

# Standard PT current-series plate: two letters, two digits, two letters
_STRICT_RE = re.compile(r'^[A-Z]{2}-\d{2}-[A-Z]{2}$', re.IGNORECASE)

# Relaxed: also accepts older PT series and hyphen-free OCR output (≥4 chars, alphanumeric)
_RELAXED_RE = re.compile(r'^[A-Z0-9]{4,10}$', re.IGNORECASE)


def is_valid_plate(plate: str) -> bool:
    """Return True if *plate* matches the current PT plate format XX-99-XX."""
    return bool(_STRICT_RE.match(plate.strip())) if plate else False


def is_valid_plate_relaxed(plate: str) -> bool:
    """Return True if *plate* is a plausible plate string (4-10 alphanumeric chars).

    Used for OCR-normalised inputs from the AI pipeline where hyphens are
    stripped and international formats are accepted.
    """
    if not plate:
        return False
    normalised = plate.strip().replace("-", "").replace(" ", "")
    return bool(_RELAXED_RE.match(normalised))


def normalise_plate(plate: str) -> str:
    """Strip hyphens/spaces and uppercase — canonical form for DB lookups."""
    return plate.strip().replace("-", "").replace(" ", "").upper()


def validate_plate(plate: str) -> str:
    """Raise ValueError if *plate* does not match XX-99-XX; return uppercased plate."""
    if not plate or not _STRICT_RE.match(plate.strip()):
        raise ValueError(f"Invalid license plate format: {plate!r} (expected XX-99-XX)")
    return plate.strip().upper()


# ---------------------------------------------------------------------------
# Detection consensus validation
# ---------------------------------------------------------------------------

import logging as _logging
_logger = _logging.getLogger(__name__)


def validate_consensus(detection: dict, threshold: float = 0.7) -> bool:
    """Return True if *detection* passes consensus validation.

    Rejects if:
    - ``confidence`` is present and below *threshold*
    - ``origem`` (source identifier) is absent or empty
    """
    confidence = detection.get("confidence")
    if confidence is not None and float(confidence) < threshold:
        _logger.warning(
            "validate_consensus: confidence %.3f below threshold %.2f — rejected",
            confidence, threshold,
        )
        return False
    if not detection.get("origem"):
        _logger.warning("validate_consensus: missing 'origem' field — rejected")
        return False
    return True
