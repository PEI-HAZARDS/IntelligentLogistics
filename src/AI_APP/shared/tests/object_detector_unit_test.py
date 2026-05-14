"""
Unit tests for shared/src/object_detector.py

Tests cover:
- ObjectDetector initialization
- YOLO detection with output suppression
- Box extraction
- Object detection status

All YOLO model calls are mocked.
"""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock


# =============================================================================
# Tests for ObjectDetector
# =============================================================================

class TestObjectDetector:
    """Tests for the ObjectDetector class."""

    def test_initialization_raises_file_not_found(self):
        """Initialization should fail when model path does not exist."""
        # Arrange & Act & Assert
        with patch("AI_APP.shared.src.object_detector.os.path.isfile", return_value=False):
            from AI_APP.shared.src.object_detector import ObjectDetector

            with pytest.raises(FileNotFoundError, match="Model file not found"):
                ObjectDetector("/missing/model.pt")

    def test_initialization_wraps_yolo_load_error(self):
        """Initialization should raise RuntimeError when YOLO fails to load."""
        # Arrange & Act & Assert
        with patch("AI_APP.shared.src.object_detector.YOLO", side_effect=Exception("load failed")), \
             patch("AI_APP.shared.src.object_detector.os.path.isfile", return_value=True):
            from AI_APP.shared.src.object_detector import ObjectDetector

            with pytest.raises(RuntimeError, match="Failed to load YOLO model"):
                ObjectDetector("/path/to/model.pt")

    def test_initialization_loads_model(self):
        """Initialization loads YOLO model with given path."""
        # Arrange & Act
        with patch("AI_APP.shared.src.object_detector.YOLO") as MockYOLO, \
             patch("AI_APP.shared.src.object_detector.os.path.isfile", return_value=True):
            mock_model = MagicMock()
            MockYOLO.return_value = mock_model
            
            from AI_APP.shared.src.object_detector import ObjectDetector
            detector = ObjectDetector("/path/to/model.pt")

            # Assert
            MockYOLO.assert_called_once_with("/path/to/model.pt")
            assert detector.model_path == "/path/to/model.pt"

    def test_initialization_with_class_id(self):
        """Initialization with class_id stores it correctly."""
        # Arrange & Act
        with patch("AI_APP.shared.src.object_detector.YOLO") as MockYOLO, \
             patch("AI_APP.shared.src.object_detector.os.path.isfile", return_value=True):
            mock_model = MagicMock()
            MockYOLO.return_value = mock_model
            
            from AI_APP.shared.src.object_detector import ObjectDetector
            detector = ObjectDetector("/path/to/model.pt", class_id=5)

            # Assert
            assert detector.class_id == 5

    def test_initialization_default_class_id(self):
        """Default class_id is -1."""
        # Arrange & Act
        with patch("AI_APP.shared.src.object_detector.YOLO") as MockYOLO, \
             patch("AI_APP.shared.src.object_detector.os.path.isfile", return_value=True):
            mock_model = MagicMock()
            MockYOLO.return_value = mock_model
            
            from AI_APP.shared.src.object_detector import ObjectDetector
            detector = ObjectDetector("/path/to/model.pt")

            # Assert
            assert detector.class_id == -1

    def test_detect_with_output_suppression(self):
        """detect method suppresses output via verbose=False by default."""
        # Arrange
        with patch("AI_APP.shared.src.object_detector.YOLO") as MockYOLO, \
             patch("AI_APP.shared.src.object_detector.os.path.isfile", return_value=True):
            mock_model = MagicMock()
            mock_results = [MagicMock()]
            mock_model.return_value = mock_results
            MockYOLO.return_value = mock_model
            
            from AI_APP.shared.src.object_detector import ObjectDetector
            detector = ObjectDetector("/path/to/model.pt")
            image = np.zeros((416, 416, 3), dtype=np.uint8)

            # Act
            result = detector.detect(image, suppress_output=True)

            # Assert
            assert result == mock_results
            mock_model.assert_called_once_with(image, verbose=False)

    def test_detect_without_output_suppression(self):
        """detect method can run without output suppression."""
        # Arrange
        with patch("AI_APP.shared.src.object_detector.YOLO") as MockYOLO, \
             patch("AI_APP.shared.src.object_detector.os.path.isfile", return_value=True):
            mock_model = MagicMock()
            mock_results = [MagicMock()]
            mock_model.return_value = mock_results
            MockYOLO.return_value = mock_model
            
            from AI_APP.shared.src.object_detector import ObjectDetector
            detector = ObjectDetector("/path/to/model.pt")
            image = np.zeros((416, 416, 3), dtype=np.uint8)

            # Act
            result = detector.detect(image, suppress_output=False)

            # Assert
            assert result == mock_results

    def test_detect_raises_value_error_for_none_image(self):
        """detect should reject None image input."""
        # Arrange
        with patch("AI_APP.shared.src.object_detector.YOLO") as MockYOLO, \
             patch("AI_APP.shared.src.object_detector.os.path.isfile", return_value=True):
            mock_model = MagicMock()
            MockYOLO.return_value = mock_model

            from AI_APP.shared.src.object_detector import ObjectDetector
            detector = ObjectDetector("/path/to/model.pt")

            # Act & Assert
            with pytest.raises(ValueError, match="Cannot run detection on None image"):
                detector.detect(None)

    def test_detect_with_class_filter(self):
        """detect uses class filter when class_id >= 0."""
        # Arrange
        with patch("AI_APP.shared.src.object_detector.YOLO") as MockYOLO, \
             patch("AI_APP.shared.src.object_detector.os.path.isfile", return_value=True):
            mock_model = MagicMock()
            mock_results = [MagicMock()]
            mock_model.return_value = mock_results
            MockYOLO.return_value = mock_model
            
            from AI_APP.shared.src.object_detector import ObjectDetector
            detector = ObjectDetector("/path/to/model.pt", class_id=2)
            image = np.zeros((416, 416, 3), dtype=np.uint8)

            # Act
            result = detector.detect(image, suppress_output=False)

            # Assert
            mock_model.assert_called_once_with(image, verbose=True, classes=[2])

    def test_get_boxes_extracts_coordinates(self):
        """get_boxes extracts box coordinates from results."""
        # Arrange
        with patch("AI_APP.shared.src.object_detector.YOLO") as MockYOLO, \
             patch("AI_APP.shared.src.object_detector.os.path.isfile", return_value=True):
            mock_model = MagicMock()
            MockYOLO.return_value = mock_model
            
            from AI_APP.shared.src.object_detector import ObjectDetector
            detector = ObjectDetector("/path/to/model.pt")
            
            # Create mock box with xyxy and conf
            mock_box = MagicMock()
            mock_tensor_xyxy = MagicMock()
            mock_tensor_xyxy.tolist.return_value = [10.0, 20.0, 50.0, 60.0]
            mock_box.xyxy = MagicMock()
            mock_box.xyxy.__getitem__ = MagicMock(return_value=mock_tensor_xyxy)
            mock_box.conf = MagicMock()
            mock_box.conf.__getitem__ = MagicMock(return_value=0.95)
            
            mock_result = MagicMock()
            mock_result.boxes = [mock_box]
            results = [mock_result]

            # Act
            boxes = detector.get_boxes(results)

            # Assert
            assert len(boxes) == 1
            assert boxes[0][4] == 0.95  # Confidence

    def test_get_boxes_multiple_detections(self):
        """get_boxes handles multiple detections."""
        # Arrange
        with patch("AI_APP.shared.src.object_detector.YOLO") as MockYOLO, \
             patch("AI_APP.shared.src.object_detector.os.path.isfile", return_value=True):
            mock_model = MagicMock()
            MockYOLO.return_value = mock_model
            
            from AI_APP.shared.src.object_detector import ObjectDetector
            detector = ObjectDetector("/path/to/model.pt")
            
            # Create multiple mock boxes
            mock_boxes = []
            for i, conf in enumerate([0.9, 0.85, 0.75]):
                mock_box = MagicMock()
                mock_tensor_xyxy = MagicMock()
                mock_tensor_xyxy.tolist.return_value = [i*10.0, i*10.0, i*10.0+40.0, i*10.0+30.0]
                mock_box.xyxy = MagicMock()
                mock_box.xyxy.__getitem__ = MagicMock(return_value=mock_tensor_xyxy)
                mock_tensor_conf = MagicMock()
                mock_tensor_conf.item.return_value = conf
                mock_box.conf = MagicMock()
                mock_box.conf.__getitem__ = MagicMock(return_value=mock_tensor_conf)
                mock_boxes.append(mock_box)
            
            mock_result = MagicMock()
            mock_result.boxes = mock_boxes
            results = [mock_result]

            # Act
            boxes = detector.get_boxes(results)

            # Assert
            assert len(boxes) == 3

    def test_object_found_true_when_boxes_exist(self):
        """object_found returns True when boxes are detected."""
        # Arrange
        with patch("AI_APP.shared.src.object_detector.YOLO") as MockYOLO, \
             patch("AI_APP.shared.src.object_detector.os.path.isfile", return_value=True):
            mock_model = MagicMock()
            MockYOLO.return_value = mock_model
            
            from AI_APP.shared.src.object_detector import ObjectDetector
            detector = ObjectDetector("/path/to/model.pt")
            
            mock_result = MagicMock()
            mock_result.boxes = [MagicMock(), MagicMock()]  # 2 boxes
            results = [mock_result]

            # Act
            found = detector.object_found(results)

            # Assert
            assert found is True

    def test_object_found_false_when_no_boxes(self):
        """object_found returns False when no boxes detected."""
        # Arrange
        with patch("AI_APP.shared.src.object_detector.YOLO") as MockYOLO, \
             patch("AI_APP.shared.src.object_detector.os.path.isfile", return_value=True):
            mock_model = MagicMock()
            MockYOLO.return_value = mock_model
            
            from AI_APP.shared.src.object_detector import ObjectDetector
            detector = ObjectDetector("/path/to/model.pt")
            
            mock_result = MagicMock()
            mock_result.boxes = []  # No boxes
            results = [mock_result]

            # Act
            found = detector.object_found(results)

            # Assert
            assert found is False

    def test_close_calls_model_close(self):
        """close method closes the model."""
        # Arrange
        with patch("AI_APP.shared.src.object_detector.YOLO") as MockYOLO, \
             patch("AI_APP.shared.src.object_detector.os.path.isfile", return_value=True):
            mock_model = MagicMock()
            MockYOLO.return_value = mock_model
            
            from AI_APP.shared.src.object_detector import ObjectDetector
            detector = ObjectDetector("/path/to/model.pt")

            # Act
            detector.close()

            # Assert
            mock_model.close.assert_called_once()
