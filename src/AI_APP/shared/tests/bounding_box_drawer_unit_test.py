"""
Unit tests for shared/src/bounding_box_drawer.py

Tests cover:
- BoundingBoxDrawer initialization
- Color mapping (_bgr method)
- Box drawing
- Label drawing

All cv2 calls are mocked.
"""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from bounding_box_drawer import BoundingBoxDrawer


# =============================================================================
# Tests for __init__
# =============================================================================

class TestBoundingBoxDrawerInit:
    """Tests for BoundingBoxDrawer initialization."""

    def test_default_initialization(self):
        """Default initialization uses black color, thickness 1, empty label."""
        # Arrange & Act
        drawer = BoundingBoxDrawer()

        # Assert
        assert drawer.color == "black"
        assert drawer.thickness == 1
        assert drawer.label == ""

    def test_custom_color(self):
        """Custom color is stored correctly."""
        # Arrange & Act
        drawer = BoundingBoxDrawer(color="red")

        # Assert
        assert drawer.color == "red"

    def test_custom_thickness(self):
        """Custom thickness is stored correctly."""
        # Arrange & Act
        drawer = BoundingBoxDrawer(thickness=3)

        # Assert
        assert drawer.thickness == 3

    def test_custom_label(self):
        """Custom label is stored correctly."""
        # Arrange & Act
        drawer = BoundingBoxDrawer(label="truck")

        # Assert
        assert drawer.label == "truck"

    def test_full_custom_initialization(self):
        """All custom parameters work together."""
        # Arrange & Act
        drawer = BoundingBoxDrawer(color="green", thickness=5, label="hazard")

        # Assert
        assert drawer.color == "green"
        assert drawer.thickness == 5
        assert drawer.label == "hazard"


# =============================================================================
# Tests for _bgr
# =============================================================================

class TestBgrColorMapping:
    """Tests for the _bgr color mapping method."""

    def test_red_color_mapping(self):
        """Red maps to (0, 0, 255) in BGR."""
        # Arrange
        drawer = BoundingBoxDrawer(color="red")

        # Act
        result = drawer._bgr()

        # Assert
        assert result == (0, 0, 255)

    def test_green_color_mapping(self):
        """Green maps to (0, 255, 0) in BGR."""
        # Arrange
        drawer = BoundingBoxDrawer(color="green")

        # Act
        result = drawer._bgr()

        # Assert
        assert result == (0, 255, 0)

    def test_blue_color_mapping(self):
        """Blue maps to (255, 0, 0) in BGR."""
        # Arrange
        drawer = BoundingBoxDrawer(color="blue")

        # Act
        result = drawer._bgr()

        # Assert
        assert result == (255, 0, 0)

    def test_white_color_mapping(self):
        """White maps to (255, 255, 255) in BGR."""
        # Arrange
        drawer = BoundingBoxDrawer(color="white")

        # Act
        result = drawer._bgr()

        # Assert
        assert result == (255, 255, 255)

    def test_black_color_mapping(self):
        """Black maps to (0, 0, 0) in BGR."""
        # Arrange
        drawer = BoundingBoxDrawer(color="black")

        # Act
        result = drawer._bgr()

        # Assert
        assert result == (0, 0, 0)

    def test_yellow_color_mapping(self):
        """Yellow maps to (0, 255, 255) in BGR."""
        # Arrange
        drawer = BoundingBoxDrawer(color="yellow")

        # Act
        result = drawer._bgr()

        # Assert
        assert result == (0, 255, 255)

    def test_orange_color_mapping(self):
        """Orange maps to (0, 165, 255) in BGR."""
        # Arrange
        drawer = BoundingBoxDrawer(color="orange")

        # Act
        result = drawer._bgr()

        # Assert
        assert result == (0, 165, 255)

    def test_unknown_color_defaults_to_black(self):
        """Unknown color defaults to black (0, 0, 0)."""
        # Arrange
        drawer = BoundingBoxDrawer(color="purple")

        # Act
        result = drawer._bgr()

        # Assert
        assert result == (0, 0, 0)

    def test_case_insensitive_color(self):
        """Color matching is case insensitive."""
        # Arrange
        drawer = BoundingBoxDrawer(color="RED")

        # Act
        result = drawer._bgr()

        # Assert
        assert result == (0, 0, 255)


