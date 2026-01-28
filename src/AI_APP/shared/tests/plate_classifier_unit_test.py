"""
Unit tests for shared/src/plate_classifier.py

Tests cover:
- PlateClassifier initialization
- Plate classification based on aspect ratio and color
- Color analysis
- Visualization (with mocked cv2)

All cv2 calls are mocked where necessary.
"""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def classifier():
    """Create a fresh PlateClassifier instance."""
    from plate_classifier import PlateClassifier
    return PlateClassifier()


@pytest.fixture
def wide_white_image():
    """Create a wide image with predominantly white color (license plate-like)."""
    # Wide aspect ratio: 200x50 (4:1)
    # White color in BGR
    img = np.ones((50, 200, 3), dtype=np.uint8) * 255
    return img


@pytest.fixture
def square_orange_image():
    """Create a square image with predominantly orange color (hazard plate-like)."""
    # Square aspect ratio: 100x100
    # Orange in BGR (0, 165, 255)
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img[:, :] = [0, 165, 255]  # BGR for orange
    return img


# =============================================================================
# Tests for __init__ and constants
# =============================================================================

class TestPlateClassifierInit:
    """Tests for PlateClassifier initialization."""

    def test_initialization_sets_thresholds(self, classifier):
        """Initialization sets aspect ratio thresholds."""
        # Assert
        assert classifier.min_aspect_ratio_license == 1.5
        assert classifier.max_aspect_ratio_hazard == 1.2

    def test_class_constants_defined(self, classifier):
        """Class constants are defined."""
        # Assert
        assert classifier.LICENSE_PLATE == "license_plate"
        assert classifier.HAZARD_PLATE == "hazard_plate"
        assert classifier.UNKNOWN == "unknown"

    def test_color_ranges_defined(self, classifier):
        """Color ranges are defined for classification."""
        # Assert
        assert len(classifier.license_plate_colors) == 2  # White, Yellow
        assert len(classifier.hazard_plate_colors) == 3  # Orange, Red(2 parts)


# =============================================================================
# Tests for classify
# =============================================================================

