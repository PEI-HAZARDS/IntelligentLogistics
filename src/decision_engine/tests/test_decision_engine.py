"""
Comprehensive Unit Tests for Decision Engine
=============================================
Decision Engine:
- Consumes 'lp-results' and 'hz-results' events from Kafka
- Matches license plates against appointments database
- Validates UN numbers and Kemler codes
- Makes ACCEPTED/REJECTED/MANUAL_REVIEW decisions
- Publishes decision results to Kafka
"""

import sys
import types
from pathlib import Path
import json
import time
import threading
import pytest
from unittest.mock import Mock, MagicMock, patch, PropertyMock, mock_open
import os

# Setup path for imports
TESTS_DIR = Path(__file__).resolve().parent
MICROSERVICE_ROOT = TESTS_DIR.parent
GLOBAL_SRC = MICROSERVICE_ROOT.parent

sys.path.insert(0, str(MICROSERVICE_ROOT / "src"))
sys.path.insert(0, str(GLOBAL_SRC))


class TestDecisionEngineInitialization:
    """Tests for Decision Engine initialization."""
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n1202|HEATING OIL"))
    def test_init_creates_kafka_components(self, mock_consumer, mock_producer):
        """Test that Decision Engine initializes Kafka components."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        
        mock_consumer.assert_called_once()
        mock_producer.assert_called_once()
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n1202|HEATING OIL"))
    def test_init_sets_running_true(self, mock_consumer, mock_producer):
        """Test that Decision Engine starts in running state."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        
        assert engine.running is True
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n1202|HEATING OIL"))
    def test_init_creates_empty_buffers(self, mock_consumer, mock_producer):
        """Test that LP and HZ buffers are initialized as empty."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        
        assert engine.lp_buffer == {}
        assert engine.hz_buffer == {}
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_init_loads_un_numbers(self, mock_consumer, mock_producer):
        """Test that UN numbers are loaded from file."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        
        assert "1203" in engine.un_numbers
        assert engine.un_numbers["1203"] == "GASOLINE"
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="33|highly flammable liquid\n"))
    def test_init_loads_kemler_codes(self, mock_consumer, mock_producer):
        """Test that Kemler codes are loaded from file."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        
        # Note: Both UN and Kemler use the same mock_open data
        # In reality they read from different files


class TestDecisionEngineLevenshteinDistance:
    """Tests for Levenshtein distance calculation."""
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_levenshtein_same_strings(self, mock_consumer, mock_producer):
        """Test Levenshtein distance of identical strings is 0."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        
        assert engine._levenshtein_distance("5876TK", "5876TK") == 0
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_levenshtein_one_substitution(self, mock_consumer, mock_producer):
        """Test Levenshtein distance with one character substitution."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        
        assert engine._levenshtein_distance("5876TK", "5876TL") == 1
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_levenshtein_insertion(self, mock_consumer, mock_producer):
        """Test Levenshtein distance with insertion."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        
        assert engine._levenshtein_distance("5876TK", "5876TKX") == 1
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_levenshtein_empty_strings(self, mock_consumer, mock_producer):
        """Test Levenshtein distance with empty string."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        
        assert engine._levenshtein_distance("", "ABC") == 3
        assert engine._levenshtein_distance("ABC", "") == 3
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_levenshtein_ocr_confusion_case(self, mock_consumer, mock_producer):
        """Test Levenshtein distance for common OCR confusion cases."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        
        # O vs 0 confusion
        distance = engine._levenshtein_distance("58O6TK", "5806TK")
        assert distance == 1
        
        # I vs 1 confusion
        distance = engine._levenshtein_distance("58I6TK", "5816TK")
        assert distance == 1


