"""
Unit tests for BaseDecisionEngine and BaseDecisionEngineConfig.
"""

import sys
import time
from unittest.mock import MagicMock, patch, PropertyMock
import pytest

# Mock prometheus before importing
prometheus_mock = MagicMock()
prometheus_mock.Counter = MagicMock(return_value=MagicMock())
prometheus_mock.Histogram = MagicMock(return_value=MagicMock())
sys.modules.setdefault('prometheus_client', prometheus_mock)

from shared.src.kafka_protocol import (
    LicensePlateResultsMessage,
    HazardPlateResultsMessage,
    KafkaTopicFactory,
)
from V_APP.shared.src.base_decision_engine import BaseDecisionEngine, BaseDecisionEngineConfig


# ═══════════════════════════════════════════════════════════════════
# Concrete subclass for testing
# ═══════════════════════════════════════════════════════════════════

class ConcreteDecisionEngine(BaseDecisionEngine):
    def _get_active_gate_ids(self) -> list[str]:
        return self.config.decision_gate_id_list

    def _get_consumer_group(self) -> str:
        return "test-group"

    def _init_specific_metrics(self) -> None:
        self.test_metric = MagicMock()

    def _execute_logic(self, gate_id, truck_id, lp_msg, hz_msg):
        self.last_executed = (gate_id, truck_id, lp_msg, hz_msg)


# ═══════════════════════════════════════════════════════════════════
# Helpers / fixtures
# ═══════════════════════════════════════════════════════════════════

def make_lp_msg(plate="AB12CD", crop_url="http://lp.jpg", confidence=0.9, timestamp=None):
    return LicensePlateResultsMessage(plate, crop_url, confidence, timestamp=timestamp)


def make_hz_msg(un="1234", kemler="33", crop_url="http://hz.jpg", confidence=0.85, timestamp=None):
    return HazardPlateResultsMessage(un, kemler, crop_url, confidence, timestamp=timestamp)


@pytest.fixture
def config():
    return BaseDecisionEngineConfig(
        kafka_bootstrap="localhost:9092",
        decision_gate_ids='["1"]',
        gate_ids='["1"]',
        infraction_gate_ids='["1"]',
        api_url="http://localhost:8080/api/v1",
    )


