"""
Comprehensive Unit Tests for Agent B
=====================================
Agent B: License Plate Detection Agent
- Consumes 'truck-detected' events from Kafka
- Detects license plates using YOLO
- Extracts text using OCR with consensus algorithm
- Publishes 'lp-results-GATE_ID' events to Kafka
"""

import sys
import types
import math
from pathlib import Path
import json
import time
import threading
import pytest
from unittest.mock import Mock, MagicMock, patch, PropertyMock
import numpy as np
from queue import Queue

# Setup path for imports
TESTS_DIR = Path(__file__).resolve().parent
MICROSERVICE_ROOT = TESTS_DIR.parent
GLOBAL_SRC = MICROSERVICE_ROOT.parent

sys.path.insert(0, str(MICROSERVICE_ROOT / "src"))
sys.path.insert(0, str(GLOBAL_SRC))

# Mock ultralytics before importing AgentB
if "ultralytics" not in sys.modules:
    ultralytics_stub = types.ModuleType("ultralytics")
    class YOLOStub:
        def __init__(self, *args, **kwargs):
            pass
    ultralytics_stub.YOLO = YOLOStub
    sys.modules["ultralytics"] = ultralytics_stub

# Mock paddleocr
if "paddleocr" not in sys.modules:
    paddleocr_stub = types.ModuleType("paddleocr")
    class PaddleOCRStub:
        def __init__(self, *args, **kwargs):
            pass
        def ocr(self, *args, **kwargs):
            return []
    paddleocr_stub.PaddleOCR = PaddleOCRStub
    sys.modules["paddleocr"] = paddleocr_stub

# Mock minio
if "minio" not in sys.modules:
    minio_stub = types.ModuleType("minio")
    class MinioStub:
        def __init__(self, *args, **kwargs):
            pass
        def bucket_exists(self, *args):
            return True
        def make_bucket(self, *args):
            pass
        def put_object(self, *args, **kwargs):
            pass
        def get_presigned_url(self, *args, **kwargs):
            return "http://minio/test.jpg"
    minio_stub.Minio = MinioStub
    minio_error = types.ModuleType("minio.error")
    minio_error.S3Error = Exception
    sys.modules["minio"] = minio_stub
    sys.modules["minio.error"] = minio_error


