"""
Unit tests for shared/src/paddle_ocr.py

Tests cover:
- OCR initialization
- Image conversion (_to_cv_image)
- Image preprocessing (_resize_and_pad, _preprocess_plate)
- Text filtering
- Result parsing (dict and list formats)
- Full text extraction pipeline

All PaddleOCR calls are mocked.
"""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from PIL import Image


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_cv_image():
    """Create a sample OpenCV image (BGR numpy array)."""
    return np.random.randint(0, 255, (100, 200, 3), dtype=np.uint8)


@pytest.fixture
def small_image():
    """Create a too-small image for OCR."""
    return np.random.randint(0, 255, (5, 10, 3), dtype=np.uint8)


# =============================================================================
# Tests for OCR initialization
# =============================================================================

class TestOCRInit:
    """Tests for OCR class initialization."""

    def test_initialization_creates_paddle_ocr(self):
        """Initialization creates PaddleOCR with correct settings."""
        # Arrange & Act
        with patch("paddle_ocr.PaddleOCR") as MockPaddleOCR:
            mock_ocr = MagicMock()
            MockPaddleOCR.return_value = mock_ocr
            
            from paddle_ocr import OCR
            ocr = OCR()

            # Assert
            MockPaddleOCR.assert_called_once()
            call_kwargs = MockPaddleOCR.call_args[1]
            assert call_kwargs["use_angle_cls"] is True
            assert call_kwargs["lang"] == "en"


# =============================================================================
# Tests for _to_cv_image
# =============================================================================

class TestToCvImage:
    """Tests for image format conversion."""

    def test_string_path_reads_image(self, sample_cv_image):
        """String path triggers cv2.imread."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            with patch("paddle_ocr.cv2") as mock_cv2:
                mock_cv2.imread.return_value = sample_cv_image
                
                from paddle_ocr import OCR
                ocr = OCR()

                # Act
                result = ocr._to_cv_image("/path/to/image.jpg")

                # Assert
                mock_cv2.imread.assert_called_once_with("/path/to/image.jpg")
                assert np.array_equal(result, sample_cv_image)

    def test_numpy_array_returns_as_is(self, sample_cv_image):
        """Numpy array is returned unchanged."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            from paddle_ocr import OCR
            ocr = OCR()

            # Act
            result = ocr._to_cv_image(sample_cv_image)

            # Assert
            assert np.array_equal(result, sample_cv_image)

    def test_pil_image_rgb_converted_to_bgr(self):
        """PIL RGB image is converted to BGR."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            with patch("paddle_ocr.cv2") as mock_cv2:
                mock_cv2.COLOR_RGB2BGR = 4  # Standard constant
                mock_cv2.cvtColor.return_value = np.zeros((50, 50, 3), dtype=np.uint8)
                
                from paddle_ocr import OCR
                ocr = OCR()
                pil_image = Image.fromarray(np.zeros((50, 50, 3), dtype=np.uint8))

                # Act
                result = ocr._to_cv_image(pil_image)

                # Assert
                mock_cv2.cvtColor.assert_called()

    def test_pil_grayscale_image(self):
        """PIL grayscale image is handled correctly."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            from paddle_ocr import OCR
            ocr = OCR()
            pil_image = Image.fromarray(np.zeros((50, 50), dtype=np.uint8))

            # Act
            result = ocr._to_cv_image(pil_image)

            # Assert
            assert result is not None

    def test_unsupported_type_returns_none(self):
        """Unsupported type returns None."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            from paddle_ocr import OCR
            ocr = OCR()

            # Act
            result = ocr._to_cv_image(12345)  # Integer, not an image

            # Assert
            assert result is None


# =============================================================================
# Tests for _resize_and_pad
# =============================================================================

class TestResizeAndPad:
    """Tests for image resizing and padding."""

    def test_resize_to_target_height(self, sample_cv_image):
        """Image is resized to target height with aspect ratio maintained."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            with patch("paddle_ocr.cv2") as mock_cv2:
                mock_cv2.INTER_LANCZOS4 = 4
                mock_cv2.BORDER_REPLICATE = 1
                mock_cv2.resize.return_value = np.zeros((48, 96, 3), dtype=np.uint8)
                mock_cv2.copyMakeBorder.return_value = np.zeros((68, 116, 3), dtype=np.uint8)
                
                from paddle_ocr import OCR
                ocr = OCR()

                # Act
                result = ocr._resize_and_pad(sample_cv_image, target_height=48)

                # Assert
                mock_cv2.resize.assert_called_once()
                mock_cv2.copyMakeBorder.assert_called_once()

    def test_adds_padding_around_image(self, sample_cv_image):
        """Padding is added around the image."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            with patch("paddle_ocr.cv2") as mock_cv2:
                mock_cv2.INTER_LANCZOS4 = 4
                mock_cv2.BORDER_REPLICATE = 1
                mock_cv2.resize.return_value = np.zeros((48, 96, 3), dtype=np.uint8)
                mock_cv2.copyMakeBorder.return_value = np.zeros((68, 116, 3), dtype=np.uint8)
                
                from paddle_ocr import OCR
                ocr = OCR()

                # Act
                result = ocr._resize_and_pad(sample_cv_image, target_height=48)

                # Assert - copyMakeBorder should be called (padding added)
                mock_cv2.copyMakeBorder.assert_called_once()
                # Verify some padding args were passed
                call = mock_cv2.copyMakeBorder.call_args
                assert call is not None


# =============================================================================
# Tests for _preprocess_plate
# =============================================================================

class TestPreprocessPlate:
    """Tests for license plate preprocessing."""

    def test_raises_on_none_image(self):
        """Raises ValueError for None image."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            from paddle_ocr import OCR
            ocr = OCR()

            # Act & Assert
            with pytest.raises(ValueError, match="Could not convert"):
                ocr._preprocess_plate(None)

    def test_raises_on_too_small_image(self, small_image):
        """Raises ValueError for too small image."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            from paddle_ocr import OCR
            ocr = OCR()

            # Act & Assert
            with pytest.raises(ValueError, match="Image too small"):
                ocr._preprocess_plate(small_image)

    def test_processes_valid_image(self, sample_cv_image):
        """Processes valid image through resize, grayscale, and back to BGR."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            with patch("paddle_ocr.cv2") as mock_cv2:
                mock_cv2.INTER_LANCZOS4 = 4
                mock_cv2.BORDER_REPLICATE = 1
                mock_cv2.COLOR_BGR2GRAY = 6
                mock_cv2.COLOR_GRAY2BGR = 8
                mock_cv2.resize.return_value = np.zeros((64, 128, 3), dtype=np.uint8)
                mock_cv2.copyMakeBorder.return_value = np.zeros((84, 148, 3), dtype=np.uint8)
                mock_cv2.cvtColor.return_value = np.zeros((84, 148), dtype=np.uint8)
                
                from paddle_ocr import OCR
                ocr = OCR()

                # Act
                result = ocr._preprocess_plate(sample_cv_image)

                # Assert
                # Should convert to grayscale then back to BGR
                assert mock_cv2.cvtColor.call_count == 2