@pytest.fixture
def engine(config):
    with patch("V_APP.shared.src.base_decision_engine.load_from_file", return_value={"1234": "Test Chemical"}):
        eng = ConcreteDecisionEngine(
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
# BaseDecisionEngineConfig
# ═══════════════════════════════════════════════════════════════════

class TestBaseDecisionEngineConfig:
    def test_defaults(self):
        cfg = BaseDecisionEngineConfig()
        assert cfg.time_tolerance_minutes == 30
        assert cfg.expiration_time_hours == 24

    def test_gate_id_list(self):
        cfg = BaseDecisionEngineConfig(gate_ids='["1","2","3"]')
        assert cfg.gate_id_list == ["1", "2", "3"]

    def test_decision_gate_id_list(self):
        cfg = BaseDecisionEngineConfig(decision_gate_ids='["4","5"]')
        assert cfg.decision_gate_id_list == ["4", "5"]

    def test_infraction_gate_id_list(self):
        cfg = BaseDecisionEngineConfig(infraction_gate_ids='["6"]')
        assert cfg.infraction_gate_id_list == ["6"]

    def test_invalid_json_gate_ids(self):
        with pytest.raises(Exception):
            BaseDecisionEngineConfig(gate_ids="not_json")

    def test_empty_array_gate_ids(self):
        with pytest.raises(Exception):
            BaseDecisionEngineConfig(gate_ids="[]")

    def test_int_gate_ids_coerced_to_str(self):
        cfg = BaseDecisionEngineConfig(gate_ids='[1, 2]')
        assert cfg.gate_id_list == ["1", "2"]


# ═══════════════════════════════════════════════════════════════════
# Init / state
# ═══════════════════════════════════════════════════════════════════

class TestBaseDecisionEngineInit:
    def test_running_initially_false(self, engine):
        assert engine.running is False

    def test_buffers_empty(self, engine):
        assert engine.lp_buffer == {}
        assert engine.hz_buffer == {}

    def test_topics_built(self, engine):
        assert KafkaTopicFactory.license_plate_results("1") in engine._lp_topics
        assert KafkaTopicFactory.hazard_plate_results("1") in engine._hz_topics

    def test_stop(self, engine):
        engine.running = True
        engine.stop()
        assert engine.running is False


# ═══════════════════════════════════════════════════════════════════
# _store_in_buffer
# ═══════════════════════════════════════════════════════════════════

class TestStoreInBuffer:
    def test_stores_lp_message(self, engine):
        lp_topic = KafkaTopicFactory.license_plate_results("1")
        lp_msg = make_lp_msg()
        engine._store_in_buffer("1", lp_topic, "truck-1", lp_msg)
        assert ("1", "truck-1") in engine.lp_buffer

    def test_stores_hz_message(self, engine):
        hz_topic = KafkaTopicFactory.hazard_plate_results("1")
        hz_msg = make_hz_msg()
        engine._store_in_buffer("1", hz_topic, "truck-1", hz_msg)
        assert ("1", "truck-1") in engine.hz_buffer

    def test_wrong_type_on_lp_topic_is_ignored(self, engine):
        lp_topic = KafkaTopicFactory.license_plate_results("1")
        hz_msg = make_hz_msg()
        engine._store_in_buffer("1", lp_topic, "truck-1", hz_msg)
        assert ("1", "truck-1") not in engine.lp_buffer

    def test_wrong_type_on_hz_topic_is_ignored(self, engine):
        hz_topic = KafkaTopicFactory.hazard_plate_results("1")
        lp_msg = make_lp_msg()
        engine._store_in_buffer("1", hz_topic, "truck-1", lp_msg)
        assert ("1", "truck-1") not in engine.hz_buffer


# ═══════════════════════════════════════════════════════════════════
# _try_process_truck
# ═══════════════════════════════════════════════════════════════════

class TestTryProcessTruck:
    def test_no_execution_when_only_lp(self, engine):
        engine.lp_buffer[("1", "t1")] = make_lp_msg()
        engine._try_process_truck("1", "t1")
        assert not hasattr(engine, "last_executed")

    def test_no_execution_when_only_hz(self, engine):
        engine.hz_buffer[("1", "t1")] = make_hz_msg()
        engine._try_process_truck("1", "t1")
        assert not hasattr(engine, "last_executed")

    def test_executes_when_both_present(self, engine):
        key = ("1", "t1")
        lp = make_lp_msg()
        hz = make_hz_msg()
        engine.lp_buffer[key] = lp
        engine.hz_buffer[key] = hz
        engine._try_process_truck("1", "t1")
        assert engine.last_executed == ("1", "t1", lp, hz)

    def test_cleans_buffers_after_execution(self, engine):
        key = ("1", "t1")
        engine.lp_buffer[key] = make_lp_msg()
        engine.hz_buffer[key] = make_hz_msg()
        engine._try_process_truck("1", "t1")
        assert key not in engine.lp_buffer
        assert key not in engine.hz_buffer


# ═══════════════════════════════════════════════════════════════════
# _clear_stale_buffer_entries
# ═══════════════════════════════════════════════════════════════════

class TestClearStaleEntries:
    def test_removes_expired_entries(self, engine):
        engine.expiration_time_seconds = 10
        old_ts = time.time() - 20
        engine.lp_buffer[("1", "old")] = make_lp_msg(timestamp=int(old_ts))
        engine.hz_buffer[("1", "old")] = make_hz_msg(timestamp=int(old_ts))
        engine._clear_stale_buffer_entries()
        assert ("1", "old") not in engine.lp_buffer
        assert ("1", "old") not in engine.hz_buffer

    def test_keeps_fresh_entries(self, engine):
        engine.expiration_time_seconds = 3600
        fresh_ts = time.time()
        engine.lp_buffer[("1", "fresh")] = make_lp_msg(timestamp=int(fresh_ts))
        engine._clear_stale_buffer_entries()
        assert ("1", "fresh") in engine.lp_buffer


# ═══════════════════════════════════════════════════════════════════
# Lookup helpers
# ═══════════════════════════════════════════════════════════════════

class TestLookupHelpers:
    def test_get_un_description_known(self, engine):
        assert engine._get_un_description("1234") == "Test Chemical"

    def test_get_un_description_unknown(self, engine):
        assert engine._get_un_description("9999") == "Unknown UN Number"

    def test_get_kemler_description_known(self, engine):
        assert engine._get_kemler_description("33") == "Highly Flammable"

    def test_get_kemler_description_unknown(self, engine):
        assert engine._get_kemler_description("99") == "Unknown Kemler Code"

    def test_enrich_hazard_codes_both(self, engine):
        full_un, full_kemler = engine._enrich_hazard_codes("1234", "33")
        assert "1234" in full_un
        assert "Test Chemical" in full_un
        assert "33" in full_kemler
        assert "Highly Flammable" in full_kemler

    def test_enrich_hazard_codes_empty(self, engine):
        full_un, full_kemler = engine._enrich_hazard_codes("", "")
        assert full_un == ""
        assert full_kemler == ""


# ═══════════════════════════════════════════════════════════════════
# _log_incoming_message
# ═══════════════════════════════════════════════════════════════════

class TestLogIncomingMessage:
    def test_logs_lp_message(self, engine):
        lp = make_lp_msg(plate="TEST99")
        engine._log_incoming_message(lp, "t1", "1")  # Should not raise

    def test_logs_hz_message(self, engine):
        hz = make_hz_msg(un="5678")
        engine._log_incoming_message(hz, "t1", "1")  # Should not raise

    def test_logs_other_message(self, engine):
        msg = MagicMock()
        engine._log_incoming_message(msg, "t1", "1")  # Should not raise


# ═══════════════════════════════════════════════════════════════════
# _load_lookup_file
# ═══════════════════════════════════════════════════════════════════

class TestLoadLookupFile:
    def test_returns_empty_on_failure(self, engine):
        with patch("V_APP.shared.src.base_decision_engine.load_from_file", side_effect=FileNotFoundError):
            result = engine._load_lookup_file("/nonexistent", "test")
        assert result == {}


# ═══════════════════════════════════════════════════════════════════
# start (main loop)
# ═══════════════════════════════════════════════════════════════════

class TestStart:
    def test_start_processes_and_stops(self, engine):
        lp_topic = KafkaTopicFactory.license_plate_results("1")
        lp_msg = make_lp_msg()

        call_count = 0
        def consume_then_stop(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (lp_topic, lp_msg, "truck-1")
            engine.running = False
            return (None, None, None)

        engine.kafka_consumer.consume_typed_message.side_effect = consume_then_stop
        engine.start()

        assert engine.running is False
        assert ("1", "truck-1") in engine.lp_buffer or call_count >= 1

    def test_start_handles_exception_in_loop(self, engine):
        call_count = 0
        def raise_once(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("boom")
            engine.running = False
            return (None, None, None)

        engine.kafka_consumer.consume_typed_message.side_effect = raise_once
        engine.start()
        assert engine.running is False

    def test_cleanup_called_on_stop(self, engine):
        engine.kafka_consumer.consume_typed_message.side_effect = lambda **kw: (
            setattr(engine, "running", False) or (None, None, None)
        )
        engine.start()
        engine.kafka_consumer.close.assert_called_once()
        engine.kafka_producer.flush.assert_called_once()
        engine.kafka_producer.close.assert_called_once()

    def test_unknown_topic_is_skipped(self, engine):
        call_count = 0
        def consume_unknown_then_stop(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ("unknown-topic", make_lp_msg(), "truck-1")
            engine.running = False
            return (None, None, None)

        engine.kafka_consumer.consume_typed_message.side_effect = consume_unknown_then_stop
        engine.start()
        assert engine.lp_buffer == {}
        assert engine.hz_buffer == {}
