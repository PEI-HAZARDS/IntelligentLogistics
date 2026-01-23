"""
Comprehensive Unit Tests for PlateClassifier (Agent C copy)
===========================================================
Same tests as AgentB but for the AgentC module location.
"""

import sys
from pathlib import Path
import numpy as np
import cv2
import pytest

# Setup path for imports
TESTS_DIR = Path(__file__).resolve().parent
MICROSERVICE_ROOT = TESTS_DIR.parent
GLOBAL_SRC = MICROSERVICE_ROOT.parent

sys.path.insert(0, str(MICROSERVICE_ROOT / "src"))
sys.path.insert(0, str(GLOBAL_SRC))

from PlateClassifier import PlateClassifier


class TestPlateClassifierInitialization:
    """Tests for PlateClassifier initialization."""
    
    def test_init_sets_class_constants(self):
        """Test that class constants are defined."""
        assert PlateClassifier.LICENSE_PLATE == "license_plate"
        assert PlateClassifier.HAZARD_PLATE == "hazard_plate"
        assert PlateClassifier.UNKNOWN == "unknown"
    
    def test_init_sets_aspect_ratio_thresholds(self):
        """Test that aspect ratio thresholds are set."""
        classifier = PlateClassifier()
        
        assert hasattr(classifier, 'min_aspect_ratio_license')
        assert hasattr(classifier, 'max_aspect_ratio_hazard')
        assert classifier.min_aspect_ratio_license > 1.0
        assert classifier.max_aspect_ratio_hazard < 2.0


class TestPlateClassifierInputValidation:
    """Tests for input validation."""
    
    def test_classify_returns_unknown_for_none(self):
        """Test that None input returns UNKNOWN."""
        classifier = PlateClassifier()
        
        result = classifier.classify(None)
        
        assert result == PlateClassifier.UNKNOWN
    
    def test_classify_returns_unknown_for_empty_array(self):
        """Test that empty array returns UNKNOWN."""
        classifier = PlateClassifier()
        
        result = classifier.classify(np.array([]))
        
        assert result == PlateClassifier.UNKNOWN
    
    def test_classify_returns_unknown_for_zero_dimensions(self):
        """Test that zero dimension images return UNKNOWN."""
        classifier = PlateClassifier()
        
        # Zero height
        img1 = np.zeros((0, 100, 3), dtype=np.uint8)
        result1 = classifier.classify(img1)
        
        # Zero width
        img2 = np.zeros((100, 0, 3), dtype=np.uint8)
        result2 = classifier.classify(img2)
        
        assert result1 == PlateClassifier.UNKNOWN
        assert result2 == PlateClassifier.UNKNOWN


class TestPlateClassifierAspectRatio:
    """Tests for aspect ratio analysis."""
    
    def test_wide_image_classified_as_license_plate(self):
        """Test that wide white images are classified as license plates."""
        classifier = PlateClassifier()
        
        # Wide white image (typical license plate)
        wide_img = np.full((50, 200, 3), 255, dtype=np.uint8)
        
        result = classifier.classify(wide_img)
        
        assert result == PlateClassifier.LICENSE_PLATE
    
    def test_square_orange_image_classification(self):
        """Test that square orange images suggest hazard plate."""
        classifier = PlateClassifier()
        
        # Square orange image (typical hazard plate)
        square_img = np.zeros((100, 100, 3), dtype=np.uint8)
        square_img[:, :] = [0, 100, 200]  # Orange-ish BGR
        
        result = classifier.classify(square_img)
        
        assert result in [PlateClassifier.HAZARD_PLATE, PlateClassifier.UNKNOWN]


class TestPlateClassifierColorAnalysis:
    """Tests for color analysis."""
    
    def test_white_wide_image_is_license_plate(self):
        """Test white wide images are license plates."""
        classifier = PlateClassifier()
        
        white_img = np.full((50, 200, 3), 255, dtype=np.uint8)
        
        result = classifier.classify(white_img)
        
        assert result == PlateClassifier.LICENSE_PLATE
    
    def test_yellow_wide_image_is_license_plate(self):
        """Test yellow wide images are license plates."""
        classifier = PlateClassifier()
        
        yellow_img = np.zeros((50, 200, 3), dtype=np.uint8)
        yellow_img[:, :] = [0, 255, 255]  # Yellow BGR
        
        result = classifier.classify(yellow_img)
        
        assert result == PlateClassifier.LICENSE_PLATE


class TestPlateClassifierEdgeCases:
    """Tests for edge cases."""
    
    def test_small_image_classification(self):
        """Test classification works for small images."""
        classifier = PlateClassifier()
        
        small_img = np.full((10, 30, 3), 255, dtype=np.uint8)
        
        result = classifier.classify(small_img)
        
        assert result in [PlateClassifier.LICENSE_PLATE, PlateClassifier.HAZARD_PLATE, PlateClassifier.UNKNOWN]
    
    def test_classification_is_deterministic(self):
        """Test that same input produces same output."""
        classifier = PlateClassifier()
        
        img = np.full((50, 200, 3), 255, dtype=np.uint8)
        
        results = [classifier.classify(img.copy()) for _ in range(3)]
        
        assert all(r == results[0] for r in results)


class TestPlateClassifierIntegration:
    """Integration tests."""
    
    def test_realistic_license_plate(self):
        """Test realistic license plate classification."""
        classifier = PlateClassifier()
        
        # Create realistic license plate crop
        plate_img = np.full((40, 180, 3), 255, dtype=np.uint8)
        
        result = classifier.classify(plate_img)
        
        assert result == PlateClassifier.LICENSE_PLATE
    
    def test_realistic_hazard_plate(self):
        """Test realistic hazard plate classification."""
        classifier = PlateClassifier()
        
        # Create realistic hazard plate crop
        hazard_img = np.zeros((90, 120, 3), dtype=np.uint8)
        hazard_img[:, :] = [0, 140, 255]  # Orange
        
        result = classifier.classify(hazard_img)
        
        assert result in [PlateClassifier.HAZARD_PLATE, PlateClassifier.UNKNOWN]