# =============================================================================
# Tests for _filter_text
# =============================================================================

class TestFilterText:
    """Tests for text filtering."""

    def test_empty_string_returns_empty(self):
        """Empty string returns empty."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            from paddle_ocr import OCR
            ocr = OCR()

            # Act
            result = ocr._filter_text("")

            # Assert
            assert result == ""

    def test_none_returns_empty(self):
        """None returns empty string."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            from paddle_ocr import OCR
            ocr = OCR()

            # Act
            result = ocr._filter_text(None)

            # Assert
            assert result == ""

    def test_uppercase_conversion(self):
        """Lowercase is converted to uppercase."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            from paddle_ocr import OCR
            ocr = OCR()

            # Act
            result = ocr._filter_text("abc123")

            # Assert
            assert result == "ABC123"

    def test_removes_special_characters(self):
        """Special characters are removed."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            from paddle_ocr import OCR
            ocr = OCR()

            # Act
            result = ocr._filter_text("AB@#$%C123!")

            # Assert
            assert result == "ABC123"

    def test_keeps_dash(self):
        """Dashes are kept."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            from paddle_ocr import OCR
            ocr = OCR()

            # Act
            result = ocr._filter_text("AB-12-CD")

            # Assert
            assert result == "AB-12-CD"

    def test_strips_whitespace(self):
        """Result is stripped of whitespace."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            from paddle_ocr import OCR
            ocr = OCR()

            # Act
            result = ocr._filter_text("  ABC123  ")

            # Assert
            assert result == "ABC123"


# =============================================================================
# Tests for result parsing
# =============================================================================

class TestParseResult:
    """Tests for parsing PaddleOCR results."""

    def test_empty_result_returns_empty(self):
        """Empty result returns empty text and 0 confidence."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            from paddle_ocr import OCR
            ocr = OCR()

            # Act
            text, conf = ocr._parse_result([])

            # Assert
            assert text == ""
            assert conf == 0.0

    def test_none_result_returns_empty(self):
        """None result returns empty text and 0 confidence."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            from paddle_ocr import OCR
            ocr = OCR()

            # Act
            text, conf = ocr._parse_result(None)

            # Assert
            assert text == ""
            assert conf == 0.0

    def test_parses_dict_format_with_rec_texts(self):
        """Parses dictionary format with rec_texts and rec_scores."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            from paddle_ocr import OCR
            ocr = OCR()
            
            result = [{"rec_texts": ["ABC", "123"], "rec_scores": [0.95, 0.92]}]

            # Act
            text, conf = ocr._parse_result(result)

            # Assert
            assert "ABC" in text
            assert "123" in text
            assert conf > 0

    def test_parses_dict_format_with_text_score(self):
        """Parses dictionary format with text and score keys."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            from paddle_ocr import OCR
            ocr = OCR()
            
            result = [{"text": "ABC123", "score": 0.95}]

            # Act
            text, conf = ocr._parse_result(result)

            # Assert
            assert text == "ABC123"
            assert conf == 0.95

    def test_parses_list_format(self):
        """Parses list/tuple format (old style)."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            from paddle_ocr import OCR
            ocr = OCR()
            
            # Old format: [[[box_coords], (text, conf)], ...]
            result = [
                [[[0, 0], [100, 0], [100, 30], [0, 30]], ("ABC123", 0.95)]
            ]

            # Act
            text, conf = ocr._parse_result(result)

            # Assert
            assert text == "ABC123"
            assert conf == 0.95

    def test_handles_parse_exception(self):
        """Handles exceptions during parsing gracefully."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            from paddle_ocr import OCR
            ocr = OCR()
            
            # Malformed result that might cause issues
            result = [{"unexpected": "format"}]

            # Act
            text, conf = ocr._parse_result(result)

            # Assert - should return empty rather than raise
            assert text == ""
            assert conf == 0.0


