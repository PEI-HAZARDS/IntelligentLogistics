"""
Unit tests for DecisionEngine class.
Tests for the main decision-making logic.
"""
import sys
from unittest.mock import MagicMock, patch, call
import pytest
import time

# =============================================================================
# Mock setup — must happen before importing the module under test
# =============================================================================

sys.modules['decision_engine.src.database_client'] = MagicMock()

prometheus_mock = MagicMock()
prometheus_mock.Counter = MagicMock(return_value=MagicMock())
prometheus_mock.Histogram = MagicMock(return_value=MagicMock())
sys.modules['prometheus_client'] = prometheus_mock

# Now we can safely import
try:
    from decision_engine import DecisionEngine, DecisionStatus, DecisionEngineConfig
except ImportError:
    from src.decision_engine import DecisionEngine, DecisionStatus, DecisionEngineConfig

from shared.src.kafka_protocol import (
    LicensePlateResultsMessage, HazardPlateResultsMessage, KafkaTopicFactory
)

# =============================================================================
# Helpers
# =============================================================================

def make_lp_msg(plate="AB12CD", confidence=0.95, crop_url="http://minio/lp.jpg"):
    msg = MagicMock(spec=LicensePlateResultsMessage)
    msg.license_plate = plate
    msg.confidence = confidence
    msg.crop_url = crop_url
    return msg

def make_hz_msg(un="1234", kemler="33", confidence=0.90, crop_url="http://minio/hz.jpg"):
    msg = MagicMock(spec=HazardPlateResultsMessage)
    msg.un = un
    msg.kemler = kemler
    msg.confidence = confidence
    msg.crop_url = crop_url
    return msg

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_kafka_consumer():
    return MagicMock()

@pytest.fixture
def mock_kafka_producer():
    return MagicMock()

@pytest.fixture
def mock_plate_matcher():
    return MagicMock()

@pytest.fixture
def mock_database_client():
    return MagicMock()

@pytest.fixture
def config():
    return DecisionEngineConfig(
        kafka_bootstrap="localhost:9092",
        decision_gate_ids='["1"]',
        api_url="http://localhost:8080/api/v1",
    )

@pytest.fixture
def decision_engine(config, mock_kafka_consumer, mock_kafka_producer, mock_plate_matcher, mock_database_client):
    """Create a DecisionEngine with injected mocks — no patching needed."""
    with patch("V_APP.shared.src.base_decision_engine.load_from_file", return_value={"1234": "Test Chemical"}):
        engine = DecisionEngine(
            config=config,
            kafka_producer=mock_kafka_producer,
            kafka_consumer=mock_kafka_consumer,
            plate_matcher=mock_plate_matcher,
            database_client=mock_database_client,
        )
    engine.un_numbers = {"1234": "Test Chemical"}
    engine.kemler_codes = {"33": "Highly Flammable"}
    return engine

# =============================================================================
# Tests — Initialization
# =============================================================================

class TestDecisionEngineInit:
    def test_init_sets_running_true(self, decision_engine):
        assert decision_engine.running is False

    def test_init_creates_empty_buffers(self, decision_engine):
        assert decision_engine.lp_buffer == {}
        assert decision_engine.hz_buffer == {}

# =============================================================================
# Tests — Stop
# =============================================================================

class TestStop:
    def test_stop_sets_running_false(self, decision_engine):
        decision_engine.running = True
        decision_engine.stop()
        assert decision_engine.running is False

# =============================================================================
# Tests — _store_in_buffer
# =============================================================================

class TestStoreInBuffer:
    def test_stores_lp_message(self, decision_engine):
        lp = make_lp_msg()
        decision_engine._store_in_buffer("1", 
            KafkaTopicFactory.license_plate_results("1"), "TRUCK-1", lp
        )
        assert ("1", "TRUCK-1") in decision_engine.lp_buffer
        assert decision_engine.lp_buffer[("1", "TRUCK-1")] is lp

    def test_stores_hz_message(self, decision_engine):
        hz = make_hz_msg()
        decision_engine._store_in_buffer("1", 
            KafkaTopicFactory.hazard_plate_results("1"), "TRUCK-1", hz
        )
        assert ("1", "TRUCK-1") in decision_engine.hz_buffer
        assert decision_engine.hz_buffer[("1", "TRUCK-1")] is hz

    def test_rejects_wrong_type_for_lp_topic(self, decision_engine):
        hz = make_hz_msg()  # Wrong type for LP topic
        decision_engine._store_in_buffer("1", 
            KafkaTopicFactory.license_plate_results("1"), "TRUCK-1", hz
        )
        assert ("1", "TRUCK-1") not in decision_engine.lp_buffer

    def test_rejects_wrong_type_for_hz_topic(self, decision_engine):
        lp = make_lp_msg()  # Wrong type for HZ topic
        decision_engine._store_in_buffer("1", 
            KafkaTopicFactory.hazard_plate_results("1"), "TRUCK-1", lp
        )
        assert ("1", "TRUCK-1") not in decision_engine.hz_buffer

# =============================================================================
# Tests — _try_process_truck
# =============================================================================