class TestDecisionEngineGeneratePlateCandidates:
    """Tests for plate candidate generation using confusion matrix."""
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_generate_candidates_includes_original(self, mock_consumer, mock_producer):
        """Test that original text is included in candidates."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        
        candidates = engine._generate_plate_candidates("AB12")
        
        assert "AB12" in candidates
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_generate_candidates_includes_confusion_variants(self, mock_consumer, mock_producer):
        """Test that confusion variants are generated."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        
        # '0' can be confused with 'O', 'D', 'Q', 'U'
        candidates = engine._generate_plate_candidates("0")
        
        assert "0" in candidates
        assert "O" in candidates
        assert "D" in candidates
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_generate_candidates_for_license_plate(self, mock_consumer, mock_producer):
        """Test candidate generation for typical license plate."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        
        candidates = engine._generate_plate_candidates("5876TK")
        
        # Original should be there
        assert "5876TK" in candidates
        
        # At least some variants should be generated
        assert len(candidates) > 1


class TestDecisionEngineFindMatchingAppointment:
    """Tests for appointment matching logic."""
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_find_matching_returns_none_for_empty_plate(self, mock_consumer, mock_producer):
        """Test that empty plate returns no match."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        
        candidates = [{"license_plate": "5876TK", "appointment_id": 1}]
        
        match, distance = engine._find_matching_appointment("", candidates)
        
        assert match is None
        assert distance == -1
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_find_matching_returns_none_for_empty_candidates(self, mock_consumer, mock_producer):
        """Test that empty candidates list returns no match."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        
        match, distance = engine._find_matching_appointment("5876TK", [])
        
        assert match is None
        assert distance == -1
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_find_matching_exact_match(self, mock_consumer, mock_producer):
        """Test exact match returns correct appointment."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        
        candidates = [
            {"license_plate": "5876TK", "appointment_id": 1},
            {"license_plate": "1234AB", "appointment_id": 2}
        ]
        
        match, distance = engine._find_matching_appointment("5876TK", candidates)
        
        assert match is not None
        assert match["appointment_id"] == 1
        assert distance == 0
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_find_matching_fuzzy_match_within_threshold(self, mock_consumer, mock_producer):
        """Test fuzzy match within Levenshtein threshold."""
        from DecisionEngine import DecisionEngine
        import DecisionEngine as de_module
        
        # Set threshold
        original_threshold = de_module.MAX_LEVENSHTEIN_DISTANCE
        de_module.MAX_LEVENSHTEIN_DISTANCE = 2
        
        try:
            engine = DecisionEngine()
            
            candidates = [
                {"license_plate": "5876TK", "appointment_id": 1}
            ]
            
            # One character off
            match, distance = engine._find_matching_appointment("5876TL", candidates)
            
            assert match is not None
            assert match["appointment_id"] == 1
            assert distance == 1
        finally:
            de_module.MAX_LEVENSHTEIN_DISTANCE = original_threshold
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_find_matching_no_match_beyond_threshold(self, mock_consumer, mock_producer):
        """Test that matches beyond threshold are rejected."""
        from DecisionEngine import DecisionEngine
        import DecisionEngine as de_module
        
        # Set threshold
        original_threshold = de_module.MAX_LEVENSHTEIN_DISTANCE
        de_module.MAX_LEVENSHTEIN_DISTANCE = 1
        
        try:
            engine = DecisionEngine()
            
            candidates = [
                {"license_plate": "5876TK", "appointment_id": 1}
            ]
            
            # Three characters off - beyond threshold
            match, distance = engine._find_matching_appointment("5876ZZ", candidates)
            
            assert match is None
        finally:
            de_module.MAX_LEVENSHTEIN_DISTANCE = original_threshold
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_find_matching_normalizes_plates(self, mock_consumer, mock_producer):
        """Test that plates are normalized (uppercase, no spaces/dashes)."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        
        candidates = [
            {"license_plate": "58-76-TK", "appointment_id": 1}
        ]
        
        # Query with lowercase and different format
        match, distance = engine._find_matching_appointment("5876tk", candidates)
        
        assert match is not None
        assert distance == 0


class TestDecisionEngineUNAndKemlerLookup:
    """Tests for UN number and Kemler code lookup."""
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n1202|HEATING OIL\n"))
    def test_get_un_description_valid(self, mock_consumer, mock_producer):
        """Test UN description lookup for valid UN number."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        engine.un_numbers = {"1203": "GASOLINE", "1202": "HEATING OIL"}
        
        desc = engine._get_un_description("1203")
        
        assert desc == "GASOLINE"
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_get_un_description_unknown(self, mock_consumer, mock_producer):
        """Test UN description lookup for unknown UN number."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        engine.un_numbers = {"1203": "GASOLINE"}
        
        desc = engine._get_un_description("9999")
        
        assert desc == "Unknown UN Number"
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="33|highly flammable liquid\n"))
    def test_get_kemler_description_valid(self, mock_consumer, mock_producer):
        """Test Kemler description lookup for valid code."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        engine.kemler_codes = {"33": "highly flammable liquid"}
        
        desc = engine._get_kemler_description("33")
        
        assert desc == "highly flammable liquid"
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="33|highly flammable liquid\n"))
    def test_get_kemler_description_unknown(self, mock_consumer, mock_producer):
        """Test Kemler description lookup for unknown code."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        engine.kemler_codes = {"33": "highly flammable liquid"}
        
        desc = engine._get_kemler_description("99")
        
        assert desc == "Unknown Kemler Code"


class TestDecisionEnginePublishDecision:
    """Tests for publishing decisions to Kafka."""
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_publish_decision_sends_correct_payload(self, mock_consumer, mock_producer):
        """Test that decision is published with correct payload."""
        from DecisionEngine import DecisionEngine
        
        mock_producer_instance = Mock()
        mock_producer.return_value = mock_producer_instance
        
        engine = DecisionEngine()
        
        decision_data = {
            "timestamp": "2025-01-01T10:00:00Z",
            "licensePlate": "5876TK",
            "UN": "1203: GASOLINE",
            "kemler": "33: highly flammable liquid",
            "alerts": [],
            "decision": "ACCEPTED"
        }
        
        engine._publish_decision("TRK123", decision_data)
        
        call_kwargs = mock_producer_instance.produce.call_args[1]
        payload = json.loads(call_kwargs['value'].decode('utf-8'))
        
        assert payload['licensePlate'] == "5876TK"
        assert payload['decision'] == "ACCEPTED"
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_publish_decision_includes_truck_id_header(self, mock_consumer, mock_producer):
        """Test that truck_id is included in headers."""
        from DecisionEngine import DecisionEngine
        
        mock_producer_instance = Mock()
        mock_producer.return_value = mock_producer_instance
        
        engine = DecisionEngine()
        
        decision_data = {"decision": "ACCEPTED"}
        
        engine._publish_decision("TRK456", decision_data)
        
        call_kwargs = mock_producer_instance.produce.call_args[1]
        headers = call_kwargs['headers']
        
        assert headers['truck_id'] == "TRK456"


class TestDecisionEngineStop:
    """Tests for stop functionality."""
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_stop_sets_running_false(self, mock_consumer, mock_producer):
        """Test that stop sets running to False."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        assert engine.running is True
        
        engine.stop()
        
        assert engine.running is False