class TestClassify:
    """Tests for the classify method."""

    def test_none_input_returns_unknown(self, classifier):
        """None input returns UNKNOWN."""
        # Act
        result = classifier.classify(None)

        # Assert
        assert result == classifier.UNKNOWN

    def test_empty_array_returns_unknown(self, classifier):
        """Empty array returns UNKNOWN."""
        # Arrange
        empty = np.array([], dtype=np.uint8)

        # Act
        result = classifier.classify(empty)

        # Assert
        assert result == classifier.UNKNOWN

    def test_zero_dimension_returns_unknown(self, classifier):
        """Zero dimension image returns UNKNOWN."""
        # Arrange
        zero_dim = np.zeros((0, 100, 3), dtype=np.uint8)

        # Act
        result = classifier.classify(zero_dim)

        # Assert
        assert result == classifier.UNKNOWN

    @patch("plate_classifier.cv2")
    def test_wide_white_classified_as_license_plate(self, mock_cv2, classifier, wide_white_image):
        """Wide white image classified as LICENSE_PLATE."""
        # Arrange
        # Mock HSV conversion
        mock_cv2.cvtColor.return_value = np.ones((50, 200, 3), dtype=np.uint8) * 200
        mock_cv2.COLOR_BGR2HSV = 40
        # 2 license colors, 3 hazard colors - license score higher
        mock_cv2.countNonZero.side_effect = [5000, 3000, 500, 500, 500]
        mock_cv2.inRange.return_value = np.ones((50, 200), dtype=np.uint8) * 255

        # Act
        result = classifier.classify(wide_white_image)

        # Assert
        assert result == classifier.LICENSE_PLATE

    @patch("plate_classifier.cv2")
    def test_square_orange_classified_as_hazard_plate(self, mock_cv2, classifier, square_orange_image):
        """Square orange image classified as HAZARD_PLATE."""
        # Arrange
        mock_cv2.cvtColor.return_value = np.ones((100, 100, 3), dtype=np.uint8) * 15  # Orange hue
        # First 2 calls for license colors (return 0), then hazard colors (return high)
        mock_cv2.countNonZero.side_effect = [0, 0, 5000, 3000, 2000]

        # Act
        result = classifier.classify(square_orange_image)

        # Assert
        assert result == classifier.HAZARD_PLATE

    @patch("plate_classifier.cv2")
    def test_ambiguous_returns_unknown(self, mock_cv2, classifier):
        """Ambiguous image (medium aspect ratio, mixed colors) returns UNKNOWN."""
        # Arrange
        # Create medium aspect ratio image (1.3)
        img = np.ones((100, 130, 3), dtype=np.uint8) * 128
        mock_cv2.cvtColor.return_value = np.ones((100, 130, 3), dtype=np.uint8) * 90
        # Similar scores for both
        mock_cv2.countNonZero.side_effect = [1000, 1000, 1000, 1000, 1000]

        # Act
        result = classifier.classify(img)

        # Assert
        assert result == classifier.UNKNOWN

    @patch("plate_classifier.cv2")
    def test_strong_license_color_wins_tiebreaker(self, mock_cv2, classifier):
        """Strong license plate color wins tiebreaker (1.5x threshold)."""
        # Arrange
        # Create medium aspect ratio image
        img = np.ones((100, 130, 3), dtype=np.uint8) * 255
        mock_cv2.cvtColor.return_value = np.ones((100, 130, 3), dtype=np.uint8) * 200
        # License score > 1.5 * hazard score
        mock_cv2.countNonZero.side_effect = [6000, 4000, 1000, 500, 500]

        # Act
        result = classifier.classify(img)

        # Assert
        assert result == classifier.LICENSE_PLATE

    @patch("plate_classifier.cv2")
    def test_strong_hazard_color_wins_tiebreaker(self, mock_cv2, classifier):
        """Strong hazard plate color wins tiebreaker (1.5x threshold)."""
        # Arrange
        img = np.ones((100, 130, 3), dtype=np.uint8) * 128
        mock_cv2.cvtColor.return_value = np.ones((100, 130, 3), dtype=np.uint8) * 15
        # Hazard score > 1.5 * license score
        mock_cv2.countNonZero.side_effect = [500, 500, 6000, 4000, 4000]

        # Act
        result = classifier.classify(img)

        # Assert
        assert result == classifier.HAZARD_PLATE


# =============================================================================
# Tests for _analyze_colors
# =============================================================================

class TestAnalyzeColors:
    """Tests for color analysis method."""

    @patch("plate_classifier.cv2")
    def test_returns_normalized_scores(self, mock_cv2, classifier):
        """Returns normalized scores between 0 and 1."""
        # Arrange
        img = np.ones((100, 100, 3), dtype=np.uint8) * 255
        mock_cv2.cvtColor.return_value = np.ones((100, 100, 3), dtype=np.uint8) * 200
        mock_cv2.countNonZero.return_value = 2500  # 25% of 10000 pixels

        # Act
        scores = classifier._analyze_colors(img)

        # Assert
        assert 0 <= scores['license'] <= 1
        assert 0 <= scores['hazard'] <= 1

    @patch("plate_classifier.cv2")
    def test_license_score_accumulates_across_ranges(self, mock_cv2, classifier):
        """License score accumulates across all color ranges."""
        # Arrange
        img = np.ones((100, 100, 3), dtype=np.uint8)
        mock_cv2.cvtColor.return_value = img
        # 2 license colors, 3 hazard colors
        mock_cv2.countNonZero.side_effect = [1000, 2000, 500, 500, 500]

        # Act
        scores = classifier._analyze_colors(img)

        # Assert
        # License: (1000 + 2000) / 10000 = 0.3
        assert scores['license'] == pytest.approx(0.3, rel=0.01)


# =============================================================================
# Tests for visualize_classification
# =============================================================================

