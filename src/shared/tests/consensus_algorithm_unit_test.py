"""
Unit tests for shared/src/consensus_algorithm.py

Tests cover:
- ConsensusAlgorithm state management (reset)
- Candidate crop management
- Consensus voting mechanism
- Full consensus checking
- Final text building
- Best crop selection
- Partial result handling
"""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from consensus_algorithm import (
    ConsensusAlgorithm,
    CONSENSUS_PERCENTAGE,
    DECISION_THRESHOLD,
    MIN_TEXT_LENGTH,
    MIN_CONFIDENCE_CONSENSUS,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def algorithm():
    """Create a fresh ConsensusAlgorithm instance for each test."""
    return ConsensusAlgorithm()


@pytest.fixture
def sample_crop():
    """Create a sample image crop (numpy array)."""
    return np.zeros((50, 100, 3), dtype=np.uint8)


# =============================================================================
# Tests for __init__ and reset
# =============================================================================

class TestConsensusAlgorithmInit:
    """Tests for initialization and reset."""

    def test_initial_state(self, algorithm):
        """Verify initial state of new algorithm."""
        # Assert
        assert algorithm.consensus_reached is False
        assert algorithm.counter == {}
        assert algorithm.decided_chars == {}
        assert algorithm.frames_processed == 0
        assert algorithm.length_counter == {}
        assert algorithm.best_crop is None
        assert algorithm.best_confidence == 0.0
        assert algorithm.candidate_crops == []

    def test_reset_clears_all_state(self, algorithm, sample_crop):
        """Reset should clear all accumulated state."""
        # Arrange - add some state
        algorithm.consensus_reached = True
        algorithm.counter = {0: {'A': 5}}
        algorithm.decided_chars = {0: 'A'}
        algorithm.frames_processed = 10
        algorithm.length_counter = {6: 5}
        algorithm.best_crop = sample_crop
        algorithm.best_confidence = 0.95
        algorithm.candidate_crops = [{"crop": sample_crop, "text": "TEST", "confidence": 0.9}]

        # Act
        algorithm.reset()

        # Assert
        assert algorithm.consensus_reached is False
        assert algorithm.counter == {}
        assert algorithm.decided_chars == {}
        assert algorithm.frames_processed == 0
        assert algorithm.length_counter == {}
        assert algorithm.best_crop is None
        assert algorithm.best_confidence == 0.0
        assert algorithm.candidate_crops == []


# =============================================================================
# Tests for add_candidate_crop
# =============================================================================

class TestAddCandidateCrop:
    """Tests for adding candidate crops."""

    def test_add_new_candidate_with_text(self, algorithm, sample_crop):
        """Add a new candidate crop with OCR text."""
        # Act
        algorithm.add_candidate_crop(sample_crop, "ABC123", 0.95, is_fallback=False)

        # Assert
        assert len(algorithm.candidate_crops) == 1
        assert algorithm.candidate_crops[0]["text"] == "ABC123"
        assert algorithm.candidate_crops[0]["confidence"] == 0.95
        assert algorithm.candidate_crops[0]["is_fallback"] is False

    def test_add_fallback_candidate_without_text(self, algorithm, sample_crop):
        """Add a fallback candidate with no OCR text."""
        # Act
        algorithm.add_candidate_crop(sample_crop, "", 0.8, is_fallback=True)

        # Assert
        assert len(algorithm.candidate_crops) == 1
        assert algorithm.candidate_crops[0]["text"] == ""
        assert algorithm.candidate_crops[0]["is_fallback"] is True

    def test_replace_existing_candidate_with_same_text(self, algorithm, sample_crop):
        """Replace existing candidate when text matches."""
        # Arrange
        crop1 = np.ones((50, 100, 3), dtype=np.uint8)
        crop2 = np.ones((50, 100, 3), dtype=np.uint8) * 2
        
        algorithm.add_candidate_crop(crop1, "ABC123", 0.8, is_fallback=False)

        # Act - add second with same text but higher confidence
        algorithm.add_candidate_crop(crop2, "ABC123", 0.95, is_fallback=False)

        # Assert - should replace, not add
        assert len(algorithm.candidate_crops) == 1
        assert algorithm.candidate_crops[0]["confidence"] == 0.95

    def test_replace_fallback_with_higher_confidence(self, algorithm, sample_crop):
        """Replace fallback candidate when new one has higher confidence."""
        # Arrange
        crop1 = np.zeros((50, 100, 3), dtype=np.uint8)
        crop2 = np.ones((50, 100, 3), dtype=np.uint8)
        
        algorithm.add_candidate_crop(crop1, "", 0.7, is_fallback=True)

        # Act - add higher confidence fallback
        algorithm.add_candidate_crop(crop2, "", 0.9, is_fallback=True)

        # Assert
        assert len(algorithm.candidate_crops) == 1
        assert algorithm.candidate_crops[0]["confidence"] == 0.9

    def test_keep_fallback_with_lower_confidence(self, algorithm, sample_crop):
        """When adding lower confidence fallback, both are kept (source adds as new)."""
        # Arrange
        crop1 = np.zeros((50, 100, 3), dtype=np.uint8)
        crop2 = np.ones((50, 100, 3), dtype=np.uint8)
        
        algorithm.add_candidate_crop(crop1, "", 0.9, is_fallback=True)

        # Act - add lower confidence fallback
        # Source code: break happens ONLY when confidence > existing, so this breaks
        # without setting existing_idx, thus the new crop gets appended
        algorithm.add_candidate_crop(crop2, "", 0.7, is_fallback=True)

        # Assert - both are added (source breaks out of loop without replacement)
        assert len(algorithm.candidate_crops) == 2
        assert algorithm.candidate_crops[0]["confidence"] == 0.9

    def test_add_multiple_different_texts(self, algorithm, sample_crop):
        """Add multiple candidates with different texts."""
        # Act
        algorithm.add_candidate_crop(sample_crop, "ABC123", 0.9, is_fallback=False)
        algorithm.add_candidate_crop(sample_crop, "DEF456", 0.85, is_fallback=False)

        # Assert
        assert len(algorithm.candidate_crops) == 2


# =============================================================================
# Tests for add_to_consensus
# =============================================================================

class TestAddToConsensus:
    """Tests for the consensus voting mechanism."""

    def test_add_valid_text_creates_position_counters(self, algorithm):
        """Valid text creates counter entries for each position."""
        # Act
        algorithm.add_to_consensus("ABCD", 0.95)

        # Assert
        assert len(algorithm.counter) == 4
        assert 0 in algorithm.counter
        assert 1 in algorithm.counter
        assert 2 in algorithm.counter
        assert 3 in algorithm.counter

    def test_vote_weight_is_2_for_high_confidence(self, algorithm):
        """High confidence (>=0.95) gets vote weight of 2."""
        # Act - use 4+ char text to pass MIN_TEXT_LENGTH
        algorithm.add_to_consensus("ABCD", 0.95)

        # Assert
        assert algorithm.counter[0]['A'] == 2
        assert algorithm.counter[1]['B'] == 2

    def test_vote_weight_is_1_for_lower_confidence(self, algorithm):
        """Lower confidence (<0.95) gets vote weight of 1."""
        # Act - use 4+ char text to pass MIN_TEXT_LENGTH
        algorithm.add_to_consensus("ABCD", 0.90)

        # Assert
        assert algorithm.counter[0]['A'] == 1
        assert algorithm.counter[1]['B'] == 1

    def test_skip_low_confidence_text(self, algorithm):
        """Text with confidence below MIN_CONFIDENCE_CONSENSUS is skipped."""
        # Act
        algorithm.add_to_consensus("ABCD", MIN_CONFIDENCE_CONSENSUS - 0.01)

        # Assert
        assert algorithm.counter == {}

    def test_skip_short_text(self, algorithm):
        """Text shorter than MIN_TEXT_LENGTH is skipped."""
        # Act - text with only 3 chars (MIN_TEXT_LENGTH is 4)
        algorithm.add_to_consensus("ABC", 0.95)

        # Assert
        assert algorithm.counter == {}

    def test_normalizes_text_uppercase_and_removes_dashes(self, algorithm):
        """Text is normalized: uppercase and dashes removed."""
        # Act
        algorithm.add_to_consensus("ab-cd", 0.95)

        # Assert
        assert 'A' in algorithm.counter[0]
        assert 'B' in algorithm.counter[1]
        assert 'C' in algorithm.counter[2]
        assert 'D' in algorithm.counter[3]

    def test_accumulates_votes_across_multiple_texts(self, algorithm):
        """Multiple texts accumulate votes at each position."""
        # Act
        algorithm.add_to_consensus("ABCD", 0.90)  # Weight 1
        algorithm.add_to_consensus("ABCD", 0.95)  # Weight 2

        # Assert
        assert algorithm.counter[0]['A'] == 3  # 1 + 2

    def test_length_mismatch_skipped_after_establishing_most_common(self, algorithm):
        """After establishing common length, mismatched lengths are skipped."""
        # Arrange - establish 4 as most common length
        algorithm.add_to_consensus("ABCD", 0.95)
        algorithm.add_to_consensus("EFGH", 0.95)
        algorithm.add_to_consensus("IJKL", 0.95)

        # Get current counter positions (should be 0-3)
        positions_before = set(algorithm.counter.keys())

        # Act - add different length (should be skipped)
        algorithm.add_to_consensus("ABCDE", 0.95)  # 5 chars vs established 4

        # Assert - position 4 should NOT be added (5th char index)
        assert 4 not in algorithm.counter
        assert set(algorithm.counter.keys()) == positions_before


# =============================================================================
# Tests for update_position_decision
# =============================================================================

class TestUpdatePositionDecision:
    """Tests for the position decision updates."""

    def test_no_decision_below_threshold(self, algorithm):
        """Position not decided if count below threshold."""
        # Arrange
        algorithm.counter = {0: {'A': DECISION_THRESHOLD - 1}}

        # Act
        algorithm.update_position_decision(0, 'A')

        # Assert
        assert 0 not in algorithm.decided_chars

    def test_decision_at_threshold(self, algorithm):
        """Position is decided when count reaches threshold."""
        # Arrange
        algorithm.counter = {0: {'A': DECISION_THRESHOLD}}

        # Act
        algorithm.update_position_decision(0, 'A')

        # Assert
        assert algorithm.decided_chars[0] == 'A'

    def test_decision_changes_when_new_char_exceeds(self, algorithm):
        """Decision can change if new character exceeds threshold."""
        # Arrange
        algorithm.counter = {0: {'A': DECISION_THRESHOLD}}
        algorithm.decided_chars = {0: 'A'}
        algorithm.counter[0]['B'] = DECISION_THRESHOLD + 1

        # Act
        algorithm.update_position_decision(0, 'B')

        # Assert
        assert algorithm.decided_chars[0] == 'B'


# =============================================================================
# Tests for check_full_consensus
# =============================================================================

class TestCheckFullConsensus:
    """Tests for consensus checking."""

    def test_empty_counter_returns_false(self, algorithm):
        """Empty counter means no consensus."""
        # Act
        result = algorithm.check_full_consensus()

        # Assert
        assert result is False

    def test_not_enough_decisions_returns_false(self, algorithm):
        """Not enough decided positions returns False."""
        # Arrange - 10 positions, only 5 decided (50%)
        algorithm.counter = {i: {'A': 5} for i in range(10)}
        algorithm.decided_chars = {i: 'A' for i in range(5)}

        # Act
        result = algorithm.check_full_consensus()

        # Assert
        assert result is False
        assert algorithm.consensus_reached is False

    def test_consensus_reached_at_threshold(self, algorithm):
        """Consensus reached when enough positions decided."""
        # Arrange - 10 positions, 8 decided (80% = CONSENSUS_PERCENTAGE)
        algorithm.counter = {i: {'A': 10} for i in range(10)}
        algorithm.decided_chars = {i: 'A' for i in range(8)}

        # Act
        result = algorithm.check_full_consensus()

        # Assert
        assert result is True
        assert algorithm.consensus_reached is True

    def test_consensus_reached_above_threshold(self, algorithm):
        """Consensus reached when more than threshold decided."""
        # Arrange - 10 positions, 10 decided (100%)
        algorithm.counter = {i: {'A': 10} for i in range(10)}
        algorithm.decided_chars = {i: 'A' for i in range(10)}

        # Act
        result = algorithm.check_full_consensus()

        # Assert
        assert result is True


# =============================================================================
# Tests for build_final_text
# =============================================================================

class TestBuildFinalText:
    """Tests for building final text from decided characters."""

    def test_empty_decided_returns_empty_string(self, algorithm):
        """No decided chars returns empty string."""
        # Act
        result = algorithm.build_final_text()

        # Assert
        assert result == ""

    def test_builds_text_from_decided_chars(self, algorithm):
        """Builds text from all decided positions in order."""
        # Arrange
        algorithm.decided_chars = {0: 'A', 1: 'B', 2: 'C', 3: '1', 4: '2', 5: '3'}

        # Act
        result = algorithm.build_final_text()

        # Assert
        assert result == "ABC123"

    def test_handles_sparse_positions(self, algorithm):
        """Builds text correctly even with non-sequential positions."""
        # Arrange
        algorithm.decided_chars = {0: 'X', 2: 'Y', 4: 'Z'}

        # Act
        result = algorithm.build_final_text()

        # Assert
        assert result == "XYZ"


# =============================================================================
# Tests for select_best_crop
# =============================================================================

class TestSelectBestCrop:
    """Tests for selecting the best crop based on text similarity."""

    def test_no_candidates_returns_none(self, algorithm):
        """No candidates returns None."""
        # Act
        result = algorithm.select_best_crop("ABC123")

        # Assert
        assert result is None

    def test_no_final_text_returns_highest_confidence_crop(self, algorithm, sample_crop):
        """Without final text, return crop with highest confidence."""
        # Arrange
        crop1 = np.zeros((50, 100, 3), dtype=np.uint8)
        crop2 = np.ones((50, 100, 3), dtype=np.uint8)
        
        algorithm.candidate_crops = [
            {"crop": crop1, "text": "ABC", "confidence": 0.7},
            {"crop": crop2, "text": "DEF", "confidence": 0.9},
        ]

        # Act
        result = algorithm.select_best_crop("")

        # Assert
        assert np.array_equal(result, crop2)

    @patch("consensus_algorithm.levenshtein_distance")
    def test_selects_crop_with_highest_similarity(self, mock_distance, algorithm, sample_crop):
        """Select crop with text most similar to final text."""
        # Arrange
        crop1 = np.zeros((50, 100, 3), dtype=np.uint8)
        crop2 = np.ones((50, 100, 3), dtype=np.uint8)
        
        algorithm.candidate_crops = [
            {"crop": crop1, "text": "ABC124", "confidence": 0.9},  # 1 char different
            {"crop": crop2, "text": "ABC123", "confidence": 0.85},  # Exact match
        ]
        
        # Mock distances: exact match = 0, one off = 1
        mock_distance.side_effect = lambda a, b: 0 if a == b else 1

        # Act
        result = algorithm.select_best_crop("ABC123")

        # Assert
        assert np.array_equal(result, crop2)
        assert algorithm.best_crop is not None

    @patch("consensus_algorithm.levenshtein_distance")
    def test_uses_confidence_as_tiebreaker(self, mock_distance, algorithm):
        """When similarity is equal, use confidence as tiebreaker."""
        # Arrange
        crop1 = np.zeros((50, 100, 3), dtype=np.uint8)
        crop2 = np.ones((50, 100, 3), dtype=np.uint8)
        
        algorithm.candidate_crops = [
            {"crop": crop1, "text": "ABC123", "confidence": 0.85},
            {"crop": crop2, "text": "ABC123", "confidence": 0.95},  # Same text, higher conf
        ]
        
        mock_distance.return_value = 0  # Both match exactly

        # Act
        result = algorithm.select_best_crop("ABC123")

        # Assert
        assert np.array_equal(result, crop2)
        assert algorithm.best_confidence == 0.95


# =============================================================================
# Tests for get_best_partial_result
# =============================================================================

class TestGetBestPartialResult:
    """Tests for getting partial results when full consensus not reached."""

    def test_no_candidates_no_counter_returns_none_tuple(self, algorithm):
        """No data at all returns (None, None, None)."""
        # Act
        text, conf, crop = algorithm.get_best_partial_result("license plate")

        # Assert
        assert text is None
        assert conf is None
        assert crop is None

    def test_fallback_to_yolo_crop_when_no_text_consensus(self, algorithm, sample_crop):
        """When no text consensus, use best YOLO detection."""
        # Arrange
        algorithm.candidate_crops = [
            {"crop": sample_crop, "text": "", "confidence": 0.85, "is_fallback": True},
        ]

        # Act
        text, conf, crop = algorithm.get_best_partial_result("license plate")

        # Assert - text is "N/A", conf is best_confidence (0.0 since select_best_crop
        # with empty final_text doesn't set best_confidence)
        assert text == "N/A"
        assert conf == 0.0  # best_confidence not updated when no final_text
        assert crop is not None

    @patch("consensus_algorithm.levenshtein_distance")
    def test_builds_partial_text_from_counter(self, mock_distance, algorithm, sample_crop):
        """Builds partial text using decided and most voted characters."""
        # Arrange
        algorithm.counter = {
            0: {'A': 5},
            1: {'B': 8},  # Decided
            2: {'C': 3},
            3: {'1': 2},
        }
        algorithm.decided_chars = {1: 'B'}
        algorithm.candidate_crops = [
            {"crop": sample_crop, "text": "AB1", "confidence": 0.9},
        ]
        mock_distance.return_value = 1

        # Act
        text, conf, crop = algorithm.get_best_partial_result("hazard plate")

        # Assert
        assert 'B' in text  # Decided char should be present
        assert conf <= 0.95  # Confidence capped at 0.95

    def test_uses_underscore_for_missing_positions(self, algorithm, sample_crop):
        """Uses underscore for positions with no votes."""
        # Arrange
        algorithm.counter = {
            0: {'A': 5},
            1: {},  # No votes
            2: {'C': 3},
        }
        algorithm.candidate_crops = [
            {"crop": sample_crop, "text": "AC", "confidence": 0.9},
        ]

        # Act
        text, conf, crop = algorithm.get_best_partial_result("license plate")

        # Assert
        assert '_' in text


# =============================================================================
# Tests for internal helper methods
# =============================================================================

class TestInternalMethods:
    """Tests for internal helper methods."""

    def test_normalize_text_uppercase(self, algorithm):
        """_normalize_text converts to uppercase."""
        # Act
        result = algorithm._normalize_text("abc123")

        # Assert
        assert result == "ABC123"

    def test_normalize_text_removes_dashes(self, algorithm):
        """_normalize_text removes dashes."""
        # Act
        result = algorithm._normalize_text("AB-12-CD")

        # Assert
        assert result == "AB12CD"

    def test_is_valid_for_consensus_rejects_low_confidence(self, algorithm):
        """_is_valid_for_consensus rejects low confidence."""
        # Act
        result = algorithm._is_valid_for_consensus("ABCD", 0.5)

        # Assert
        assert result is False

    def test_is_valid_for_consensus_rejects_short_text(self, algorithm):
        """_is_valid_for_consensus rejects short text."""
        # Act
        result = algorithm._is_valid_for_consensus("AB", 0.95)

        # Assert
        assert result is False

    def test_is_valid_for_consensus_accepts_valid(self, algorithm):
        """_is_valid_for_consensus accepts valid text and confidence."""
        # Act
        result = algorithm._is_valid_for_consensus("ABCD", 0.95)

        # Assert
        assert result is True

    def test_get_vote_weight_high_confidence(self, algorithm):
        """_get_vote_weight returns 2 for high confidence."""
        # Act
        result = algorithm._get_vote_weight(0.95)

        # Assert
        assert result == 2

    def test_get_vote_weight_lower_confidence(self, algorithm):
        """_get_vote_weight returns 1 for lower confidence."""
        # Act
        result = algorithm._get_vote_weight(0.90)

        # Assert
        assert result == 1

    def test_track_text_length_first_few_entries(self, algorithm):
        """_track_text_length accepts all in first few entries."""
        # Act
        result1 = algorithm._track_text_length(6)
        result2 = algorithm._track_text_length(5)

        # Assert - first few are always accepted
        assert result1 is True
        assert result2 is True

    def test_track_text_length_rejects_outliers(self, algorithm):
        """_track_text_length rejects outlier lengths after establishing pattern."""
        # Arrange - establish 6 as common length
        algorithm._track_text_length(6)
        algorithm._track_text_length(6)
        algorithm._track_text_length(6)

        # Act - try to add different length
        result = algorithm._track_text_length(8)

        # Assert
        assert result is False
