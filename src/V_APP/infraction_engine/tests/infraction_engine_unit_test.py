"""
Unit tests for InfractionEngine.
"""

import sys
import importlib
import time
from unittest.mock import MagicMock, patch
import pytest

prometheus_mock = MagicMock()
prometheus_mock.Counter = MagicMock(side_effect=lambda *a, **kw: MagicMock())
prometheus_mock.Histogram = MagicMock(side_effect=lambda *a, **kw: MagicMock())
sys.modules['prometheus_client'] = prometheus_mock

from shared.src.kafka_protocol import (
    LicensePlateResultsMessage,
    HazardPlateResultsMessage,
    KafkaTopicFactory,
)

# Force-reload so the module picks up OUR prometheus mock even if
# a prior test already imported it with a different mock.
import V_APP.infraction_engine.src.infraction_engine as _ie_mod
importlib.reload(_ie_mod)
from V_APP.infraction_engine.src.infraction_engine import InfractionEngine, InfractionEngineConfig


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def make_lp_msg(plate="AB12CD", crop_url="http://lp.jpg", confidence=0.9):
    return LicensePlateResultsMessage(plate, crop_url, confidence)


def make_hz_msg(un="1234", kemler="33", crop_url="http://hz.jpg", confidence=0.85):
    return HazardPlateResultsMessage(un, kemler, crop_url, confidence)


@pytest.fixture
def config():
    return InfractionEngineConfig(
        kafka_bootstrap="localhost:9092",
        infraction_gate_ids='["1"]',
        gate_ids='["1"]',
        decision_gate_ids='["1"]',
        api_url="http://localhost:8080/api/v1",
    )


@pytest.fixture
def engine(config):
    with patch("V_APP.shared.src.base_decision_engine.load_from_file", return_value={"1234": "Test Chemical"}):
        eng = InfractionEngine(
            config=config,
            kafka_producer=MagicMock(),
            kafka_consumer=MagicMock(),
            plate_matcher=MagicMock(),
            database_client=MagicMock(),
        )
    eng.un_numbers = {"1234": "Test Chemical"}
    eng.kemler_codes = {"33": "Highly Flammable"}
    return eng


# ═══════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════

class TestInfractionEngineConfig:
    def test_inherits_base(self):
        cfg = InfractionEngineConfig(
            kafka_bootstrap="localhost:9092",
            infraction_gate_ids='["2","3"]',
        )
        assert cfg.infraction_gate_id_list == ["2", "3"]


# ═══════════════════════════════════════════════════════════════════
# Init
# ═══════════════════════════════════════════════════════════════════

class TestInfractionEngineInit:
    def test_consumer_group(self, engine):
        assert engine._get_consumer_group() == "infraction-engine-group"

    def test_active_gate_ids_uses_infraction_list(self, engine):
        assert engine._get_active_gate_ids() == ["1"]

    def test_metrics_initialized(self, engine):
        assert hasattr(engine, "infractions_processed")
        assert hasattr(engine, "infractions_detected")
        assert hasattr(engine, "no_infractions")


# ═══════════════════════════════════════════════════════════════════
# _is_hazardous
# ═══════════════════════════════════════════════════════════════════

class TestIsHazardous:
    def test_hazardous_with_un(self, engine):
        assert engine._is_hazardous("1234", "N/A") is True

    def test_hazardous_with_kemler(self, engine):
        assert engine._is_hazardous("N/A", "33") is True

    def test_hazardous_with_both(self, engine):
        assert engine._is_hazardous("1234", "33") is True

    def test_not_hazardous_na(self, engine):
        assert engine._is_hazardous("N/A", "N/A") is False

    def test_not_hazardous_empty(self, engine):
        assert engine._is_hazardous("", "") is False

    def test_not_hazardous_mixed(self, engine):
        assert engine._is_hazardous("", "N/A") is False


# ═══════════════════════════════════════════════════════════════════
# _has_matching_appointment
# ═══════════════════════════════════════════════════════════════════