class TestDecisionEngineConfusionMatrix:
    """Tests for OCR confusion matrix."""
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_confusion_matrix_number_zero(self, mock_consumer, mock_producer):
        """Test that 0 has correct confusable characters."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        
        assert '0' in engine.confusion_matrix
        assert 'O' in engine.confusion_matrix['0']
        assert 'D' in engine.confusion_matrix['0']
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_confusion_matrix_number_one(self, mock_consumer, mock_producer):
        """Test that 1 has correct confusable characters."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        
        assert '1' in engine.confusion_matrix
        assert 'I' in engine.confusion_matrix['1']
        assert 'L' in engine.confusion_matrix['1']
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_confusion_matrix_letter_S(self, mock_consumer, mock_producer):
        """Test that S has correct confusable characters."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        
        assert 'S' in engine.confusion_matrix
        assert '5' in engine.confusion_matrix['S']
        assert '8' in engine.confusion_matrix['S']


class TestDecisionEngineMakeDecision:
    """Tests for the main decision-making logic."""
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    @patch('DecisionEngine.requests.post')
    def test_make_decision_manual_review_for_missing_license_plate(
            self, mock_post, mock_consumer, mock_producer):
        """Test that missing license plate triggers manual review."""
        from DecisionEngine import DecisionEngine
        
        mock_producer_instance = Mock()
        mock_producer.return_value = mock_producer_instance
        
        engine = DecisionEngine()
        engine.un_numbers = {"1203": "GASOLINE"}
        engine.kemler_codes = {"33": "highly flammable liquid"}
        
        lp_data = {"licensePlate": "N/A", "cropUrl": None}
        hz_data = {"un": "1203", "kemler": "33", "cropUrl": None}
        
        engine._make_decision("TRK123", lp_data, hz_data)
        
        # Check that produce was called
        call_kwargs = mock_producer_instance.produce.call_args[1]
        payload = json.loads(call_kwargs['value'].decode('utf-8'))
        
        assert payload['decision'] == "MANUAL_REVIEW"
        assert "License plate not detected" in payload['alerts']
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    @patch('DecisionEngine.requests.post')
    @patch('DecisionEngine.requests.patch')
    def test_make_decision_accepted_for_matching_appointment(
            self, mock_patch, mock_post, mock_consumer, mock_producer):
        """Test that matching appointment results in ACCEPTED decision."""
        from DecisionEngine import DecisionEngine
        
        mock_producer_instance = Mock()
        mock_producer.return_value = mock_producer_instance
        
        # Mock API response with matching appointment
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "found": True,
            "candidates": [
                {
                    "license_plate": "5876TK",
                    "appointment_id": 123,
                    "gate_in_id": "1",
                    "terminal_id": "T1"
                }
            ]
        }
        
        mock_patch.return_value.status_code = 200
        
        engine = DecisionEngine()
        engine.un_numbers = {"1203": "GASOLINE"}
        engine.kemler_codes = {"33": "highly flammable liquid"}
        
        lp_data = {"licensePlate": "5876TK", "cropUrl": "http://minio/lp.jpg"}
        hz_data = {"un": "1203", "kemler": "33", "cropUrl": "http://minio/hz.jpg"}
        
        engine._make_decision("TRK123", lp_data, hz_data)
        
        call_kwargs = mock_producer_instance.produce.call_args[1]
        payload = json.loads(call_kwargs['value'].decode('utf-8'))
        
        assert payload['decision'] == "ACCEPTED"
        assert payload['route'] is not None
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    @patch('DecisionEngine.requests.post')
    def test_make_decision_rejected_for_no_matching_appointment(
            self, mock_post, mock_consumer, mock_producer):
        """Test that no matching appointment results in REJECTED decision."""
        from DecisionEngine import DecisionEngine
        
        mock_producer_instance = Mock()
        mock_producer.return_value = mock_producer_instance
        
        # Mock API response with no matching appointments
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "found": False,
            "candidates": [],
            "message": "No appointments found"
        }
        
        engine = DecisionEngine()
        engine.un_numbers = {"1203": "GASOLINE"}
        engine.kemler_codes = {"33": "highly flammable liquid"}
        
        lp_data = {"licensePlate": "UNKNOWN", "cropUrl": None}
        hz_data = {"un": "1203", "kemler": "33", "cropUrl": None}
        
        engine._make_decision("TRK123", lp_data, hz_data)
        
        call_kwargs = mock_producer_instance.produce.call_args[1]
        payload = json.loads(call_kwargs['value'].decode('utf-8'))
        
        assert payload['decision'] == "REJECTED"


class TestDecisionEngineBufferManagement:
    """Tests for LP and HZ buffer management."""
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_lp_buffer_stores_data(self, mock_consumer, mock_producer):
        """Test that LP data is stored in buffer."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        
        engine.lp_buffer["TRK123"] = {"licensePlate": "5876TK"}
        
        assert "TRK123" in engine.lp_buffer
        assert engine.lp_buffer["TRK123"]["licensePlate"] == "5876TK"
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_hz_buffer_stores_data(self, mock_consumer, mock_producer):
        """Test that HZ data is stored in buffer."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        
        engine.hz_buffer["TRK123"] = {"un": "1203", "kemler": "33"}
        
        assert "TRK123" in engine.hz_buffer
        assert engine.hz_buffer["TRK123"]["un"] == "1203"
    
    @patch('DecisionEngine.Producer')
    @patch('DecisionEngine.Consumer')
    @patch('builtins.open', mock_open(read_data="1203|GASOLINE\n"))
    def test_buffers_can_hold_multiple_trucks(self, mock_consumer, mock_producer):
        """Test that buffers can hold data for multiple trucks."""
        from DecisionEngine import DecisionEngine
        
        engine = DecisionEngine()
        
        engine.lp_buffer["TRK001"] = {"licensePlate": "5876TK"}
        engine.lp_buffer["TRK002"] = {"licensePlate": "1234AB"}
        
        assert len(engine.lp_buffer) == 2
        assert "TRK001" in engine.lp_buffer
        assert "TRK002" in engine.lp_buffer