class TestVisualizeClassification:
    """Tests for classification visualization."""

    @patch("plate_classifier.cv2")
    def test_license_plate_green_border(self, mock_cv2, classifier):
        """LICENSE_PLATE gets green border."""
        # Arrange
        img = np.ones((50, 100, 3), dtype=np.uint8) * 128
        mock_cv2.copyMakeBorder.return_value = np.ones((60, 110, 3), dtype=np.uint8)
        mock_cv2.BORDER_CONSTANT = 0

        # Act
        classifier.visualize_classification(img, classifier.LICENSE_PLATE)

        # Assert
        mock_cv2.copyMakeBorder.assert_called_once()
        call_kwargs = mock_cv2.copyMakeBorder.call_args[1]
        assert call_kwargs["value"] == (0, 255, 0)  # Green

    @patch("plate_classifier.cv2")
    def test_hazard_plate_red_border(self, mock_cv2, classifier):
        """HAZARD_PLATE gets red border."""
        # Arrange
        img = np.ones((50, 100, 3), dtype=np.uint8) * 128
        mock_cv2.copyMakeBorder.return_value = np.ones((60, 110, 3), dtype=np.uint8)
        mock_cv2.BORDER_CONSTANT = 0

        # Act
        classifier.visualize_classification(img, classifier.HAZARD_PLATE)

        # Assert
        call_kwargs = mock_cv2.copyMakeBorder.call_args[1]
        assert call_kwargs["value"] == (0, 0, 255)  # Red

    @patch("plate_classifier.cv2")
    def test_unknown_gray_border(self, mock_cv2, classifier):
        """UNKNOWN gets gray border."""
        # Arrange
        img = np.ones((50, 100, 3), dtype=np.uint8) * 128
        mock_cv2.copyMakeBorder.return_value = np.ones((60, 110, 3), dtype=np.uint8)
        mock_cv2.BORDER_CONSTANT = 0

        # Act
        classifier.visualize_classification(img, classifier.UNKNOWN)

        # Assert
        call_kwargs = mock_cv2.copyMakeBorder.call_args[1]
        assert call_kwargs["value"] == (128, 128, 128)  # Gray

    @patch("plate_classifier.cv2")
    def test_save_to_file_when_path_provided(self, mock_cv2, classifier):
        """Saves to file when save_path is provided."""
        # Arrange
        img = np.ones((50, 100, 3), dtype=np.uint8) * 128
        mock_cv2.copyMakeBorder.return_value = np.ones((60, 110, 3), dtype=np.uint8)
        mock_cv2.BORDER_CONSTANT = 0

        # Act
        classifier.visualize_classification(
            img, classifier.LICENSE_PLATE, save_path="/tmp/test.jpg"
        )

        # Assert
        mock_cv2.imwrite.assert_called_once()
        call_args = mock_cv2.imwrite.call_args[0]
        assert call_args[0] == "/tmp/test.jpg"

    @patch("plate_classifier.cv2")
    def test_no_save_without_path(self, mock_cv2, classifier):
        """Does not save when save_path is None."""
        # Arrange
        img = np.ones((50, 100, 3), dtype=np.uint8) * 128
        mock_cv2.copyMakeBorder.return_value = np.ones((60, 110, 3), dtype=np.uint8)
        mock_cv2.BORDER_CONSTANT = 0

        # Act
        classifier.visualize_classification(img, classifier.LICENSE_PLATE)

        # Assert
        mock_cv2.imwrite.assert_not_called()

    @patch("plate_classifier.cv2")
    def test_returns_annotated_image(self, mock_cv2, classifier):
        """Returns the annotated image."""
        # Arrange
        img = np.ones((50, 100, 3), dtype=np.uint8) * 128
        expected_result = np.ones((60, 110, 3), dtype=np.uint8) * 200
        mock_cv2.copyMakeBorder.return_value = expected_result
        mock_cv2.BORDER_CONSTANT = 0

        # Act
        result = classifier.visualize_classification(img, classifier.LICENSE_PLATE)

        # Assert
        assert result is not None