# =============================================================================
# Tests for _extract_text
# =============================================================================

class TestExtractText:
    """Tests for the main text extraction method."""

    def test_returns_empty_for_none_image(self):
        """Returns empty for None image."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            from paddle_ocr import OCR
            ocr = OCR()

            # Act
            text, conf = ocr._extract_text(None)

            # Assert
            assert text == ""
            assert conf == 0.0

    def test_successful_extraction(self, sample_cv_image):
        """Successfully extracts text from image."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR") as MockPaddleOCR:
            with patch("paddle_ocr.cv2") as mock_cv2:
                mock_ocr = MagicMock()
                mock_ocr.predict.return_value = [{"rec_texts": ["ABC123"], "rec_scores": [0.95]}]
                MockPaddleOCR.return_value = mock_ocr
                
                # Set up cv2 mocks
                mock_cv2.INTER_LANCZOS4 = 4
                mock_cv2.BORDER_REPLICATE = 1
                mock_cv2.COLOR_BGR2GRAY = 6
                mock_cv2.COLOR_GRAY2BGR = 8
                mock_cv2.resize.return_value = np.zeros((64, 128, 3), dtype=np.uint8)
                mock_cv2.copyMakeBorder.return_value = np.zeros((84, 148, 3), dtype=np.uint8)
                mock_cv2.cvtColor.return_value = np.zeros((84, 148), dtype=np.uint8)
                
                from paddle_ocr import OCR
                ocr = OCR()

                # Act
                text, conf = ocr._extract_text(sample_cv_image)

                # Assert
                assert text == "ABC123"
                assert conf == 0.95

    def test_handles_preprocessing_error(self, small_image):
        """Handles preprocessing errors by returning empty."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            from paddle_ocr import OCR
            ocr = OCR()

            # Act - small image should fail preprocessing
            text, conf = ocr._extract_text(small_image)

            # Assert
            assert text == ""
            assert conf == 0.0


# =============================================================================
# Tests for helper parsing methods
# =============================================================================

class TestParseDictItem:
    """Tests for _parse_dict_item helper."""

    def test_extracts_rec_texts_format(self):
        """Extracts rec_texts and rec_scores."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            from paddle_ocr import OCR
            ocr = OCR()
            
            texts = []
            confidences = []
            item = {"rec_texts": ["A", "B"], "rec_scores": [0.9, 0.8]}

            # Act
            ocr._parse_dict_item(item, texts, confidences)

            # Assert
            assert texts == ["A", "B"]
            assert confidences == [0.9, 0.8]

    def test_extracts_text_score_format(self):
        """Extracts text and score keys."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            from paddle_ocr import OCR
            ocr = OCR()
            
            texts = []
            confidences = []
            item = {"text": "ABC", "score": 0.95}

            # Act
            ocr._parse_dict_item(item, texts, confidences)

            # Assert
            assert texts == ["ABC"]
            assert confidences == [0.95]


class TestParseListItem:
    """Tests for _parse_list_item helper."""

    def test_extracts_from_tuple_format(self):
        """Extracts text and confidence from tuple format."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            from paddle_ocr import OCR
            ocr = OCR()
            
            texts = []
            confidences = []
            item = [[[0, 0], [100, 0]], ("TEXT", 0.92)]

            # Act
            ocr._parse_list_item(item, texts, confidences)

            # Assert
            assert texts == ["TEXT"]
            assert confidences == [0.92]

    def test_skips_item_with_less_than_2_elements(self):
        """Skips items with less than 2 elements."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            from paddle_ocr import OCR
            ocr = OCR()
            
            texts = []
            confidences = []
            item = [[[0, 0]]]  # Only 1 element

            # Act
            ocr._parse_list_item(item, texts, confidences)

            # Assert
            assert texts == []
            assert confidences == []

    def test_handles_string_text_data(self):
        """Handles string text data with default confidence."""
        # Arrange
        with patch("paddle_ocr.PaddleOCR"):
            from paddle_ocr import OCR
            ocr = OCR()
            
            texts = []
            confidences = []
            item = [[[0, 0], [100, 0]], "JUST_TEXT"]

            # Act
            ocr._parse_list_item(item, texts, confidences)

            # Assert
            assert texts == ["JUST_TEXT"]
            assert confidences == [0.5]  # Default confidence