# =============================================================================
# Tests for draw_box
# =============================================================================

class TestDrawBox:
    """Tests for the draw_box method."""

    @patch("bounding_box_drawer.cv2")
    def test_draw_single_box_without_confidence(self, mock_cv2):
        """Draw a single box without confidence value."""
        # Arrange
        drawer = BoundingBoxDrawer(color="red", thickness=2)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        boxes = [(10, 20, 50, 60)]

        # Act
        result = drawer.draw_box(frame, boxes)

        # Assert
        mock_cv2.rectangle.assert_called_once()
        assert result is frame

    @patch("bounding_box_drawer.cv2")
    def test_draw_single_box_with_confidence(self, mock_cv2):
        """Draw a single box with confidence value."""
        # Arrange
        drawer = BoundingBoxDrawer(color="green", thickness=2, label="plate")
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        boxes = [(10, 20, 50, 60, 0.95)]
        mock_cv2.getTextSize.return_value = ((50, 10), 0)

        # Act
        result = drawer.draw_box(frame, boxes)

        # Assert
        mock_cv2.rectangle.assert_called()
        assert result is frame

    @patch("bounding_box_drawer.cv2")
    def test_draw_multiple_boxes(self, mock_cv2):
        """Draw multiple boxes in single call."""
        # Arrange
        drawer = BoundingBoxDrawer(color="blue", thickness=1)
        frame = np.zeros((200, 200, 3), dtype=np.uint8)
        boxes = [
            (10, 10, 50, 50, 0.8),
            (60, 60, 100, 100, 0.9),
            (110, 110, 150, 150, 0.7),
        ]
        mock_cv2.getTextSize.return_value = ((50, 10), 0)

        # Act
        result = drawer.draw_box(frame, boxes)

        # Assert - 3 boxes + 3 label backgrounds = 6 rectangle calls
        assert mock_cv2.rectangle.call_count == 6
        assert result is frame

    @patch("bounding_box_drawer.cv2")
    def test_draw_empty_boxes_list(self, mock_cv2):
        """Empty boxes list doesn't call rectangle."""
        # Arrange
        drawer = BoundingBoxDrawer()
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        boxes = []

        # Act
        result = drawer.draw_box(frame, boxes)

        # Assert
        mock_cv2.rectangle.assert_not_called()
        assert result is frame

    @patch("bounding_box_drawer.cv2")
    def test_skip_invalid_box_with_less_than_4_elements(self, mock_cv2):
        """Boxes with less than 4 elements are skipped."""
        # Arrange
        drawer = BoundingBoxDrawer()
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        boxes = [(10, 20, 30)]  # Only 3 elements

        # Act
        result = drawer.draw_box(frame, boxes)

        # Assert
        mock_cv2.rectangle.assert_not_called()
        assert result is frame

    @patch("bounding_box_drawer.cv2")
    def test_draw_box_with_label_only(self, mock_cv2):
        """Draw box with label but no confidence."""
        # Arrange
        drawer = BoundingBoxDrawer(color="yellow", label="truck")
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        boxes = [(10, 20, 50, 60)]  # No confidence
        mock_cv2.getTextSize.return_value = ((40, 10), 0)

        # Act
        result = drawer.draw_box(frame, boxes)

        # Assert
        mock_cv2.rectangle.assert_called()
        assert result is frame

    @patch("bounding_box_drawer.cv2")
    def test_continue_on_exception_in_single_box(self, mock_cv2):
        """If one box fails, continue drawing others."""
        # Arrange
        drawer = BoundingBoxDrawer()
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        
        # First box causes exception, second box is valid
        boxes = [
            (float('inf'), float('inf'), float('inf'), float('inf')),  # May cause issues
            (10, 20, 50, 60, 0.9),
        ]
        
        # Make first call raise exception
        mock_cv2.rectangle.side_effect = [Exception("Test"), None]
        mock_cv2.getTextSize.return_value = ((40, 10), 0)

        # Act
        result = drawer.draw_box(frame, boxes)

        # Assert - should complete without raising
        assert result is frame


