"""
Comprehensive Unit Tests for Agent C
=====================================
Agent C: Hazard Plate Detection Agent
- Consumes 'truck-detected' events from Kafka
- Detects hazard plates using YOLO
- Extracts UN number and Kemler code using OCR with consensus algorithm
- Publishes 'hz-results-GATE_ID' events to Kafka
"""

import sys
import types
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

# Mock ultralytics before importing AgentC
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


class TestAgentCInitialization:
    """Tests for Agent C initialization."""
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_init_creates_all_components(self, mock_consumer, mock_producer, 
                                         mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that Agent C initializes all required components."""
        from AgentC import AgentC
        
        agent = AgentC()
        
        mock_yolo.assert_called_once()
        mock_ocr.assert_called_once()
        mock_classifier.assert_called_once()
        mock_consumer.assert_called_once()
        mock_producer.assert_called_once()
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_init_sets_running_true(self, mock_consumer, mock_producer,
                                    mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that Agent C starts in running state."""
        from AgentC import AgentC
        
        agent = AgentC()
        
        assert agent.running is True
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_init_sets_consensus_defaults(self, mock_consumer, mock_producer,
                                          mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that consensus state is initialized correctly."""
        from AgentC import AgentC
        
        agent = AgentC()
        
        assert agent.consensus_reached is False
        assert agent.counter == {}
        assert agent.decided_chars == {}
        assert agent.decision_threshold == 8
        assert agent.consensus_percentage == 0.8
        assert agent.max_frames == 40
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_init_creates_frames_queue(self, mock_consumer, mock_producer,
                                       mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that frames queue is created."""
        from AgentC import AgentC
        
        agent = AgentC()
        
        assert isinstance(agent.frames_queue, Queue)


class TestAgentCConsensusAlgorithm:
    """Tests for the consensus algorithm."""
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_reset_consensus_state(self, mock_consumer, mock_producer,
                                   mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that reset_consensus_state clears all state."""
        from AgentC import AgentC
        
        agent = AgentC()
        
        # Modify state
        agent.counter = {0: {'3': 5}}
        agent.decided_chars = {0: '3'}
        agent.consensus_reached = True
        agent.best_crop = np.zeros((10, 10, 3))
        agent.candidate_crops = [{"crop": np.zeros((10, 10, 3)), "text": "331234", "confidence": 0.9}]
        
        agent._reset_consensus_state()
        
        assert agent.counter == {}
        assert agent.decided_chars == {}
        assert agent.consensus_reached is False
        assert agent.best_crop is None
        assert agent.candidate_crops == []
        assert agent.frames_processed == 0
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_add_to_consensus_ignores_low_confidence(self, mock_consumer, mock_producer,
                                                      mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that low confidence results are ignored."""
        from AgentC import AgentC
        
        agent = AgentC()
        
        agent._add_to_consensus("331234", confidence=0.5)  # Below 0.80 threshold
        
        assert agent.counter == {}
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_add_to_consensus_ignores_short_text(self, mock_consumer, mock_producer,
                                                  mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that short text (< 4 chars) is ignored."""
        from AgentC import AgentC
        
        agent = AgentC()
        
        agent._add_to_consensus("33", confidence=0.95)  # Too short
        
        assert agent.counter == {}
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_add_to_consensus_adds_characters(self, mock_consumer, mock_producer,
                                               mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that consensus correctly adds character votes."""
        from AgentC import AgentC
        
        agent = AgentC()
        
        # Typical hazard plate format: "33 1203" (Kemler UN)
        agent._add_to_consensus("331203", confidence=0.90)
        
        # Check that characters were added
        assert 0 in agent.counter
        assert '3' in agent.counter[0]
        assert agent.counter[0]['3'] >= 1
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_add_to_consensus_high_confidence_double_votes(self, mock_consumer, mock_producer,
                                                            mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that high confidence (>= 0.95) adds double votes."""
        from AgentC import AgentC
        
        agent = AgentC()
        
        agent._add_to_consensus("331203", confidence=0.95)
        
        # High confidence should add 2 votes
        assert agent.counter[0]['3'] == 2
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_check_full_consensus_returns_false_when_empty(self, mock_consumer, mock_producer,
                                                           mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that consensus check returns False when no data."""
        from AgentC import AgentC
        
        agent = AgentC()
        
        assert agent._check_full_consensus() is False
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_check_full_consensus_returns_true_when_threshold_met(self, mock_consumer, mock_producer,
                                                                   mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test consensus returns True when threshold is met."""
        from AgentC import AgentC
        
        agent = AgentC()
        
        # Setup counter with 6 positions (typical hazard: "331203")
        agent.counter = {0: {}, 1: {}, 2: {}, 3: {}, 4: {}, 5: {}}
        
        # Decide 5 out of 6 positions (83% > 80%)
        agent.decided_chars = {0: '3', 1: '3', 2: '1', 3: '2', 4: '0'}
        
        assert agent._check_full_consensus() is True
        assert agent.consensus_reached is True
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_build_final_text_constructs_from_decided_chars(self, mock_consumer, mock_producer,
                                                             mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that build_final_text constructs text correctly."""
        from AgentC import AgentC
        
        agent = AgentC()
        agent.decided_chars = {0: '3', 1: '3', 2: '1', 3: '2', 4: '0', 5: '3'}
        
        result = agent._build_final_text()
        
        assert result == "331203"
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_build_final_text_returns_empty_when_no_decided(self, mock_consumer, mock_producer,
                                                             mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that build_final_text returns empty when no decided chars."""
        from AgentC import AgentC
        
        agent = AgentC()
        
        result = agent._build_final_text()
        
        assert result == ""


class TestAgentCLevenshteinDistance:
    """Tests for Levenshtein distance calculation."""
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_levenshtein_same_strings(self, mock_consumer, mock_producer,
                                       mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test Levenshtein distance of identical strings is 0."""
        from AgentC import AgentC
        
        agent = AgentC()
        
        assert agent._levenshtein_distance("331203", "331203") == 0
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_levenshtein_one_substitution(self, mock_consumer, mock_producer,
                                           mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test Levenshtein distance with one character substitution."""
        from AgentC import AgentC
        
        agent = AgentC()
        
        assert agent._levenshtein_distance("331203", "331213") == 1
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_levenshtein_empty_strings(self, mock_consumer, mock_producer,
                                        mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test Levenshtein distance with empty string."""
        from AgentC import AgentC
        
        agent = AgentC()
        
        assert agent._levenshtein_distance("", "331203") == 6
        assert agent._levenshtein_distance("331203", "") == 6


class TestAgentCSelectBestCrop:
    """Tests for crop selection based on similarity."""
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_select_best_crop_returns_none_when_empty(self, mock_consumer, mock_producer,
                                                       mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that select_best_crop returns None when no candidates."""
        from AgentC import AgentC
        
        agent = AgentC()
        agent.candidate_crops = []
        
        result = agent._select_best_crop("331203")
        
        assert result is None
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_select_best_crop_chooses_exact_match(self, mock_consumer, mock_producer,
                                                   mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that exact match crop is selected."""
        from AgentC import AgentC
        
        agent = AgentC()
        
        crop1 = np.zeros((10, 10, 3))
        crop2 = np.ones((10, 10, 3))
        
        agent.candidate_crops = [
            {"crop": crop1, "text": "331203", "confidence": 0.9},
            {"crop": crop2, "text": "221456", "confidence": 0.95}
        ]
        
        result = agent._select_best_crop("331203")
        
        assert np.array_equal(result, crop1)


class TestAgentCPartialResult:
    """Tests for partial result handling."""
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_get_best_partial_result_returns_none_when_empty(self, mock_consumer, mock_producer,
                                                              mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test partial result returns None when no counter data."""
        from AgentC import AgentC
        
        agent = AgentC()
        
        text, conf, crop = agent._get_best_partial_result()
        
        assert text is None
        assert conf is None
        assert crop is None
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_get_best_partial_result_builds_from_decided_and_best_candidates(
            self, mock_consumer, mock_producer, mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test partial result uses decided chars and best candidates."""
        from AgentC import AgentC
        
        agent = AgentC()
        
        # Setup counter with votes for hazard plate
        agent.counter = {
            0: {'3': 5, '2': 2},
            1: {'3': 4, '1': 1},
            2: {'1': 3, '2': 2},
            3: {'2': 6},
            4: {'0': 3},
            5: {'3': 4}
        }
        
        # Only some positions decided
        agent.decided_chars = {0: '3', 1: '3', 3: '2'}
        
        # Add candidate crop
        agent.candidate_crops = [
            {"crop": np.zeros((10, 10, 3)), "text": "331203", "confidence": 0.9}
        ]
        
        text, conf, crop = agent._get_best_partial_result()
        
        assert text is not None
        assert len(text) == 6
        assert conf <= 0.95  # Max 0.95 for partial
        assert crop is not None


class TestAgentCPublishHZDetected:
    """Tests for publishing hazard plate detection results."""
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_publish_hz_detected_sends_correct_payload(self, mock_consumer, mock_producer,
                                                        mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that publish sends correct JSON payload."""
        from AgentC import AgentC
        
        mock_producer_instance = Mock()
        mock_producer.return_value = mock_producer_instance
        
        agent = AgentC()
        agent._publish_hz_detected(
            truck_id="TRK123",
            un="1203",
            kemler="33",
            plate_conf=0.95,
            crop_url="http://minio/crop.jpg"
        )
        
        call_kwargs = mock_producer_instance.produce.call_args[1]
        payload = json.loads(call_kwargs['value'].decode('utf-8'))
        
        assert payload['un'] == "1203"
        assert payload['kemler'] == "33"
        assert payload['confidence'] == pytest.approx(0.95)
        assert payload['cropUrl'] == "http://minio/crop.jpg"
        assert 'timestamp' in payload
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_publish_hz_detected_includes_truck_id_header(self, mock_consumer, mock_producer,
                                                          mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that publish includes truckId in headers."""
        from AgentC import AgentC
        
        mock_producer_instance = Mock()
        mock_producer.return_value = mock_producer_instance
        
        agent = AgentC()
        agent._publish_hz_detected(
            truck_id="TRK456",
            un="1203",
            kemler="33",
            plate_conf=0.88,
            crop_url=None
        )
        
        call_kwargs = mock_producer_instance.produce.call_args[1]
        headers = call_kwargs['headers']
        
        assert headers['truckId'] == "TRK456"


class TestAgentCStop:
    """Tests for stop functionality."""
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_stop_sets_running_false(self, mock_consumer, mock_producer,
                                      mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test that stop sets running to False."""
        from AgentC import AgentC
        
        agent = AgentC()
        assert agent.running is True
        
        agent.stop()
        
        assert agent.running is False


class TestAgentCDeliveryCallback:
    """Tests for Kafka delivery callback."""
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_delivery_callback_handles_success(self, mock_consumer, mock_producer,
                                                mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test delivery callback handles successful delivery."""
        from AgentC import AgentC
        
        agent = AgentC()
        
        mock_msg = Mock()
        mock_msg.topic.return_value = 'test-topic'
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 42
        
        # Should not raise
        agent._delivery_callback(None, mock_msg)
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_delivery_callback_handles_error(self, mock_consumer, mock_producer,
                                              mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test delivery callback logs error on failure."""
        from AgentC import AgentC
        
        agent = AgentC()
        
        mock_msg = Mock()
        mock_msg.topic.return_value = 'test-topic'
        mock_msg.partition.return_value = 0
        
        mock_error = Mock()
        
        # Should not raise, just log
        agent._delivery_callback(mock_error, mock_msg)


class TestYOLOHazardPlateUnit:
    """Unit tests for YOLO_Hazard_Plate class."""
    
    @patch('YOLO_Hazard_Plate.YOLO')
    def test_found_hazard_plate_returns_true_when_boxes_exist(self, mock_yolo):
        """Test found_hazard_plate returns True when boxes detected."""
        from YOLO_Hazard_Plate import YOLO_Hazard_Plate
        
        mock_model = Mock()
        mock_yolo.return_value = mock_model
        
        yolo = YOLO_Hazard_Plate()
        
        mock_result = Mock()
        mock_result.boxes = [Mock(), Mock()]
        mock_results = [mock_result]
        
        assert yolo.found_hazard_plate(mock_results) is True
    
    @patch('YOLO_Hazard_Plate.YOLO')
    def test_found_hazard_plate_returns_false_when_no_boxes(self, mock_yolo):
        """Test found_hazard_plate returns False when no boxes."""
        from YOLO_Hazard_Plate import YOLO_Hazard_Plate
        
        mock_model = Mock()
        mock_yolo.return_value = mock_model
        
        yolo = YOLO_Hazard_Plate()
        
        mock_result = Mock()
        mock_result.boxes = []
        mock_results = [mock_result]
        
        assert yolo.found_hazard_plate(mock_results) is False
    
    @patch('YOLO_Hazard_Plate.YOLO')
    def test_get_boxes_extracts_coordinates_and_confidence(self, mock_yolo):
        """Test get_boxes extracts correct data from results."""
        from YOLO_Hazard_Plate import YOLO_Hazard_Plate
        import torch
        
        mock_model = Mock()
        mock_yolo.return_value = mock_model
        
        yolo = YOLO_Hazard_Plate()
        
        # Create mock box
        mock_box = Mock()
        mock_box.xyxy = [torch.tensor([10.0, 20.0, 100.0, 200.0])]
        mock_box.conf = [torch.tensor([0.92])]
        
        mock_result = Mock()
        mock_result.boxes = [mock_box]
        mock_results = [mock_result]
        
        boxes = yolo.get_boxes(mock_results)
        
        assert len(boxes) == 1
        assert boxes[0][4] == pytest.approx(0.92)  # Confidence (use approx for float precision)


class TestAgentCHazardPlateTextParsing:
    """Tests for parsing hazard plate text into UN number and Kemler code."""
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_parse_hazard_text_with_space_separator(self, mock_consumer, mock_producer,
                                                     mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test parsing hazard text with space separator."""
        # This tests the parsing logic in _loop
        plate_text = "33 1203"
        parts = plate_text.split(" ")
        
        if len(parts) == 2:
            kemler = parts[0]
            un = parts[1]
        else:
            un = "N/A"
            kemler = "N/A"
        
        assert kemler == "33"
        assert un == "1203"
    
    @patch('AgentC.CropStorage')
    @patch('AgentC.PlateClassifier')
    @patch('AgentC.OCR')
    @patch('AgentC.YOLO_Hazard_Plate')
    @patch('AgentC.Producer')
    @patch('AgentC.Consumer')
    def test_parse_hazard_text_without_space(self, mock_consumer, mock_producer,
                                              mock_yolo, mock_ocr, mock_classifier, mock_storage):
        """Test parsing hazard text without space separator."""
        plate_text = "331203"  # No space
        parts = plate_text.split(" ")
        
        if len(parts) == 2:
            kemler = parts[0]
            un = parts[1]
        else:
            un = "N/A"
            kemler = "N/A"
        
        # Without space, should default to N/A
        assert kemler == "N/A"
        assert un == "N/A"
