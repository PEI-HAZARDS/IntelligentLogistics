"""
Unit tests for PlateMatcher class.
Tests for license plate matching using OCR confusion matrix and Levenshtein distance.
"""
import pytest
from unittest.mock import patch, MagicMock

from plate_matcher import PlateMatcher, PlateMatcherMode


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def hybrid_matcher():
    """Create a PlateMatcher in hybrid mode."""
    return PlateMatcher(mode=PlateMatcherMode.HYBRID, max_distance=2)


@pytest.fixture
def levenshtein_matcher():
    """Create a PlateMatcher in Levenshtein-only mode."""
    return PlateMatcher(mode=PlateMatcherMode.LEVENSHTEIN, max_distance=2)


@pytest.fixture
def confusion_matrix_matcher():
    """Create a PlateMatcher in confusion matrix-only mode."""
    return PlateMatcher(mode=PlateMatcherMode.CONFUSION_MATRIX, max_distance=2)


@pytest.fixture
def sample_db_plates():
    """Sample database plates for testing."""
    return ["AB-12-CD", "XY-34-ZW", "AA-11-BB", "12-AB-34"]


# =============================================================================
# Tests for __init__
# =============================================================================

class TestPlateMatcherInit:
    """Tests for PlateMatcher initialization."""

    def test_init_default_mode(self):
        """Default mode is HYBRID."""
        matcher = PlateMatcher()
        assert matcher.mode == PlateMatcherMode.HYBRID

    def test_init_default_max_distance(self):
        """Default max distance is 2."""
        matcher = PlateMatcher()
        assert matcher.max_distance == 2

    def test_init_custom_mode(self):
        """Custom mode is respected."""
        matcher = PlateMatcher(mode=PlateMatcherMode.LEVENSHTEIN)
        assert matcher.mode == PlateMatcherMode.LEVENSHTEIN

    def test_init_custom_max_distance(self):
        """Custom max distance is respected."""
        matcher = PlateMatcher(max_distance=3)
        assert matcher.max_distance == 3

    def test_init_creates_confusion_matrix(self, hybrid_matcher):
        """Confusion matrix is created with expected entries."""
        assert '0' in hybrid_matcher.confusion_matrix
        assert 'O' in hybrid_matcher.confusion_matrix['0']
        assert '8' in hybrid_matcher.confusion_matrix
        assert 'B' in hybrid_matcher.confusion_matrix['8']


# =============================================================================
# Tests for match_plate
# =============================================================================

class TestMatchPlate:
    """Tests for match_plate method."""

    def test_exact_match(self, hybrid_matcher, sample_db_plates):
        """Exact match returns correct plate."""
        result = hybrid_matcher.match_plate("AB-12-CD", sample_db_plates)
        assert result == "AB-12-CD"

    def test_exact_match_ignore_case(self, hybrid_matcher, sample_db_plates):
        """Exact match ignores case."""
        result = hybrid_matcher.match_plate("ab-12-cd", sample_db_plates)
        assert result == "AB-12-CD"

    def test_exact_match_ignore_spaces(self, hybrid_matcher, sample_db_plates):
        """Exact match ignores spaces and dashes."""
        result = hybrid_matcher.match_plate("AB12CD", sample_db_plates)
        assert result == "AB-12-CD"

    def test_empty_db_plates_returns_none(self, hybrid_matcher):
        """Empty database plates returns None."""
        result = hybrid_matcher.match_plate("AB-12-CD", [])
        assert result is None

    def test_no_match_returns_none(self, hybrid_matcher, sample_db_plates):
        """No match returns None."""
        result = hybrid_matcher.match_plate("ZZ-99-ZZ", sample_db_plates)
        assert result is None

    def test_confusion_matrix_mode(self, confusion_matrix_matcher, sample_db_plates):
        """Confusion matrix mode handles OCR errors."""
        # '0' is confused with 'O', so "A0-12-CD" should match "AB-12-CD"
        # Actually test realistic confusion: 'O' confused with '0'
        db_plates = ["AB-00-CD"]
        result = confusion_matrix_matcher.match_plate("AB-OO-CD", db_plates)
        assert result == "AB-00-CD"

    def test_levenshtein_mode(self, levenshtein_matcher, sample_db_plates):
        """Levenshtein mode handles small differences."""
        # One character different
        result = levenshtein_matcher.match_plate("AB-12-CE", sample_db_plates)
        assert result == "AB-12-CD"

    def test_hybrid_mode_uses_confusion_first(self, hybrid_matcher):
        """Hybrid mode tries confusion matrix first."""
        db_plates = ["AB-00-CD"]
        result = hybrid_matcher.match_plate("AB-OO-CD", db_plates)
        assert result == "AB-00-CD"


