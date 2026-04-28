"""
Phase 13 unit tests — Validators (plate_validation + consensus).

test_plate_validation.py scope:
- is_valid_plate: strict PT format XX-99-XX
- is_valid_plate_relaxed: OCR-normalised inputs accepted
- normalise_plate: canonical form

test_consensus_validation.py scope:
- validate_consensus: threshold rejection, missing origem
"""
import pytest

# ---------------------------------------------------------------------------
# Plate validation — live import (no infra deps)
# ---------------------------------------------------------------------------

from utils.plate_validation import is_valid_plate, is_valid_plate_relaxed, normalise_plate


class TestIsValidPlateStrict:

    def test_valid_pt_format(self):
        assert is_valid_plate("AB-12-CD")

    def test_valid_lowercase_accepted(self):
        assert is_valid_plate("ab-12-cd")

    def test_rejects_digits_only(self):
        assert not is_valid_plate("12-34-56")

    def test_rejects_letters_only(self):
        assert not is_valid_plate("AB-CD-EF")

    def test_rejects_no_hyphens(self):
        assert not is_valid_plate("AB12CD")

    def test_rejects_too_short(self):
        assert not is_valid_plate("AB-1-C")

    def test_rejects_empty(self):
        assert not is_valid_plate("")

    def test_rejects_none_like_empty(self):
        assert not is_valid_plate("")


class TestIsValidPlateRelaxed:

    def test_accepts_no_hyphens_ocr(self):
        assert is_valid_plate_relaxed("AB12CD")

    def test_accepts_digits_and_letters(self):
        assert is_valid_plate_relaxed("87AX60")

    def test_accepts_standard_pt_format(self):
        assert is_valid_plate_relaxed("AB-12-CD")

    def test_rejects_too_short(self):
        assert not is_valid_plate_relaxed("AB")

    def test_rejects_empty(self):
        assert not is_valid_plate_relaxed("")

    def test_rejects_special_chars(self):
        assert not is_valid_plate_relaxed("AB!12#CD")

    def test_accepts_up_to_ten_chars(self):
        assert is_valid_plate_relaxed("AB1234CDEF")

    def test_rejects_over_ten_chars(self):
        assert not is_valid_plate_relaxed("AB1234CDEFG")


class TestNormalisePlate:

    def test_strips_hyphens(self):
        assert normalise_plate("AB-12-CD") == "AB12CD"

    def test_strips_spaces(self):
        assert normalise_plate("AB 12 CD") == "AB12CD"

    def test_uppercases(self):
        assert normalise_plate("ab-12-cd") == "AB12CD"

    def test_strips_leading_trailing(self):
        assert normalise_plate("  AB-12-CD  ") == "AB12CD"


# ---------------------------------------------------------------------------
# Structural: plate validator wired into routes and mongo.py
# ---------------------------------------------------------------------------

import pathlib
_BASE = pathlib.Path(__file__).parents[2]


def _src(rel: str) -> str:
    return (_BASE / rel).read_text()


class TestPlateValidatorWiredIn:

    def test_plate_validation_module_exists(self):
        assert (_BASE / "utils" / "plate_validation.py").exists()

    def test_decisions_route_imports_validator(self):
        src = _src("routes/decisions.py")
        assert "plate_validation" in src or "is_valid_plate" in src

    def test_decisions_route_has_field_validator(self):
        src = _src("routes/decisions.py")
        assert "field_validator" in src or "validator" in src

    def test_arrivals_route_validates_plate(self):
        src = _src("routes/arrivals.py")
        assert "is_valid_plate_relaxed" in src or "plate_validation" in src

    def test_mongo_validate_agent_detection_uses_validator(self):
        src = _src("infrastructure/persistence/mongo.py")
        assert "plate_validation" in src or "is_valid_plate_relaxed" in src


# ---------------------------------------------------------------------------
# Consensus validation — live tests
# ---------------------------------------------------------------------------

from utils.plate_validation import validate_consensus


class TestValidateConsensus:

    def test_accepts_above_threshold_with_origem(self):
        assert validate_consensus({"confidence": 0.9, "origem": "AgentB"})

    def test_accepts_exactly_at_threshold(self):
        assert validate_consensus({"confidence": 0.7, "origem": "AgentB"})

    def test_rejects_below_threshold(self):
        assert not validate_consensus({"confidence": 0.5, "origem": "AgentB"})

    def test_rejects_zero_confidence(self):
        assert not validate_consensus({"confidence": 0.0, "origem": "AgentB"})

    def test_rejects_missing_origem(self):
        assert not validate_consensus({"confidence": 0.9})

    def test_rejects_empty_origem(self):
        assert not validate_consensus({"confidence": 0.9, "origem": ""})

    def test_accepts_no_confidence_field(self):
        # No confidence field = not rejected by threshold (only origem matters)
        assert validate_consensus({"origem": "AgentB"})

    def test_custom_threshold(self):
        assert not validate_consensus({"confidence": 0.8, "origem": "AgentB"}, threshold=0.9)
        assert validate_consensus({"confidence": 0.8, "origem": "AgentB"}, threshold=0.6)

    def test_validate_consensus_defined_in_plate_validation(self):
        src = _src("utils/plate_validation.py")
        assert "def validate_consensus(" in src

    def test_decision_queries_delegates_to_utils(self):
        src = _src("application/queries/decision_queries.py")
        assert "def validate_consensus(" in src
        assert "utils.plate_validation" in src or "plate_validation import" in src

    def test_default_threshold_is_0_7(self):
        src = _src("utils/plate_validation.py")
        fn_start = src.index("def validate_consensus(")
        fn_sig = src[fn_start:fn_start + 80]
        assert "0.7" in fn_sig

    def test_rejects_missing_origem_documented(self):
        src = _src("utils/plate_validation.py")
        fn_start = src.index("def validate_consensus(")
        try:
            fn_end = src.index("\ndef ", fn_start + 1)
        except ValueError:
            fn_end = len(src)
        fn_body = src[fn_start:fn_end]
        assert "origem" in fn_body
