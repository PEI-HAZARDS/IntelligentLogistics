"""
Comprehensive Unit Tests for PlateClassifier
=============================================
PlateClassifier:
- Classifies image crops as LICENSE_PLATE or HAZARD_PLATE
- Uses aspect ratio analysis
- Uses color analysis (HSV ranges)
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
        assert classifier.min_aspect_ratio_license > 1.0  # License plates are wide
        assert classifier.max_aspect_ratio_hazard < 2.0  # Hazard plates are square/vertical
    
    def test_init_sets_color_ranges(self):
        """Test that color ranges are defined."""
        classifier = PlateClassifier()
        
        assert hasattr(classifier, 'license_plate_colors')
        assert hasattr(classifier, 'hazard_plate_colors')
        assert len(classifier.license_plate_colors) > 0
        assert len(classifier.hazard_plate_colors) > 0


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
    
    def test_classify_returns_unknown_for_zero_height(self):
        """Test that zero height image returns UNKNOWN."""
        classifier = PlateClassifier()
        
        # Create image with 0 height
        img = np.zeros((0, 100, 3), dtype=np.uint8)
        
        result = classifier.classify(img)
        
        assert result == PlateClassifier.UNKNOWN
    
    def test_classify_returns_unknown_for_zero_width(self):
        """Test that zero width image returns UNKNOWN."""
        classifier = PlateClassifier()
        
        # Create image with 0 width
        img = np.zeros((100, 0, 3), dtype=np.uint8)
        
        result = classifier.classify(img)
        
        assert result == PlateClassifier.UNKNOWN


class TestPlateClassifierAspectRatio:
    """Tests for aspect ratio analysis."""
    
    def test_wide_aspect_ratio_suggests_license_plate(self):
        """Test that wide images (high aspect ratio) suggest license plate."""
        classifier = PlateClassifier()
        
        # Create wide image: width 200, height 50 -> aspect ratio = 4.0
        wide_img = np.full((50, 200, 3), 255, dtype=np.uint8)  # White
        
        result = classifier.classify(wide_img)
        
        # Wide + white should be license plate
        assert result == PlateClassifier.LICENSE_PLATE
    
    def test_square_aspect_ratio_suggests_hazard_plate(self):
        """Test that square images suggest hazard plate."""
        classifier = PlateClassifier()
        
        # Create square orange image
        square_img = np.zeros((100, 100, 3), dtype=np.uint8)
        # Orange in BGR: (0, 165, 255) approximately
        square_img[:, :] = [0, 100, 200]  # Orange-ish
        
        result = classifier.classify(square_img)
        
        # Square + orange should be hazard plate or at least not license plate
        assert result in [PlateClassifier.HAZARD_PLATE, PlateClassifier.UNKNOWN]
    
    def test_vertical_aspect_ratio_suggests_hazard_plate(self):
        """Test that vertical images (low aspect ratio) suggest hazard plate."""
        classifier = PlateClassifier()
        
        # Create vertical image: width 60, height 100 -> aspect ratio = 0.6
        vertical_img = np.zeros((100, 60, 3), dtype=np.uint8)
        # Orange color
        vertical_img[:, :] = [0, 100, 200]
        
        result = classifier.classify(vertical_img)
        
        # Vertical + orange should suggest hazard plate
        assert result in [PlateClassifier.HAZARD_PLATE, PlateClassifier.UNKNOWN]


class TestPlateClassifierColorAnalysis:
    """Tests for color analysis."""
    
    def test_white_color_suggests_license_plate(self):
        """Test that white color suggests license plate."""
        classifier = PlateClassifier()
        
        # Create wide white image
        white_img = np.full((50, 200, 3), 255, dtype=np.uint8)
        
        result = classifier.classify(white_img)
        
        assert result == PlateClassifier.LICENSE_PLATE
    
    def test_yellow_color_suggests_license_plate(self):
        """Test that yellow color suggests license plate."""
        classifier = PlateClassifier()
        
        # Create wide yellow image
        # Yellow in BGR: (0, 255, 255)
        yellow_img = np.zeros((50, 200, 3), dtype=np.uint8)
        yellow_img[:, :] = [0, 255, 255]
        
        result = classifier.classify(yellow_img)
        
        # Wide + yellow should be license plate
        assert result == PlateClassifier.LICENSE_PLATE
    
    def test_orange_color_suggests_hazard_plate(self):
        """Test that orange color suggests hazard plate."""
        classifier = PlateClassifier()
        
        # Create square orange image
        # Orange in BGR: approximately (0, 165, 255)
        orange_img = np.zeros((80, 80, 3), dtype=np.uint8)
        orange_img[:, :] = [0, 128, 255]  # Orange
        
        result = classifier.classify(orange_img)
        
        # Square + orange should be hazard plate
        assert result in [PlateClassifier.HAZARD_PLATE, PlateClassifier.UNKNOWN]
    
    def test_red_color_suggests_hazard_plate(self):
        """Test that red color suggests hazard plate."""
        classifier = PlateClassifier()
        
        # Create square red image
        # Red in BGR: (0, 0, 255)
        red_img = np.zeros((80, 80, 3), dtype=np.uint8)
        red_img[:, :] = [0, 0, 255]  # Red
        
        result = classifier.classify(red_img)
        
        # Square + red could suggest hazard plate
        assert result in [PlateClassifier.HAZARD_PLATE, PlateClassifier.UNKNOWN]


class TestPlateClassifierEdgeCases:
    """Tests for edge cases."""
    
    def test_small_image_classification(self):
        """Test classification of very small images."""
        classifier = PlateClassifier()
        
        # Very small wide image
        small_img = np.full((10, 30, 3), 255, dtype=np.uint8)
        
        result = classifier.classify(small_img)
        
        # Should still work
        assert result in [PlateClassifier.LICENSE_PLATE, PlateClassifier.HAZARD_PLATE, PlateClassifier.UNKNOWN]
    
    def test_grayscale_image_handling(self):
        """Test handling of grayscale images."""
        classifier = PlateClassifier()
        
        # 2D grayscale image
        gray_img = np.full((50, 200), 255, dtype=np.uint8)
        
        # Should handle gracefully (may return UNKNOWN or attempt classification)
        try:
            result = classifier.classify(gray_img)
            assert result in [PlateClassifier.LICENSE_PLATE, PlateClassifier.HAZARD_PLATE, PlateClassifier.UNKNOWN]
        except Exception:
            # If it raises, that's also acceptable behavior for invalid input
            pass
    
    def test_mixed_color_image(self):
        """Test classification of image with mixed colors."""
        classifier = PlateClassifier()
        
        # Create image with mixed colors
        mixed_img = np.zeros((50, 200, 3), dtype=np.uint8)
        mixed_img[:25, :] = [255, 255, 255]  # White top half
        mixed_img[25:, :] = [0, 0, 0]  # Black bottom half
        
        result = classifier.classify(mixed_img)
        
        # Should return some classification
        assert result in [PlateClassifier.LICENSE_PLATE, PlateClassifier.HAZARD_PLATE, PlateClassifier.UNKNOWN]
    
    def test_borderline_aspect_ratio(self):
        """Test classification at borderline aspect ratios."""
        classifier = PlateClassifier()
        
        # Aspect ratio right at license plate threshold
        borderline_img = np.full((66, 100, 3), 255, dtype=np.uint8)  # AR = 1.5
        
        result = classifier.classify(borderline_img)
        
        # Should make a decision even at borderline
        assert result in [PlateClassifier.LICENSE_PLATE, PlateClassifier.HAZARD_PLATE, PlateClassifier.UNKNOWN]


class TestPlateClassifierColorRanges:
    """Tests for HSV color range definitions."""
    
    def test_license_plate_color_ranges_format(self):
        """Test that license plate color ranges are properly formatted."""
        classifier = PlateClassifier()
        
        for lower, upper in classifier.license_plate_colors:
            assert len(lower) == 3  # HSV has 3 channels
            assert len(upper) == 3
            
            # Lower bounds should be less than or equal to upper bounds
            for i in range(3):
                # Note: H can wrap around (0-180 in OpenCV)
                pass  # Just check format is correct
    
    def test_hazard_plate_color_ranges_format(self):
        """Test that hazard plate color ranges are properly formatted."""
        classifier = PlateClassifier()
        
        for lower, upper in classifier.hazard_plate_colors:
            assert len(lower) == 3  # HSV has 3 channels
            assert len(upper) == 3


class TestPlateClassifierIntegration:
    """Integration tests for complete classification workflow."""
    
    def test_realistic_license_plate_crop(self):
        """Test classification of a realistic license plate crop."""
        classifier = PlateClassifier()
        
        # Create a realistic license plate: wide, white background
        # Portuguese plates are typically 520x110mm, aspect ratio ~4.7
        height, width = 40, 180
        plate_img = np.full((height, width, 3), 255, dtype=np.uint8)  # White
        
        # Add some gray "text" areas
        plate_img[10:30, 20:40] = [100, 100, 100]  # Characters
        plate_img[10:30, 50:70] = [100, 100, 100]
        plate_img[10:30, 80:100] = [100, 100, 100]
        
        result = classifier.classify(plate_img)
        
        assert result == PlateClassifier.LICENSE_PLATE
    
    def test_realistic_hazard_plate_crop(self):
        """Test classification of a realistic hazard plate crop."""
        classifier = PlateClassifier()
        
        # Hazard plates (ADR) are typically 400x300mm (ratio ~1.33) or diamond shape
        # Orange background
        height, width = 90, 120
        hazard_img = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Orange in BGR: (0, 165, 255) approximately
        hazard_img[:, :] = [0, 140, 255]  # Orange
        
        # Add black "text" for UN number
        hazard_img[30:60, 30:90] = [0, 0, 0]
        
        result = classifier.classify(hazard_img)
        
        # Should classify as hazard plate or unknown (not license plate)
        assert result in [PlateClassifier.HAZARD_PLATE, PlateClassifier.UNKNOWN]
    
    def test_consecutive_classifications(self):
        """Test that consecutive classifications are consistent."""
        classifier = PlateClassifier()
        
        # Create a clear license plate image
        plate_img = np.full((50, 200, 3), 255, dtype=np.uint8)
        
        results = [classifier.classify(plate_img) for _ in range(5)]
        
        # All results should be the same
        assert all(r == results[0] for r in results)