class TestHasMatchingAppointment:
    def test_returns_false_for_na(self, engine):
        matched, plate = engine._has_matching_appointment("1", "N/A")
        assert matched is False
        assert plate == "N/A"

    def test_returns_false_on_api_error(self, engine):
        engine.database_client.get_appointments.side_effect = Exception("connection error")
        matched, plate = engine._has_matching_appointment("1", "AB12CD")
        assert matched is False
        assert plate == "AB12CD"

    def test_returns_false_when_api_unavailable(self, engine):
        engine.database_client.get_appointments.return_value = {"message": "unavailable"}
        engine.database_client.is_api_unavailable.return_value = True
        matched, plate = engine._has_matching_appointment("1", "AB12CD")
        assert matched is False
        assert plate == "AB12CD"

    def test_returns_false_when_no_appointments(self, engine):
        engine.database_client.get_appointments.return_value = {"found": False}
        engine.database_client.is_api_unavailable.return_value = False
        matched, plate = engine._has_matching_appointment("1", "AB12CD")
        assert matched is False
        assert plate == "AB12CD"

    def test_returns_false_when_none(self, engine):
        engine.database_client.get_appointments.return_value = None
        engine.database_client.is_api_unavailable.return_value = False
        matched, plate = engine._has_matching_appointment("1", "AB12CD")
        assert matched is False
        assert plate == "AB12CD"

    def test_returns_true_when_plate_matches(self, engine):
        engine.database_client.get_appointments.return_value = {
            "found": True,
            "candidates": [{"license_plate": "AB12CD"}],
        }
        engine.database_client.is_api_unavailable.return_value = False
        engine.plate_matcher.match_plate.return_value = "AB12CD"
        matched, plate = engine._has_matching_appointment("1", "AB12CD")
        assert matched is True
        assert plate == "AB12CD"

    def test_returns_false_when_no_plate_matches(self, engine):
        engine.database_client.get_appointments.return_value = {
            "found": True,
            "candidates": [{"license_plate": "XY99ZZ"}],
        }
        engine.database_client.is_api_unavailable.return_value = False
        engine.plate_matcher.match_plate.return_value = None
        matched, plate = engine._has_matching_appointment("1", "AB12CD")
        assert matched is False
        assert plate == "AB12CD"

    def test_restores_gate_id(self, engine):
        engine.database_client.gate_id = "original"
        engine.database_client.get_appointments.return_value = {"found": False}
        engine.database_client.is_api_unavailable.return_value = False
        engine._has_matching_appointment("5", "AB12CD")
        assert engine.database_client.gate_id == "original"


# ═══════════════════════════════════════════════════════════════════
# _execute_logic
# ═══════════════════════════════════════════════════════════════════

class TestExecuteLogic:
    def test_no_hazard_publishes_no_infraction(self, engine):
        lp = make_lp_msg()
        hz = make_hz_msg(un="N/A", kemler="N/A")
        engine._execute_logic("1", "truck-1", lp, hz)
        engine.kafka_producer.produce.assert_called_once()
        call_data = engine.kafka_producer.produce.call_args
        assert call_data.kwargs["topic"] == KafkaTopicFactory.infraction_decision("1")

    def test_hazardous_truck_with_appointment(self, engine):
        lp = make_lp_msg(plate="AB12CD")
        hz = make_hz_msg(un="1234", kemler="33")
        engine.database_client.get_appointments.return_value = {
            "found": True,
            "candidates": [{"license_plate": "AB12CD"}],
        }
        engine.database_client.is_api_unavailable.return_value = False
        engine.plate_matcher.match_plate.return_value = "AB12CD"
        engine._execute_logic("1", "truck-1", lp, hz)
        engine.kafka_producer.produce.assert_called_once()

    def test_hazardous_truck_without_appointment(self, engine):
        lp = make_lp_msg(plate="AB12CD")
        hz = make_hz_msg(un="1234", kemler="33")
        engine.database_client.get_appointments.return_value = {"found": False}
        engine.database_client.is_api_unavailable.return_value = False
        engine._execute_logic("1", "truck-1", lp, hz)
        engine.kafka_producer.produce.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# _publish_infraction
# ═══════════════════════════════════════════════════════════════════

class TestPublishInfraction:
    def test_publishes_to_correct_topic(self, engine):
        lp = make_lp_msg()
        hz = make_hz_msg()
        engine._publish_infraction("1", "t1", "AB12CD", lp, hz, "U", "K", True, time.time())
        call_args = engine.kafka_producer.produce.call_args
        assert call_args.kwargs["topic"] == KafkaTopicFactory.infraction_decision("1")
        assert call_args.kwargs["headers"] == {"truckId": "t1"}

    def test_publishes_infraction_true(self, engine):
        lp = make_lp_msg()
        hz = make_hz_msg()
        engine._publish_infraction("1", "t1", "AB12CD", lp, hz, "U", "K", True, time.time())
        data = engine.kafka_producer.produce.call_args.kwargs["data"]
        assert data["infraction"] is True

    def test_publishes_infraction_false(self, engine):
        lp = make_lp_msg()
        hz = make_hz_msg()
        engine._publish_infraction("1", "t1", "AB12CD", lp, hz, "U", "K", False, time.time())
        data = engine.kafka_producer.produce.call_args.kwargs["data"]
        assert data["infraction"] is False


# ═══════════════════════════════════════════════════════════════════
# _record_infraction_metrics
# ═══════════════════════════════════════════════════════════════════

class TestRecordInfractionMetrics:
    def test_infraction_increments_detected(self, engine):
        engine._record_infraction_metrics(True, time.time() - 1)
        engine.infractions_detected.inc.assert_called_once()
        engine.infractions_processed.inc.assert_called_once()

    def test_no_infraction_increments_no_infractions(self, engine):
        engine._record_infraction_metrics(False, time.time() - 1)
        engine.no_infractions.inc.assert_called_once()
        engine.infractions_processed.inc.assert_called_once()