# =============================================================================
# Tests for _generate_plate_candidates
# =============================================================================

class TestGeneratePlateCandidates:
    """Tests for _generate_plate_candidates method."""

    def test_generates_candidates(self, hybrid_matcher):
        """Generates candidates for OCR text."""
        candidates = hybrid_matcher._generate_plate_candidates("AB")
        assert "AB" in candidates
        assert "4B" in candidates  # A -> 4
        assert "A8" in candidates  # B -> 8

    def test_includes_original_text(self, hybrid_matcher):
        """Original text is always included."""
        candidates = hybrid_matcher._generate_plate_candidates("XY")
        assert "XY" in candidates

    def test_respects_max_substitutions(self, hybrid_matcher):
        """Max substitutions limits candidates."""
        candidates_unlimited = hybrid_matcher._generate_plate_candidates("AB", max_substitutions=0)
        candidates_limited = hybrid_matcher._generate_plate_candidates("AB", max_substitutions=1)
        # Limited should have fewer candidates
        assert len(candidates_limited) <= len(candidates_unlimited)

    def test_handles_characters_without_confusion(self, hybrid_matcher):
        """Handles characters not in confusion matrix."""
        candidates = hybrid_matcher._generate_plate_candidates("!")
        assert "!" in candidates
        assert len(candidates) == 1


# =============================================================================
# Tests for _match_with_confusion_matrix
# =============================================================================

class TestMatchWithConfusionMatrix:
    """Tests for _match_with_confusion_matrix method."""

    def test_finds_match_with_confusion(self, hybrid_matcher):
        """Finds match when confusion substitution needed."""
        db_plates = ["AB00CD"]
        result = hybrid_matcher._match_with_confusion_matrix("ABOOCD", db_plates, ["AB00CD"])
        assert result == "AB00CD"

    def test_returns_none_when_no_match(self, hybrid_matcher):
        """Returns None when no match found."""
        db_plates = ["XYZABC"]
        result = hybrid_matcher._match_with_confusion_matrix("ZZZZZ", db_plates, ["XYZABC"])
        assert result is None


# =============================================================================
# Tests for _match_with_levenshtein
# =============================================================================

class TestMatchWithLevenshtein:
    """Tests for _match_with_levenshtein method."""

    def test_finds_match_within_distance(self, hybrid_matcher):
        """Finds match within max distance."""
        db_plates = ["ABCDEF"]
        result = hybrid_matcher._match_with_levenshtein("ABCDEG", db_plates, ["ABCDEF"])
        assert result == "ABCDEF"

    def test_returns_none_when_too_far(self, hybrid_matcher):
        """Returns None when distance exceeds max."""
        db_plates = ["ABCDEF"]
        result = hybrid_matcher._match_with_levenshtein("XXXXXX", db_plates, ["ABCDEF"])
        assert result is None

    def test_returns_best_match(self, hybrid_matcher):
        """Returns the best (closest) match."""
        db_plates = ["ABCDEF", "ABCDXX"]
        result = hybrid_matcher._match_with_levenshtein("ABCDEG", db_plates, ["ABCDEF", "ABCDXX"])
        assert result == "ABCDEF"  # Distance 1 vs 2


# =============================================================================
# Tests for _match_with_hybrid
# =============================================================================

class TestMatchWithHybrid:
    """Tests for _match_with_hybrid method."""

    def test_uses_confusion_matrix_first(self, hybrid_matcher):
        """Uses confusion matrix first."""
        db_plates = ["AB00CD"]
        # O->0 confusion should be found by confusion matrix
        result = hybrid_matcher._match_with_hybrid("ABOOCD", db_plates, ["AB00CD"])
        assert result == "AB00CD"

    def test_falls_back_to_levenshtein(self, hybrid_matcher):
        """Falls back to Levenshtein when confusion matrix fails."""
        db_plates = ["ABCDEF"]
        # No confusion match, but within Levenshtein distance
        result = hybrid_matcher._match_with_hybrid("ABCDEG", db_plates, ["ABCDEF"])
        assert result == "ABCDEF"

    def test_returns_none_when_both_fail(self, hybrid_matcher):
        """Returns None when both methods fail."""
        db_plates = ["ABCDEF"]
        result = hybrid_matcher._match_with_hybrid("XXXXXX", db_plates, ["ABCDEF"])
        assert result is None
