"""
Unit tests for DecisionEngine class.
Tests for the main decision-making logic.
"""
import sys
from unittest.mock import MagicMock, patch
import pytest
import time

# =============================================================================
# Mock setup to handle imports before loading the module
# =============================================================================

# We need to mock these modules because they are imported by decision_engine.py
# and might cause import errors or require complex setup
mock_plate_matcher_module = MagicMock()
mock_db_client_module = MagicMock()

sys.modules['decision_engine.src.plate_matcher'] = mock_plate_matcher_module
sys.modules['decision_engine.src.database_client'] = mock_db_client_module

# Now we can safely import the class under test
# The try/except block handles different import paths depending on how pytest is run
try:
    from decision_engine import DecisionEngine, DecisionStatus
except ImportError:
    # Fallback for when running from different directory
    from src.decision_engine import DecisionEngine, DecisionStatus

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_kafka_consumer():
    """Create a mock Kafka consumer."""
    return MagicMock()

@pytest.fixture
def mock_kafka_producer():
    """Create a mock Kafka producer."""
    return MagicMock()

@pytest.fixture
def mock_plate_matcher():
    """Create a mock PlateMatcher instance."""
    return MagicMock()

@pytest.fixture
def mock_database_client():
    """Create a mock DatabaseClient instance."""
    return MagicMock()

@pytest.fixture
def decision_engine(mock_kafka_consumer, mock_kafka_producer, mock_plate_matcher, mock_database_client):
    """Create a real DecisionEngine instance with mocked dependencies."""
    with patch("decision_engine.KafkaConsumerWrapper", return_value=mock_kafka_consumer), \
         patch("decision_engine.KafkaProducerWrapper", return_value=mock_kafka_producer), \
         patch("decision_engine.PlateMatcher", return_value=mock_plate_matcher), \
         patch("decision_engine.DatabaseClient", return_value=mock_database_client), \
         patch("decision_engine.load_from_file", return_value={"1234": "Test Chemical"}):
        
        engine = DecisionEngine()
        # Ensure our specific mocks are attached (constructor might create new mocks)
        engine.kafka_consumer = mock_kafka_consumer
        engine.kafka_producer = mock_kafka_producer
        engine.plate_matcher = mock_plate_matcher
        engine.database_client = mock_database_client
        
        # Setup basic data
        engine.un_numbers = {"1234": "Test Chemical"}
        engine.kemler_codes = {"33": "Highly Flammable"}
        
        return engine

@pytest.fixture
def sample_lp_data():
    """Sample license plate detection data."""
    return {
        "licensePlate": "AB-12-CD",
        "confidence": 0.95,
        "cropUrl": "http://minio/lp-crop.jpg"
    }

@pytest.fixture
def sample_hz_data():
    """Sample hazard plate detection data."""
    return {
        "un": "1234",
        "kemler": "33",
        "confidence": 0.90,
        "cropUrl": "http://minio/hz-crop.jpg"
    }

# =============================================================================
# Tests
# =============================================================================

class TestDecisionEngineInit:
    """Tests for DecisionEngine initialization."""

    def test_init_sets_running_true(self, decision_engine):
        """Initialization sets running to True."""
        assert decision_engine.running is True

    def test_init_creates_empty_buffers(self, decision_engine):
        """Initialization creates empty LP and HZ buffers."""
        assert decision_engine.lp_buffer == {}
        assert decision_engine.hz_buffer == {}


class TestStop:
    """Tests for stop method."""

    def test_stop_sets_running_false(self, decision_engine):
        """Stop sets running to False."""
        decision_engine.running = True
        decision_engine.stop()
        assert decision_engine.running is False


class TestStoreInBuffer:
    """Tests for _store_in_buffer method."""

    def test_stores_lp_data(self, decision_engine, sample_lp_data):
        """Stores LP data in lp_buffer."""
        decision_engine._store_in_buffer("lp-results-1", "TRUCK-123", sample_lp_data)
        assert "TRUCK-123" in decision_engine.lp_buffer
        assert decision_engine.lp_buffer["TRUCK-123"] == sample_lp_data

    def test_stores_hz_data(self, decision_engine, sample_hz_data):
        """Stores HZ data in hz_buffer."""
        decision_engine._store_in_buffer("hz-results-1", "TRUCK-123", sample_hz_data)
        assert "TRUCK-123" in decision_engine.hz_buffer
        assert decision_engine.hz_buffer["TRUCK-123"] == sample_hz_data


