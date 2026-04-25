"""
Unit tests for Portuguese truck license-plate format validation (BR-49).

BR-49 — License plates must match the format AA-00-BB
        (two uppercase letters, two digits, two uppercase letters).

utils/plate_validation.py implements:
    is_valid_plate(plate) -> bool       — strict format check
    validate_plate(plate) -> str        — raises ValueError on invalid, returns uppercase
    is_valid_plate_relaxed(plate) -> bool — OCR-tolerant (strips hyphens/spaces)
    normalise_plate(plate) -> str       — canonical DB form

Run:
    PYTHONPATH=. pytest tests/unit/test_plate_validation.py -v
"""

import pytest

# ---------------------------------------------------------------------------
# Validator import
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def validate_plate():
    """Import validate_plate from utils.plate_validation."""
    from utils.plate_validation import validate_plate as _fn
    return _fn


# ---------------------------------------------------------------------------
# 1. Module existence
# ---------------------------------------------------------------------------

def test_plate_validator_module_exists():
    """utils/plate_validation.py must expose a validate_plate() function (BR-49)."""
    from utils import plate_validation  # noqa: F401
    assert hasattr(plate_validation, "validate_plate"), (
        "utils/plate_validation must expose a validate_plate() function"
    )


# ---------------------------------------------------------------------------
# 2. Valid plate acceptance
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("plate", [
    "AB-12-CD",
    "ZZ-99-AA",
    "PQ-00-XY",
    "AA-00-BB",   # canonical BR-49 example
])
def test_valid_plates_accepted(validate_plate, plate):
    """Valid AA-00-BB plates must be accepted and returned (uppercased)."""
    result = validate_plate(plate)
    assert result == plate.upper()


def test_validator_normalises_lowercase(validate_plate):
    """Lowercase input that matches the pattern must be normalised to uppercase."""
    result = validate_plate("ab-12-cd")
    assert result == "AB-12-CD"


# ---------------------------------------------------------------------------
# 3. Invalid plate rejection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_plate", [
    "AB12CD",        # missing dashes
    "A1-12-CD",      # first group has digit
    "AB-1A-CD",      # middle group has letter
    "AB-12-C3",      # last group has digit
    "ABC-12-CD",     # first group too long
    "AB-123-CD",     # middle group too long
    "AB-12-CDE",     # last group too long
    "",              # empty
    "   ",           # whitespace only
    "AB-12",         # too short
    "AB-12-CD-EF",   # too long
    "12-AB-CD",      # wrong group order
])
def test_invalid_plates_rejected(validate_plate, bad_plate):
    """Plates that do not match AA-00-BB must raise ValueError."""
    with pytest.raises(ValueError):
        validate_plate(bad_plate)
