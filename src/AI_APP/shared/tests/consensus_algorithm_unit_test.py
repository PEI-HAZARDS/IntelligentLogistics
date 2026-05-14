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

from AI_APP.shared.src.consensus_algorithm import (
    ConsensusAlgorithm,
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

    def test_most_common_length_can_shift_and_then_accept_new_length(self, algorithm):
        """Length 5 is accepted only after it overtakes length 4 as most common."""
        # Arrange - establish 4 as most common (3 accepted samples)
        algorithm.add_to_consensus("ABCD", 0.95)
        algorithm.add_to_consensus("EFGH", 0.95)
        algorithm.add_to_consensus("IJKL", 0.95)

        # Act - add three length-5 samples; still tied or behind, should be skipped
        algorithm.add_to_consensus("ABCDE", 0.95)  # counts: 4->3, 5->1
        algorithm.add_to_consensus("FGHIJ", 0.95)  # counts: 4->3, 5->2
        algorithm.add_to_consensus("KLMNO", 0.95)  # counts: 4->3, 5->3 (tie -> prefer 4)

        # Tie-breaker: when counts are equal, the algorithm prefers the larger
        # negative length value; for example, -4 > -5, so length 4 is chosen.
        # Assert - still using length 4, so position 4 must not exist yet
        assert 4 not in algorithm.counter

        # Act - fourth length-5 sample makes 5 the most common and should be accepted
        algorithm.add_to_consensus("PQRST", 0.95)  # counts: 4->3, 5->4

        # Assert - now length 5 is accepted, adding the 5th character position
        assert 4 in algorithm.counter
        assert algorithm._get_most_common_length() == 5


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

    def test_consensus_not_reached_until_all_expected_positions_decided(self, algorithm):
        """Consensus requires 100% of expected positions, not 80%."""
        # Arrange - 10 positions, 8 decided (should still be False)
        algorithm.counter = {i: {'A': 10} for i in range(10)}
        algorithm.decided_chars = {i: 'A' for i in range(8)}

        # Act
        result = algorithm.check_full_consensus()

        # Assert
        assert result is False
        assert algorithm.consensus_reached is False

    def test_consensus_reached_when_all_expected_positions_decided(self, algorithm):
        """Consensus reached only when all expected positions are decided."""
        # Arrange - 10 positions, 10 decided (100%)
        algorithm.counter = {i: {'A': 10} for i in range(10)}
        algorithm.decided_chars = {i: 'A' for i in range(10)}

        # Act
        result = algorithm.check_full_consensus()

        # Assert
        assert result is True

    def test_consensus_uses_most_common_length_as_expected_positions(self, algorithm):
        """Outlier positions do not block consensus when most common length is complete."""
        # Arrange - raw counter includes outlier 7th position, but expected length is 6
        algorithm.length_counter = {6: 5, 7: 1}
        algorithm.counter = {i: {'A': 10} for i in range(7)}
        algorithm.decided_chars = {i: 'A' for i in range(6)}
        algorithm.decided_chars[6] = 'Z'  # out-of-range decided position should be ignored

        # Assert inferred expected length before checking consensus
        assert algorithm._get_expected_positions() == 6

        # Act
        result = algorithm.check_full_consensus()

        # Assert
        assert result is True
        assert algorithm.consensus_reached is True

    def test_returns_false_when_expected_positions_is_zero(self, algorithm):
        """Consensus should fail when expected position inference returns 0."""
        # Arrange
        algorithm.counter = {0: {'A': 10}}

        # Act
        with patch.object(algorithm, "_get_expected_positions", return_value=0):
            result = algorithm.check_full_consensus()

        # Assert
        assert result is False
        assert algorithm.consensus_reached is False

    def test_resets_stale_consensus_flag_when_current_state_has_no_consensus(self, algorithm):
        """A previously True consensus flag should be cleared when current check fails."""
        # Arrange - stale state from an older cycle without calling reset().
        algorithm.consensus_reached = True
        algorithm.counter = {i: {'A': 10} for i in range(6)}
        algorithm.decided_chars = {0: 'A', 1: 'B'}  # not enough for full consensus

        # Act
        result = algorithm.check_full_consensus()

        # Assert
        assert result is False
        assert algorithm.consensus_reached is False


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

    def test_uses_expected_length_when_available(self, algorithm):
        """Build final text uses inferred expected length and ignores out-of-range positions."""
        # Arrange
        algorithm.length_counter = {6: 5, 7: 1}
        algorithm.decided_chars = {
            0: 'A', 1: 'B', 2: 'C', 3: '1', 4: '2', 5: '3', 6: 'Z'
        }

        # Expected length is driven by length_counter (6), not by extra decided positions.
        assert algorithm._get_expected_positions() == 6

        # Act
        result = algorithm.build_final_text()

        # Assert
        assert result == "ABC123"

    def test_returns_empty_string_when_expected_length_has_missing_position(self, algorithm):
        """Returns empty string when expected length is known but a required position is undecided."""
        # Arrange
        algorithm.length_counter = {6: 5, 7: 1}
        algorithm.counter = {i: {'A': 10} for i in range(6)}
        algorithm.decided_chars = {
            0: 'A', 1: 'B', 2: 'C', 4: '2', 5: '3'
        }

        # Act
        result = algorithm.build_final_text()

        # Assert
        assert result == ""


# =============================================================================
# Tests for compute_consensus_confidence
# =============================================================================

class TestComputeConsensusConfidence:
    """Tests for consensus confidence computation."""

    def test_returns_zero_without_required_state(self, algorithm):
        """Returns 0.0 when there are no decided chars or no counter."""
        # Arrange
        algorithm.decided_chars = {}
        algorithm.counter = {}

        # Act
        confidence = algorithm.compute_consensus_confidence()

        # Assert
        assert confidence == 0.0

    def test_uses_zero_avg_when_no_accepted_confidences(self, algorithm):
        """Agreement exists, but confidence is 0.0 when accepted_confidences is empty."""
        # Arrange
        algorithm.counter = {
            0: {'A': 8, 'B': 2},
            1: {'B': 7, 'C': 3},
        }
        algorithm.decided_chars = {0: 'A', 1: 'B'}
        algorithm.accepted_confidences = []

        # Act
        confidence = algorithm.compute_consensus_confidence()

        # Assert
        assert confidence == 0.0

    def test_computes_agreement_times_avg_ocr_confidence(self, algorithm):
        """Confidence should be agreement score multiplied by average OCR confidence."""
        # Arrange
        algorithm.counter = {
            0: {'A': 8, 'B': 2},  # dominance = 0.8
            1: {'B': 6, 'C': 4},  # dominance = 0.6
        }
        algorithm.decided_chars = {0: 'A', 1: 'B'}
        algorithm.accepted_confidences = [0.9, 0.8]  # avg = 0.85

        # expected = mean([0.8, 0.6]) * 0.85 = 0.7 * 0.85 = 0.595
        # Act
        confidence = algorithm.compute_consensus_confidence()

        # Assert
        assert confidence == pytest.approx(0.595, rel=1e-6)


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

    def test_no_final_text_updates_best_crop_and_confidence(self, algorithm):
        """Selecting without final text should still keep internal best state synchronized."""
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
        assert np.array_equal(algorithm.best_crop, crop2)
        assert algorithm.best_confidence == pytest.approx(0.9, rel=1e-6)

    @patch("AI_APP.shared.src.consensus_algorithm.levenshtein_distance")
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

    @patch("AI_APP.shared.src.consensus_algorithm.levenshtein_distance")
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

        # Assert
        assert text == "N/A"
        assert conf == pytest.approx(0.85, rel=1e-6)
        assert crop is not None
        assert np.array_equal(algorithm.best_crop, crop)
        assert algorithm.best_confidence == pytest.approx(conf, rel=1e-6)

    @patch("AI_APP.shared.src.consensus_algorithm.levenshtein_distance")
    def test_falls_back_to_counter_range_when_expected_positions_is_zero(self, mock_distance, algorithm, sample_crop):
        """Partial result should fallback to max(counter.keys()) + 1 when expected length is unavailable."""
        # Arrange
        algorithm.counter = {
            0: {'A': 5},
            1: {'B': 3},
        }
        algorithm.decided_chars = {0: 'A'}
        algorithm.candidate_crops = [
            {"crop": sample_crop, "text": "AB", "confidence": 0.9},
        ]
        mock_distance.return_value = 0

        # Act
        with patch.object(algorithm, "_get_expected_positions", return_value=0):
            text, conf, crop = algorithm.get_best_partial_result("license plate")

        # Assert
        assert text == "AB"
        assert conf == pytest.approx(0.5, rel=1e-6)  # 1 decided out of 2 positions
        assert crop is not None

    @patch("AI_APP.shared.src.consensus_algorithm.levenshtein_distance")
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

    @patch("AI_APP.shared.src.consensus_algorithm.levenshtein_distance")
    def test_partial_confidence_ignores_out_of_range_decisions(self, mock_distance, algorithm, sample_crop):
        """Confidence should count only decided positions within expected range."""
        # Arrange: expected length is 6, but decided chars include outlier positions 6 and 7.
        algorithm.length_counter = {6: 5, 7: 1}
        algorithm.counter = {i: {'A': 3} for i in range(8)}
        algorithm.decided_chars = {
            0: 'A', 1: 'B', 2: 'C', 3: '1', 6: 'X', 7: 'Y'
        }
        algorithm.candidate_crops = [
            {"crop": sample_crop, "text": "ABC1XY", "confidence": 0.9},
        ]
        mock_distance.return_value = 1

        # Act
        _, conf, _ = algorithm.get_best_partial_result("license plate")

        # Assert: only positions 0..5 count -> 4/6, not 6/6.
        assert conf == pytest.approx(4 / 6, rel=1e-6)

    @patch("AI_APP.shared.src.consensus_algorithm.levenshtein_distance")
    def test_partial_confidence_blends_completeness_with_quality(self, mock_distance, algorithm, sample_crop):
        """When accepted OCR confidence exists, partial confidence blends completeness and quality."""
        # Arrange
        algorithm.counter = {
            0: {'A': 9, 'B': 1},  # dominance 0.9
            1: {'C': 8, 'D': 2},  # dominance 0.8
        }
        algorithm.decided_chars = {0: 'A'}  # completeness = 1/2 = 0.5
        algorithm.accepted_confidences = [0.9, 0.8]  # avg = 0.85
        algorithm.candidate_crops = [
            {"crop": sample_crop, "text": "AC", "confidence": 0.9},
        ]
        mock_distance.return_value = 0

        # Act
        _, conf, _ = algorithm.get_best_partial_result("license plate")

        # quality = mean(0.9, 0.8) * 0.85 = 0.7225
        # blended = (0.5 + 0.7225) / 2 = 0.61125
        assert conf == pytest.approx(0.61125, rel=1e-6)

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
# Tests for real-world noisy scenarios
# =============================================================================

class TestRealWorldConsensusScenarios:
    """Scenario tests with many noisy readings to simulate production behavior."""

    def test_full_consensus_with_many_readings_and_noise(self, algorithm):
        """Full consensus should still converge with many readings and realistic OCR noise."""
        # Arrange: a mix of clean reads, one-char OCR mistakes, low-confidence and short noise.
        readings = [
            ("ABC123", 0.96), ("ABC123", 0.96), ("ABC123", 0.96),
            ("ABC123", 0.96), ("ABC123", 0.96), ("ABC123", 0.96),
            ("ABC12B", 0.90), ("ABG123", 0.90), ("A8C123", 0.90), ("ABCI23", 0.90),
            ("ABC123", 0.40), ("ABC123", 0.55),  # ignored by confidence threshold
            ("AB1", 0.99), ("A2", 0.99),  # ignored by min text length
        ]

        # Act
        for text, conf in readings:
            algorithm.add_to_consensus(text, conf)

        consensus_reached = algorithm.check_full_consensus()
        final_text = algorithm.build_final_text()
        confidence = algorithm.compute_consensus_confidence()

        # Assert
        assert consensus_reached is True
        assert final_text == "ABC123"
        assert confidence > 0.8

    def test_partial_result_with_many_readings_and_last_char_noise(self, algorithm, sample_crop):
        """Partial path should return best-effort text/confidence when one position never reaches threshold."""
        # Arrange: first 5 positions are stable; last position flips between two options.
        for _ in range(7):
            algorithm.add_to_consensus("ABC123", 0.90)
        for _ in range(6):
            algorithm.add_to_consensus("ABC128", 0.90)

        algorithm.add_candidate_crop(sample_crop, "ABC123", 0.88, is_fallback=False)

        # Act
        consensus_reached = algorithm.check_full_consensus()
        text, conf, crop = algorithm.get_best_partial_result("license plate")

        # Assert: no full consensus (last position is undecided), but partial should be coherent.
        assert consensus_reached is False
        assert text == "ABC123"
        assert crop is not None

        expected_completeness = 5 / 6
        expected_agreement = (1 + 1 + 1 + 1 + 1 + (7 / 13)) / 6
        expected_quality = expected_agreement * 0.90
        expected_confidence = min((expected_completeness + expected_quality) / 2, 0.95)
        assert conf == pytest.approx(expected_confidence, rel=1e-6)


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

    def test_get_most_common_length_returns_zero_when_empty(self, algorithm):
        """_get_most_common_length returns 0 when no lengths were observed."""
        # Act
        result = algorithm._get_most_common_length()

        # Assert
        assert result == 0

    def test_average_ocr_confidence_returns_zero_when_empty(self, algorithm):
        """_average_ocr_confidence returns 0.0 when there are no accepted confidences."""
        # Act
        result = algorithm._average_ocr_confidence()

        # Assert
        assert result == 0.0

    def test_average_ocr_confidence_returns_mean(self, algorithm):
        """_average_ocr_confidence returns arithmetic mean of accepted confidences."""
        # Arrange
        algorithm.accepted_confidences = [0.8, 0.9, 1.0]

        # Act
        result = algorithm._average_ocr_confidence()

        # Assert
        assert result == pytest.approx(0.9, rel=1e-6)

    def test_compute_agreement_score_uses_decided_chars(self, algorithm):
        """_compute_agreement_score should use decided character vote when requested."""
        # Arrange
        algorithm.counter = {
            0: {'A': 8, 'B': 2},
            1: {'C': 7, 'D': 3},
        }
        algorithm.decided_chars = {0: 'A', 1: 'C'}

        # Act
        result = algorithm._compute_agreement_score(positions=[0, 1], use_decided_chars=True)

        # Assert: (0.8 + 0.7) / 2 = 0.75
        assert result == pytest.approx(0.75, rel=1e-6)

    def test_compute_agreement_score_returns_zero_without_valid_positions(self, algorithm):
        """_compute_agreement_score returns 0.0 when positions have no valid vote data."""
        # Arrange
        algorithm.counter = {0: {}}

        # Act
        result = algorithm._compute_agreement_score(positions=[0, 1], use_decided_chars=False)

        # Assert
        assert result == 0.0

    def test_compute_partial_confidence_uses_completeness_without_ocr_quality(self, algorithm):
        """_compute_partial_confidence falls back to completeness when OCR quality is unavailable."""
        # Arrange
        algorithm.counter = {
            0: {'A': 3},
            1: {'B': 2},
            2: {'C': 1},
        }
        algorithm.accepted_confidences = []

        # Act
        result = algorithm._compute_partial_confidence(total_positions=3, decided_count=1)

        # Assert
        assert result == pytest.approx(1 / 3, rel=1e-6)

    def test_compute_partial_confidence_blends_completeness_and_quality(self, algorithm):
        """_compute_partial_confidence blends completeness with quality score when available."""
        # Arrange
        algorithm.counter = {
            0: {'A': 9, 'B': 1},  # dominance 0.9
            1: {'C': 8, 'D': 2},  # dominance 0.8
        }
        algorithm.accepted_confidences = [0.9, 0.8]  # avg 0.85

        # Act
        result = algorithm._compute_partial_confidence(total_positions=2, decided_count=1)

        # Assert: completeness=0.5, quality=(0.85*0.85)=0.7225, blended=0.61125
        assert result == pytest.approx(0.61125, rel=1e-6)

    def test_compute_partial_confidence_is_capped_at_ninety_five_percent(self, algorithm):
        """_compute_partial_confidence should cap values to 0.95."""
        # Arrange
        algorithm.counter = {
            0: {'A': 5},
            1: {'B': 5},
        }
        algorithm.accepted_confidences = [1.0]

        # Act
        result = algorithm._compute_partial_confidence(total_positions=2, decided_count=2)

        # Assert
        assert result == pytest.approx(0.95, rel=1e-6)

    def test_compute_partial_confidence_returns_zero_for_invalid_total_positions(self, algorithm):
        """_compute_partial_confidence returns 0.0 when total_positions is not positive."""
        # Act
        result = algorithm._compute_partial_confidence(total_positions=0, decided_count=0)

        # Assert
        assert result == 0.0

