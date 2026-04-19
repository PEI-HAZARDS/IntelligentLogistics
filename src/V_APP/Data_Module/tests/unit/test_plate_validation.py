"""
Unit tests for Portuguese truck license-plate format validation (BR-49).

BR-49 — License plates must match the format AA-00-BB
        (two uppercase letters, two digits, two uppercase letters).

Audit finding: NO plate validator exists in this codebase.
`license_plate` is declared as a plain `str` in `application/schemas.py`
with no regex constraint, so invalid plates are accepted silently.

This file:
  - Documents the expected validator contract (accept/reject cases).
  - Marks the existence test as xfail to signal the missing implementation.
  - Provides the canonical test suite that must pass once a validator is added.

The expected validator location is `utils/plate_validation.py`, exporting:
    def validate_plate(plate: str) -> str:
        '''Return the plate uppercased if valid, raise ValueError otherwise.'''

Run:
    PYTHONPATH=. pytest tests/unit/test_plate_validation.py -v
"""

import pytest

# ---------------------------------------------------------------------------
# Validator import (will fail until the module is created — expected)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def validate_plate():
    """
    Import validate_plate from utils.plate_validation.
    If the module does not exist this fixture raises ImportError,
    which causes all tests that depend on it to be skipped with
    an explanatory message rather than failing with a confusing traceback.
    """
    try:
        from utils.plate_validation import validate_plate as _fn
        return _fn
    except ImportError:
        pytest.skip(
            "utils/plate_validation.py does not exist — BR-49 validator not implemented. "
            "Create the module with validate_plate(plate: str) -> str before enabling these tests."
        )


# ---------------------------------------------------------------------------
# 1. Gap documentation — no validator module exists today
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    reason=(
        "BR-49 gap: no plate validator exists. "
        "utils/plate_validation.py and validate_plate() are absent. "
        "schemas.py accepts any string for license_plate with no format check. "
        "Fix: add utils/plate_validation.py with a regex for AA-00-BB format "
        "and wire it into TruckCreate/Truck Pydantic schemas as a field_validator."
    ),
    strict=True,
)
def test_plate_validator_module_exists():
    """
    The plate validator module must exist in utils/plate_validation.py.
    This xfail test tracks the missing implementation.
    When the module is added, remove this xfail marker.
    """
    from utils import plate_validation  # noqa: F401  — import existence check
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