class TestTryProcessTruck:
    """Tests for _try_process_truck method."""

    def test_does_nothing_when_lp_missing(self, decision_engine, sample_hz_data):
        """Does nothing when LP data is missing."""
        decision_engine.hz_buffer["TRUCK-123"] = sample_hz_data
        
        # Mock _make_decision to verify it's NOT called
        with patch.object(decision_engine, '_make_decision') as mock_make:
            decision_engine._try_process_truck("TRUCK-123")
            mock_make.assert_not_called()

    def test_does_nothing_when_hz_missing(self, decision_engine, sample_lp_data):
        """Does nothing when HZ data is missing."""
        decision_engine.lp_buffer["TRUCK-123"] = sample_lp_data
        
        with patch.object(decision_engine, '_make_decision') as mock_make:
            decision_engine._try_process_truck("TRUCK-123")
            mock_make.assert_not_called()

    def test_processes_when_both_available(self, decision_engine, sample_lp_data, sample_hz_data):
        """Processes truck when both LP and HZ data available."""
        decision_engine.lp_buffer["TRUCK-123"] = sample_lp_data
        decision_engine.hz_buffer["TRUCK-123"] = sample_hz_data
        
        with patch.object(decision_engine, '_make_decision') as mock_make:
            decision_engine._try_process_truck("TRUCK-123")
            mock_make.assert_called_once()


class TestExtractDetectionData:
    """Tests for _extract_detection_data method."""

    def test_extracts_data_correctly(self, decision_engine, sample_lp_data, sample_hz_data):
        """Extracts all fields correctly."""
        result = decision_engine._extract_detection_data(sample_lp_data, sample_hz_data)
        assert result["license_plate"] == "AB-12-CD"
        assert result["un_number"] == "1234"
        assert result["kemler_code"] == "33"
        assert "Test Chemical" in result["un_data"]
        assert "Highly Flammable" in result["kemler_data"]

    def test_handles_missing_fields(self, decision_engine):
        """Handles missing fields gracefully."""
        result = decision_engine._extract_detection_data({}, {})
        assert result["license_plate"] == "N/A"
        assert result["un_number"] == "N/A"
        assert "No UN number" in result["un_data"]


class TestGetAppointmentFromPlate:
    """Tests for _get_appointment_from_plate method."""

    def test_returns_matching_appointment(self, decision_engine):
        """Returns match from list."""
        appointments = [{"license_plate": "AB-12-CD", "id": 1}]
        result = decision_engine._get_appointment_from_plate("AB-12-CD", appointments)
        assert result["id"] == 1

    def test_returns_none_no_match(self, decision_engine):
        """Returns None if not found."""
        appointments = [{"license_plate": "XY-99-ZZ", "id": 1}]
        result = decision_engine._get_appointment_from_plate("AB-12-CD", appointments)
        assert result is None


class TestBuildDecisionPayload:
    """Tests for _build_decision_payload method."""

    def test_builds_payload(self, decision_engine, sample_lp_data, sample_hz_data):
        """Builds correct payload dict."""
        detection = {
            "license_plate": "AB-12-CD", 
            "un_data": "UN1234", 
            "kemler_data": "K33"
        }
        
        result = decision_engine._build_decision_payload(
            "2024-01-01", detection, sample_lp_data, sample_hz_data,
            "ACCEPTED", [], "test_reason", None
        )
        
        assert result["decision"] == "ACCEPTED"
        assert result["licensePlate"] == "AB-12-CD"
        assert result["decision_reason"] == "test_reason"
        assert result["lp_cropUrl"] == sample_lp_data["cropUrl"]