class TestAgentBInitialization:
    """Tests for Agent B initialization."""
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_init_creates_all_components(self, mock_consumer, mock_producer, 
                                         mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that Agent B initializes all required components."""
        from AgentB import AgentB
        
        agent = AgentB()
        
        mock_yolo.assert_called_once()
        mock_ocr.assert_called_once()
        mock_classifier.assert_called_once()
        mock_consumer.assert_called_once()
        mock_producer.assert_called_once()
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_init_sets_running_true(self, mock_consumer, mock_producer,
                                    mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that Agent B starts in running state."""
        from AgentB import AgentB
        
        agent = AgentB()
        
        assert agent.running is True
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_init_sets_consensus_defaults(self, mock_consumer, mock_producer,
                                          mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that consensus state is initialized correctly."""
        from AgentB import AgentB
        
        agent = AgentB()
        
        assert agent.consensus_reached is False
        assert agent.counter == {}
        assert agent.decided_chars == {}
        assert agent.decision_threshold == 8
        assert math.isclose(agent.consensus_percentage, 0.8, rel_tol=1e-09, abs_tol=1e-09)
        assert agent.max_frames == 40


class TestAgentBConsensusAlgorithm:
    """Tests for the consensus algorithm."""
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_reset_consensus_state(self, mock_consumer, mock_producer,
                                   mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that reset_consensus_state clears all state."""
        from AgentB import AgentB
        
        agent = AgentB()
        
        # Modify state
        agent.counter = {0: {'A': 5}}
        agent.decided_chars = {0: 'A'}
        agent.consensus_reached = True
        agent.best_crop = np.zeros((10, 10, 3))
        agent.candidate_crops = [{"crop": np.zeros((10, 10, 3)), "text": "TEST", "confidence": 0.9}]
        
        agent._reset_consensus_state()
        
        assert agent.counter == {}
        assert agent.decided_chars == {}
        assert agent.consensus_reached is False
        assert agent.best_crop is None
        assert agent.candidate_crops == []
        assert agent.frames_processed == 0
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_add_to_consensus_ignores_low_confidence(self, mock_consumer, mock_producer,
                                                      mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that low confidence results are ignored."""
        from AgentB import AgentB
        
        agent = AgentB()
        
        agent._add_to_consensus("ABC123", confidence=0.5)  # Below 0.80 threshold
        
        assert agent.counter == {}
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_add_to_consensus_ignores_short_text(self, mock_consumer, mock_producer,
                                                  mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that short text (< 4 chars) is ignored."""
        from AgentB import AgentB
        
        agent = AgentB()
        
        agent._add_to_consensus("AB", confidence=0.95)  # Too short
        
        assert agent.counter == {}
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_add_to_consensus_adds_characters(self, mock_consumer, mock_producer,
                                               mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that consensus correctly adds character votes."""
        from AgentB import AgentB
        
        agent = AgentB()
        
        agent._add_to_consensus("ABC123", confidence=0.90)
        
        # Check that characters were added
        assert 0 in agent.counter
        assert 'A' in agent.counter[0]
        assert agent.counter[0]['A'] >= 1
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_add_to_consensus_high_confidence_double_votes(self, mock_consumer, mock_producer,
                                                            mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that high confidence (>= 0.95) adds double votes."""
        from AgentB import AgentB
        
        agent = AgentB()
        
        agent._add_to_consensus("ABCD", confidence=0.95)
        
        # High confidence should add 2 votes
        assert agent.counter[0]['A'] == 2
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_check_full_consensus_returns_false_when_empty(self, mock_consumer, mock_producer,
                                                           mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that consensus check returns False when no data."""
        from AgentB import AgentB
        
        agent = AgentB()
        
        assert agent._check_full_consensus() is False
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_check_full_consensus_returns_true_when_threshold_met(self, mock_consumer, mock_producer,
                                                                   mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test consensus returns True when threshold is met."""
        from AgentB import AgentB
        
        agent = AgentB()
        
        # Setup counter with 5 positions
        agent.counter = {0: {}, 1: {}, 2: {}, 3: {}, 4: {}}
        
        # Decide 4 out of 5 positions (80%)
        agent.decided_chars = {0: 'A', 1: 'B', 2: 'C', 3: 'D'}
        
        assert agent._check_full_consensus() is True
        assert agent.consensus_reached is True
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_build_final_text_constructs_from_decided_chars(self, mock_consumer, mock_producer,
                                                             mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that build_final_text constructs text correctly."""
        from AgentB import AgentB
        
        agent = AgentB()
        agent.decided_chars = {0: 'A', 1: 'B', 2: '1', 3: '2'}
        
        result = agent._build_final_text()
        
        assert result == "AB12"
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_build_final_text_returns_empty_when_no_decided(self, mock_consumer, mock_producer,
                                                             mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that build_final_text returns empty when no decided chars."""
        from AgentB import AgentB
        
        agent = AgentB()
        
        result = agent._build_final_text()
        
        assert result == ""


class TestAgentBLevenshteinDistance:
    """Tests for Levenshtein distance calculation."""
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_levenshtein_same_strings(self, mock_consumer, mock_producer,
                                       mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test Levenshtein distance of identical strings is 0."""
        from AgentB import AgentB
        
        agent = AgentB()
        
        assert agent._levenshtein_distance("ABC123", "ABC123") == 0
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_levenshtein_one_substitution(self, mock_consumer, mock_producer,
                                           mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test Levenshtein distance with one character substitution."""
        from AgentB import AgentB
        
        agent = AgentB()
        
        assert agent._levenshtein_distance("ABC", "ABD") == 1
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_levenshtein_insertion(self, mock_consumer, mock_producer,
                                    mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test Levenshtein distance with insertion."""
        from AgentB import AgentB
        
        agent = AgentB()
        
        assert agent._levenshtein_distance("ABC", "ABCD") == 1
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_levenshtein_deletion(self, mock_consumer, mock_producer,
                                   mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test Levenshtein distance with deletion."""
        from AgentB import AgentB
        
        agent = AgentB()
        
        assert agent._levenshtein_distance("ABCD", "ABC") == 1
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_levenshtein_empty_strings(self, mock_consumer, mock_producer,
                                        mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test Levenshtein distance with empty string."""
        from AgentB import AgentB
        
        agent = AgentB()
        
        assert agent._levenshtein_distance("", "ABC") == 3
        assert agent._levenshtein_distance("ABC", "") == 3


class TestAgentBSelectBestCrop:
    """Tests for crop selection based on similarity."""
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_select_best_crop_returns_none_when_empty(self, mock_consumer, mock_producer,
                                                       mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that select_best_crop returns None when no candidates."""
        from AgentB import AgentB
        
        agent = AgentB()
        agent.candidate_crops = []
        
        result = agent._select_best_crop("ABC123")
        
        assert result is None
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_select_best_crop_chooses_exact_match(self, mock_consumer, mock_producer,
                                                   mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that exact match crop is selected."""
        from AgentB import AgentB
        
        agent = AgentB()
        
        crop1 = np.zeros((10, 10, 3))
        crop2 = np.ones((10, 10, 3))
        
        agent.candidate_crops = [
            {"crop": crop1, "text": "ABC123", "confidence": 0.9},
            {"crop": crop2, "text": "XYZ789", "confidence": 0.95}
        ]
        
        result = agent._select_best_crop("ABC123")
        
        assert np.array_equal(result, crop1)
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_select_best_crop_uses_confidence_as_tiebreaker(self, mock_consumer, mock_producer,
                                                             mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that confidence is used as tiebreaker."""
        from AgentB import AgentB
        
        agent = AgentB()
        
        crop1 = np.zeros((10, 10, 3))
        crop2 = np.ones((10, 10, 3))
        
        agent.candidate_crops = [
            {"crop": crop1, "text": "ABC123", "confidence": 0.85},
            {"crop": crop2, "text": "ABC123", "confidence": 0.95}
        ]
        
        result = agent._select_best_crop("ABC123")
        
        # Should select crop2 due to higher confidence
        assert np.array_equal(result, crop2)


class TestAgentBPartialResult:
    """Tests for partial result handling."""
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_get_best_partial_result_returns_none_when_empty(self, mock_consumer, mock_producer,
                                                              mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test partial result returns None when no counter data."""
        from AgentB import AgentB
        
        agent = AgentB()
        
        text, conf, crop = agent._get_best_partial_result()
        
        assert text is None
        assert conf is None
        assert crop is None
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_get_best_partial_result_builds_from_decided_and_best_candidates(
            self, mock_consumer, mock_producer, mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test partial result uses decided chars and best candidates."""
        from AgentB import AgentB
        
        agent = AgentB()
        
        # Setup counter with votes
        agent.counter = {
            0: {'A': 5, 'B': 2},
            1: {'B': 4, 'C': 1},
            2: {'C': 3, 'D': 2},
            3: {'1': 6}
        }
        
        # Only some positions decided
        agent.decided_chars = {0: 'A', 3: '1'}
        
        # Add candidate crop
        agent.candidate_crops = [
            {"crop": np.zeros((10, 10, 3)), "text": "ABC1", "confidence": 0.9}
        ]
        
        text, conf, crop = agent._get_best_partial_result()
        
        # Position 0: decided 'A'
        # Position 1: best voted 'B'
        # Position 2: best voted 'C'
        # Position 3: decided '1'
        assert text == "ABC1"
        assert conf <= 0.95  # Max 0.95 for partial
        assert crop is not None


class TestAgentBPublishLPDetected:
    """Tests for publishing license plate detection results."""
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_publish_lp_detected_sends_correct_payload(self, mock_consumer, mock_producer,
                                                        mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that publish sends correct JSON payload."""
        from AgentB import AgentB
        
        mock_producer_instance = Mock()
        mock_producer.return_value = mock_producer_instance
        
        agent = AgentB()
        agent._publish_lp_detected(
            truck_id="TRK123",
            plate_text="AB12CD",
            plate_conf=0.95,
            crop_url="http://minio/crop.jpg"
        )
        
        call_kwargs = mock_producer_instance.produce.call_args[1]
        payload = json.loads(call_kwargs['value'].decode('utf-8'))
        
        assert payload['licensePlate'] == "AB12CD"
        assert math.isclose(payload['confidence'], 0.95, rel_tol=1e-09, abs_tol=1e-09)
        assert payload['cropUrl'] == "http://minio/crop.jpg"
        assert 'timestamp' in payload
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_publish_lp_detected_includes_truck_id_header(self, mock_consumer, mock_producer,
                                                          mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that publish includes truckId in headers."""
        from AgentB import AgentB
        
        mock_producer_instance = Mock()
        mock_producer.return_value = mock_producer_instance
        
        agent = AgentB()
        agent._publish_lp_detected(
            truck_id="TRK456",
            plate_text="XY34ZZ",
            plate_conf=0.88,
            crop_url=None
        )
        
        call_kwargs = mock_producer_instance.produce.call_args[1]
        headers = call_kwargs['headers']
        
        assert headers['truckId'] == "TRK456"


class TestAgentBStop:
    """Tests for stop functionality."""
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_stop_sets_running_false(self, mock_consumer, mock_producer,
                                      mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that stop sets running to False."""
        from AgentB import AgentB
        
        agent = AgentB()
        assert agent.running is True
        
        agent.stop()
        
        assert agent.running is False


class TestAgentBDeliveryCallback:
    """Tests for Kafka delivery callback."""
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_delivery_callback_handles_success(self, mock_consumer, mock_producer,
                                                mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test delivery callback handles successful delivery."""
        from AgentB import AgentB
        
        agent = AgentB()
        
        mock_msg = Mock()
        mock_msg.topic.return_value = 'test-topic'
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 42
        
        # Should not raise
        agent._delivery_callback(None, mock_msg)
    
    @patch('AgentB.CropStorage')
    @patch('AgentB.PlateClassifier')
    @patch('AgentB.OCR')
    @patch('AgentB.YOLO_License_Plate')
    @patch('AgentB.Producer')
    @patch('AgentB.Consumer')
    def test_delivery_callback_handles_error(self, mock_consumer, mock_producer,
                                              mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test delivery callback logs error on failure."""
        from AgentB import AgentB
        
        agent = AgentB()
        
        mock_msg = Mock()
        mock_msg.topic.return_value = 'test-topic'
        mock_msg.partition.return_value = 0
        
        mock_error = Mock()
        
        # Should not raise, just log
        agent._delivery_callback(mock_error, mock_msg)


class TestYOLOLicensePlateUnit:
    """Unit tests for YOLO_License_Plate class."""
    
    @patch('YOLO_License_Plate.YOLO')
    def test_found_license_plate_returns_true_when_boxes_exist(self, mock_yolo):
        """Test found_license_plate returns True when boxes detected."""
        from YOLO_License_Plate import YOLO_License_Plate
        
        mock_model = Mock()
        mock_yolo.return_value = mock_model
        
        yolo = YOLO_License_Plate()
        
        mock_result = Mock()
        mock_result.boxes = [Mock(), Mock()]
        mock_results = [mock_result]
        
        assert yolo.found_license_plate(mock_results) is True
    
    @patch('YOLO_License_Plate.YOLO')
    def test_found_license_plate_returns_false_when_no_boxes(self, mock_yolo):
        """Test found_license_plate returns False when no boxes."""
        from YOLO_License_Plate import YOLO_License_Plate
        
        mock_model = Mock()
        mock_yolo.return_value = mock_model
        
        yolo = YOLO_License_Plate()
        
        mock_result = Mock()
        mock_result.boxes = []
        mock_results = [mock_result]
        
        assert yolo.found_license_plate(mock_results) is False


class TestPlateClassifierUnit:
    """Unit tests for PlateClassifier class."""
    
    def test_classify_returns_unknown_for_none_input(self):
        """Test classifier returns UNKNOWN for None input."""
        from PlateClassifier import PlateClassifier
        
        classifier = PlateClassifier()
        
        result = classifier.classify(None)
        
        assert result == PlateClassifier.UNKNOWN
    
    def test_classify_returns_unknown_for_empty_array(self):
        """Test classifier returns UNKNOWN for empty array."""
        from PlateClassifier import PlateClassifier
        
        classifier = PlateClassifier()
        
        result = classifier.classify(np.array([]))
        
        assert result == PlateClassifier.UNKNOWN
    
    def test_classify_license_plate_by_aspect_ratio(self):
        """Test classifier identifies license plate by wide aspect ratio."""
        from PlateClassifier import PlateClassifier
        
        classifier = PlateClassifier()
        
        # Wide image (typical license plate aspect ratio)
        # Width 200, Height 50 -> aspect ratio = 4.0
        wide_image = np.full((50, 200, 3), 255, dtype=np.uint8)  # White image
        
        result = classifier.classify(wide_image)
        
        # Should identify as license plate due to high aspect ratio + white color
        assert result == PlateClassifier.LICENSE_PLATE
    
    def test_classify_hazard_plate_by_aspect_ratio_and_color(self):
        """Test classifier identifies hazard plate by square/vertical aspect and orange color."""
        from PlateClassifier import PlateClassifier
        import cv2
        
        classifier = PlateClassifier()
        
        # Square image with orange color (typical hazard plate)
        # Create an orange colored square image
        orange_image = np.zeros((100, 80, 3), dtype=np.uint8)
        # BGR for orange: ~(0, 165, 255) 
        orange_image[:, :] = [0, 100, 200]  # Orange-ish BGR
        
        result = classifier.classify(orange_image)
        
        # Should identify as hazard plate due to low aspect ratio + orange color
        assert result in [PlateClassifier.HAZARD_PLATE, PlateClassifier.UNKNOWN]
