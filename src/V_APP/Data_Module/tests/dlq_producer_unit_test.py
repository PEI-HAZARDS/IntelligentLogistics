"""Unit tests for DLQProducer."""

from unittest.mock import patch

from infrastructure.messaging.dlq_producer import DLQProducer


@patch("infrastructure.messaging.dlq_producer.KafkaProducerWrapper")
def test_send_to_dlq_builds_expected_envelope(mock_wrapper_cls):
    mock_wrapper = mock_wrapper_cls.return_value
    producer = DLQProducer("kafka:29092")

    error = ValueError("bad payload")
    producer.send_to_dlq(
        source_topic="agent-decision-1",
        source_partition=2,
        source_offset=42,
        key="truck-abc",
        headers={"truckId": "truck-abc"},
        payload={"foo": "bar"},
        error=error,
        attempt_count=3,
    )

    assert mock_wrapper.produce.call_count == 1
    kwargs = mock_wrapper.produce.call_args.kwargs
    assert kwargs["topic"] == "agent-decision-1.DLQ"
    assert kwargs["key"] == "truck-abc"

    envelope = kwargs["data"]
    assert envelope["original_topic"] == "agent-decision-1"
    assert envelope["original_partition"] == 2
    assert envelope["original_offset"] == 42
    assert envelope["original_payload"] == {"foo": "bar"}
    assert envelope["error_class"] == "ValueError"
    assert envelope["error_message"] == "bad payload"
    assert envelope["attempt_count"] == 3
    assert envelope["service"] == DLQProducer.SERVICE_NAME
    assert envelope["stacktrace_hash"]


def test_permanent_error_classification():
    assert DLQProducer.is_permanent_error(ValueError("invalid")) is True
    assert DLQProducer.is_permanent_error(KeyError("missing")) is True
    assert DLQProducer.is_permanent_error(RuntimeError("temporary")) is False