class TestMakeDecision:
    """Tests for key _make_decision logic."""

    def test_manual_review_if_plate_missing(self, decision_engine, sample_hz_data):
        """Goes to MANUAL_REVIEW if license plate is N/A."""
        lp_data = {"licensePlate": "N/A"}
        
        decision_engine._make_decision("TRUCK-1", lp_data, sample_hz_data)
        
        # Verify payload sent to Kafka has MANUAL_REVIEW
        args = decision_engine.kafka_producer.produce.call_args
        assert args is not None
        payload = args[0][1]
        assert payload["decision"] == "MANUAL_REVIEW"
        assert payload["decision_reason"] == "license_plate_not_detected"


    def test_manual_review_if_no_appointments_found(self, decision_engine, sample_lp_data, sample_hz_data):
        """Goes to MANUAL_REVIEW if no appointments found in DB."""
        decision_engine.database_client.get_appointments.return_value = {
            "found": False, 
            "candidates": [],
            "message": "No appointments"
        }
        decision_engine.database_client.is_api_unavailable.return_value = False
        
        decision_engine._make_decision("TRUCK-1", sample_lp_data, sample_hz_data)
        
        args = decision_engine.kafka_producer.produce.call_args
        payload = args[0][1]
        assert payload["decision"] == "MANUAL_REVIEW"
        assert payload["decision_reason"] == "empty_db_appointments"

    def test_manual_review_if_no_plate_match(self, decision_engine, sample_lp_data, sample_hz_data):
        """Goes to MANUAL_REVIEW if plate matching fails."""
        decision_engine.database_client.get_appointments.return_value = {
            "found": True,
            "candidates": [{"license_plate": "XY-99-ZZ"}]
        }
        decision_engine.database_client.is_api_unavailable.return_value = False
        decision_engine.plate_matcher.match_plate.return_value = None  # No match
        
        decision_engine._make_decision("TRUCK-1", sample_lp_data, sample_hz_data)
        
        args = decision_engine.kafka_producer.produce.call_args
        payload = args[0][1]
        assert payload["decision"] == "MANUAL_REVIEW"
        assert payload["decision_reason"] == "license_plate_not_found"

    def test_record_metrics_rejected(self, decision_engine):
        """Records metrics for REJECTED decision."""
        # This covers lines 279-280
        decision_engine._record_decision_metrics("REJECTED", time.time())
        decision_engine.denied_access.inc.assert_called()


class TestLoop:
    """Tests for main loop logic."""
    
    def test_loop_processes_message(self, decision_engine):
        """Loop consumes and processes message."""
        # Setup mocks to run loop once then stop
        decision_engine.kafka_consumer.consume_message.side_effect = ["msg", None] # Run once then None
        decision_engine.kafka_consumer.parse_message.return_value = ("topic", {"data": 1}, "truck1")
        
        # Mock running state to stop after first iteration
        # We can't easily change decision_engine.running within the loop without side_effect on a method called in the loop
        # Instead, we rely on consume_message raising an exception or returning None (which continues)
        # To break the loop we can mock consume_message to raise KeyboardInterrupt eventually
        decision_engine.kafka_consumer.consume_message.side_effect = ["msg", KeyboardInterrupt()]
        
        decision_engine.loop()
        
        # Verify processing happened
        decision_engine.kafka_consumer.parse_message.assert_called()
        
    def test_loop_handles_exception(self, decision_engine):
        """Loop handles unexpected exceptions."""
        decision_engine.kafka_consumer.consume_message.side_effect = Exception("Boom")
        
        decision_engine.loop()
        
        # Should verify it logged exception and finished (via break or running=False)
        # Since loop catches Exception and continues, we need a way to stop it.
        # The code is: while self.running: try ... except Exception: logger.exception...
        # So it will loop forever on Exception unless we stop it.
        # We can make the Exception side effect raise KeyboardInterrupt the second time
        decision_engine.kafka_consumer.consume_message.side_effect = [Exception("Boom"), KeyboardInterrupt()]
        
        decision_engine.loop()
        
        # Should have called close eventually
        decision_engine.kafka_consumer.close.assert_called()


class TestCleanupResources:
    """Tests for cleanup."""

    def test_cleanup_calls_close(self, decision_engine):
        """Cleanup closes resources."""
        decision_engine._cleanup_resources()
        decision_engine.kafka_consumer.close.assert_called()
        decision_engine.kafka_producer.flush.assert_called()