class TestTryProcessTruck:
    def test_does_nothing_when_lp_missing(self, decision_engine):
        decision_engine.hz_buffer[("1", "TRUCK-1")] = make_hz_msg()
        with patch.object(decision_engine, '_execute_logic') as mock_make:
            decision_engine._try_process_truck("1", "TRUCK-1")
            mock_make.assert_not_called()

    def test_does_nothing_when_hz_missing(self, decision_engine):
        decision_engine.lp_buffer[("1", "TRUCK-1")] = make_lp_msg()
        with patch.object(decision_engine, '_execute_logic') as mock_make:
            decision_engine._try_process_truck("1", "TRUCK-1")
            mock_make.assert_not_called()

    def test_processes_when_both_available(self, decision_engine):
        decision_engine.lp_buffer[("1", "TRUCK-1")] = make_lp_msg()
        decision_engine.hz_buffer[("1", "TRUCK-1")] = make_hz_msg()
        with patch.object(decision_engine, '_execute_logic') as mock_make:
            decision_engine._try_process_truck("1", "TRUCK-1")
            mock_make.assert_called_once()

    def test_clears_buffers_after_processing(self, decision_engine):
        decision_engine.lp_buffer[("1", "TRUCK-1")] = make_lp_msg()
        decision_engine.hz_buffer[("1", "TRUCK-1")] = make_hz_msg()
        with patch.object(decision_engine, '_execute_logic'):
            decision_engine._try_process_truck("1", "TRUCK-1")
        assert ("1", "TRUCK-1") not in decision_engine.lp_buffer
        assert ("1", "TRUCK-1") not in decision_engine.hz_buffer



# =============================================================================
# Tests — _make_decision (via _publish_decision)
# =============================================================================

class TestMakeDecision:

    def _get_produced_payload(self, mock_producer):
        """Extract the data dict from the produce() call."""
        args, kwargs = mock_producer.produce.call_args
        # produce(topic=..., data=..., headers=...)
        return kwargs.get("data") or (args[1] if len(args) > 1 else None)

    def test_manual_review_if_plate_is_na(self, decision_engine, mock_kafka_producer):
        lp = make_lp_msg(plate="N/A")
        hz = make_hz_msg()
        decision_engine._execute_logic("1", "TRUCK-1", lp, hz)
        payload = self._get_produced_payload(mock_kafka_producer)
        assert payload["decision"] == "MANUAL_REVIEW"
        assert payload["decision_reason"] == "license_plate_not_detected"

    def test_manual_review_if_api_unavailable(self, decision_engine, mock_kafka_producer, mock_database_client):
        mock_database_client.get_appointments.return_value = {"message": "Connection refused"}
        mock_database_client.is_api_unavailable.return_value = True
        decision_engine._execute_logic("1", "TRUCK-1", make_lp_msg(), make_hz_msg())
        payload = self._get_produced_payload(mock_kafka_producer)
        assert payload["decision"] == "MANUAL_REVIEW"
        assert payload["decision_reason"] == "api_unavailable"

    def test_manual_review_if_no_appointments_found(self, decision_engine, mock_kafka_producer, mock_database_client):
        mock_database_client.get_appointments.return_value = {"found": False, "candidates": [], "message": ""}
        mock_database_client.is_api_unavailable.return_value = False
        decision_engine._execute_logic("1", "TRUCK-1", make_lp_msg(), make_hz_msg())
        payload = self._get_produced_payload(mock_kafka_producer)
        assert payload["decision"] == "MANUAL_REVIEW"
        assert payload["decision_reason"] == "empty_db_appointments"

    def test_manual_review_if_plate_not_matched(self, decision_engine, mock_kafka_producer, mock_database_client, mock_plate_matcher):
        mock_database_client.get_appointments.return_value = {
            "found": True, "candidates": [{"license_plate": "XY99ZZ"}], "message": ""
        }
        mock_database_client.is_api_unavailable.return_value = False
        mock_plate_matcher.match_plate.return_value = None
        decision_engine._execute_logic("1", "TRUCK-1", make_lp_msg(), make_hz_msg())
        payload = self._get_produced_payload(mock_kafka_producer)
        assert payload["decision"] == "MANUAL_REVIEW"
        assert payload["decision_reason"] == "license_plate_not_found"

    def test_accepted_if_plate_matched(self, decision_engine, mock_kafka_producer, mock_database_client, mock_plate_matcher):
        mock_database_client.get_appointments.return_value = {
            "found": True, "candidates": [{"license_plate": "AB12CD"}], "message": ""
        }
        mock_database_client.is_api_unavailable.return_value = False
        mock_plate_matcher.match_plate.return_value = "AB12CD"
        decision_engine._execute_logic("1", "TRUCK-1", make_lp_msg(), make_hz_msg())
        payload = self._get_produced_payload(mock_kafka_producer)
        assert payload["decision"] == "ACCEPTED"
        assert payload["decision_reason"] == "license_plate_matched"

    def test_publish_uses_correct_topic(self, decision_engine, mock_kafka_producer):
        lp = make_lp_msg(plate="N/A")
        hz = make_hz_msg()
        decision_engine._execute_logic("1", "TRUCK-1", lp, hz)
        _, kwargs = mock_kafka_producer.produce.call_args
        assert kwargs["topic"] == KafkaTopicFactory.agent_decision("1")

# =============================================================================
# Tests — Metrics
# =============================================================================

class TestRecordMetrics:
    def test_approved_metric_incremented(self, decision_engine):
        decision_engine._record_decision_metrics(DecisionStatus.ACCEPTED.value, time.time())
        decision_engine.approved_access.inc.assert_called()

    def test_denied_metric_incremented(self, decision_engine):
        decision_engine._record_decision_metrics(DecisionStatus.MANUAL_REVIEW.value, time.time())
        decision_engine.manual_review_decisions.inc.assert_called()

    def test_latency_observed(self, decision_engine):
        decision_engine._record_decision_metrics("ACCEPTED", time.time())
        decision_engine.processing_latency.observe.assert_called()

# =============================================================================
# Tests — Cleanup
# =============================================================================

class TestCleanupResources:
    def test_cleanup_calls_close(self, decision_engine, mock_kafka_consumer, mock_kafka_producer):
        decision_engine._cleanup_resources()
        mock_kafka_consumer.close.assert_called()
        mock_kafka_producer.flush.assert_called()