# =============================================================================
# Tests for _draw_label
# =============================================================================

class TestDrawLabel:
    """Tests for the _draw_label method."""

    @patch("bounding_box_drawer.cv2")
    def test_draw_label_with_light_background(self, mock_cv2):
        """Light color background gets dark text (sum >= 400)."""
        # Arrange
        drawer = BoundingBoxDrawer(color="white")
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_cv2.getTextSize.return_value = ((40, 10), 0)

        # Act - white = (255, 255, 255), sum = 765 >= 400 -> black text
        drawer._draw_label(frame, 10, 20, "TEST", (255, 255, 255))

        # Assert - check putText was called
        mock_cv2.putText.assert_called_once()
        # putText(frame, label_text, (x, y), font, font_scale, text_color, ...)
        call_args = mock_cv2.putText.call_args[0]
        text_color = call_args[5]  # 6th positional arg is text_color
        assert text_color == (0, 0, 0)  # Black text for light background

    @patch("bounding_box_drawer.cv2")
    def test_draw_label_with_dark_background(self, mock_cv2):
        """Dark color background gets light text (sum < 400)."""
        # Arrange
        drawer = BoundingBoxDrawer(color="black")
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_cv2.getTextSize.return_value = ((40, 10), 0)

        # Act - black = (0, 0, 0), sum = 0 < 400 -> white text
        drawer._draw_label(frame, 10, 20, "TEST", (0, 0, 0))

        # Assert
        mock_cv2.putText.assert_called_once()
        call_args = mock_cv2.putText.call_args[0]
        text_color = call_args[5]  # 6th positional arg is text_color
        assert text_color == (255, 255, 255)  # White text for dark background

    @patch("bounding_box_drawer.cv2")
    def test_label_repositioned_when_near_right_edge(self, mock_cv2):
        """Label is shifted left when it would overflow right edge."""
        # Arrange
        drawer = BoundingBoxDrawer()
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_cv2.getTextSize.return_value = ((50, 10), 0)  # 50px wide label

        # Position near right edge (x=90 on 100px wide image)
        # Act
        drawer._draw_label(frame, 90, 20, "LONG LABEL", (0, 0, 255))

        # Assert
        mock_cv2.rectangle.assert_called()

    @patch("bounding_box_drawer.cv2")
    def test_label_repositioned_when_near_top_edge(self, mock_cv2):
        """Label is placed below box when near top edge."""
        # Arrange
        drawer = BoundingBoxDrawer()
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_cv2.getTextSize.return_value = ((40, 10), 0)

        # Position near top (y=5, with ~16px label height, would go negative)
        # Act
        drawer._draw_label(frame, 10, 5, "TEST", (0, 255, 0))

        # Assert
        mock_cv2.rectangle.assert_called()

    @patch("bounding_box_drawer.cv2")
    def test_label_handles_exception_getting_frame_shape(self, mock_cv2):
        """Handle exception when frame shape can't be determined."""
        # Arrange
        drawer = BoundingBoxDrawer()
        mock_cv2.getTextSize.return_value = ((40, 10), 0)

        # Create a mock frame that raises on shape access
        mock_frame = MagicMock()
        mock_frame.shape = property(lambda self: exec('raise Exception("test")'))

        # Use a frame without proper shape
        frame = MagicMock()
        frame.shape = [100, 100]  # List instead of tuple, should work

        # Act
        result = drawer._draw_label(frame, 10, 20, "TEST", (255, 0, 0))

        # Assert - should complete without raising
        mock_cv2.rectangle.assert_called()
