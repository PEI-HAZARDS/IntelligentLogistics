"""
Unit tests for shared/src/base_gateway.py

Tests cover:
- BaseGateway initialization and configuration
- FastAPI endpoints (/health, /receive_message)
- Message forwarding to receiver gateways
- Kafka consumer loop
- Lifecycle: start / stop

Since BaseGateway is abstract, we create a ConcreteTestGateway subclass for testing.
All external dependencies (Kafka, HTTP, uvicorn) are mocked.
"""

import pytest
import json
import threading
from unittest.mock import patch, MagicMock, PropertyMock, call
from fastapi.testclient import TestClient


# =============================================================================
# Concrete test implementation of BaseGateway
# =============================================================================

def create_test_gateway(
    kafka_producer=None,
    kafka_consumer=None,
    config_overrides=None,
):
    """Create a concrete test gateway with mocked dependencies."""
    from base_gateway import BaseGateway, BaseGatewayConfig

    class ConcreteTestGateway(BaseGateway):
        def get_topics_consume(self):
            return ["topic-a", "topic-b"]

        def get_topics_produce(self):
            return {
                "topic-a": "local-topic-a",
                "truck_detected": "local-truck-detected",
            }

        def get_gateway_name(self):
            return "TestGateway"

        def get_receivers(self):
            return ["http://receiver1:8000", "http://receiver2:8000"]

        def process_message(self, message):
            return message

    defaults = {
        "kafka_bootstrap": "localhost:9092",
        "gate_ids": ["1"],
        "gateway_port": 8000,
        "gateway_host": "0.0.0.0",
        "receivers": ["http://receiver1:8000"],
    }
    if config_overrides:
        defaults.update(config_overrides)

    config = BaseGatewayConfig(**defaults)

    kafka_producer = kafka_producer or MagicMock()
    kafka_consumer = kafka_consumer or MagicMock()

    return ConcreteTestGateway(
        config=config,
        kafka_producer=kafka_producer,
        kafka_consumer=kafka_consumer,
    )


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_producer():
    return MagicMock()


@pytest.fixture
def mock_consumer():
    return MagicMock()


@pytest.fixture
def gateway(mock_producer, mock_consumer):
    return create_test_gateway(
        kafka_producer=mock_producer,
        kafka_consumer=mock_consumer,
    )


@pytest.fixture
def client(gateway):
    """FastAPI test client for the gateway app."""
    return TestClient(gateway.app)


# =============================================================================
# Tests for __init__
# =============================================================================

class TestBaseGatewayInit:
    """Tests for BaseGateway initialization."""

    def test_initialization_sets_attributes(self, gateway, mock_producer, mock_consumer):
        """Init sets config, logger, kafka, and app."""
        assert gateway.gateway_name == "TestGateway"
        assert gateway.topics_consume == ["topic-a", "topic-b"]
        assert gateway.receivers == ["http://receiver1:8000", "http://receiver2:8000"]
        assert gateway.kafka_producer is mock_producer
        assert gateway.kafka_consumer is mock_consumer
        assert gateway.running is False
        assert gateway.app is not None

    def test_initialization_creates_default_kafka_when_not_provided(self):
        """Init creates Kafka producer/consumer when not injected."""
        from base_gateway import BaseGateway, BaseGatewayConfig

        class MinimalGateway(BaseGateway):
            def get_topics_consume(self):
                return ["t"]
            def get_topics_produce(self):
                return {}
            def get_gateway_name(self):
                return "Minimal"
            def get_receivers(self):
                return []
            def process_message(self, message):
                return message

        config = BaseGatewayConfig(kafka_bootstrap="localhost:9092")

        with patch("base_gateway.KafkaProducerWrapper") as MockProd, \
             patch("base_gateway.KafkaConsumerWrapper") as MockCons:
            gw = MinimalGateway(config=config)

            MockProd.assert_called_once_with("localhost:9092")
            MockCons.assert_called_once_with("localhost:9092", "minimal-group", ["t"])


# =============================================================================
# Tests for /health endpoint
# =============================================================================

class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_degraded_when_no_consumer_thread(self, client):
        """Health returns degraded when consumer thread is not running."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["consumer_alive"] is False

    def test_health_ok_when_consumer_thread_alive(self, gateway, client):
        """Health returns ok when consumer thread is alive."""
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        gateway._consumer_thread = mock_thread

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["consumer_alive"] is True

    def test_health_degraded_when_consumer_thread_dead(self, gateway, client):
        """Health returns degraded when consumer thread has died."""
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = False
        gateway._consumer_thread = mock_thread

        response = client.get("/health")
        data = response.json()
        assert data["status"] == "degraded"
        assert data["consumer_alive"] is False


# =============================================================================
# Tests for /receive_message endpoint
# =============================================================================

class TestReceiveMessageEndpoint:
    """Tests for the /receive_message endpoint."""

    def test_receive_valid_message_produces_to_kafka(self, gateway, client, mock_producer):
        """Valid message is deserialized, routed, and produced to Kafka."""
        payload = {
            "message_type": "truck_detected",
            "confidence": 0.9,
            "num_detections": 3,
            "timestamp": 1000,
        }

        response = client.post(
            "/receive_message",
            json=payload,
            headers={"X-Truck-ID": "TRUCK-1", "X-Source-Topic": "topic-a"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "local-topic-a" in data["message"]

        mock_producer.produce.assert_called_once()
        call_kwargs = mock_producer.produce.call_args
        assert call_kwargs.args[0] == "local-topic-a"
        assert call_kwargs.kwargs["headers"] == {"truck_id": "TRUCK-1"}
        mock_producer.flush.assert_called_once()

    def test_receive_message_routes_by_message_type_fallback(self, gateway, client, mock_producer):
        """Falls back to message_type routing when X-Source-Topic is absent."""
        payload = {
            "message_type": "truck_detected",
            "confidence": 0.8,
            "num_detections": 1,
            "timestamp": 2000,
        }

        response = client.post("/receive_message", json=payload)

        assert response.status_code == 200
        call_args = mock_producer.produce.call_args
        assert call_args.args[0] == "local-truck-detected"

    def test_receive_message_no_truck_id_header(self, gateway, client, mock_producer):
        """Message without X-Truck-ID produces with no kafka headers."""
        payload = {
            "message_type": "truck_detected",
            "confidence": 0.5,
            "num_detections": 1,
            "timestamp": 3000,
        }

        response = client.post(
            "/receive_message",
            json=payload,
            headers={"X-Source-Topic": "topic-a"},
        )

        assert response.status_code == 200
        call_kwargs = mock_producer.produce.call_args.kwargs
        assert call_kwargs["headers"] is None

    def test_receive_message_invalid_json_returns_400(self, gateway, client):
        """Non-JSON body returns 400."""
        response = client.post(
            "/receive_message",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid JSON body"

    def test_receive_message_invalid_message_type_returns_400(self, gateway, client):
        """Unknown message_type returns 400."""
        payload = {"message_type": "unknown_type", "data": "test"}

        response = client.post("/receive_message", json=payload)

        assert response.status_code == 400
        assert "error" in response.json()["status"]

    def test_receive_message_no_topic_mapping_returns_400(self, gateway, client):
        """Message with valid type but unmapped topic returns 400."""
        payload = {
            "message_type": "license_plate_results",
            "license_plate": "ABC123",
            "crop_url": "http://example.com/crop.jpg",
            "confidence": 0.95,
            "timestamp": 4000,
        }

        response = client.post("/receive_message", json=payload)

        assert response.status_code == 400
        assert "No topic" in response.json()["detail"]

    def test_receive_message_source_topic_takes_priority(self, gateway, client, mock_producer):
        """X-Source-Topic takes priority over message_type for routing."""
        payload = {
            "message_type": "truck_detected",
            "confidence": 0.9,
            "num_detections": 2,
            "timestamp": 5000,
        }

        response = client.post(
            "/receive_message",
            json=payload,
            headers={"X-Source-Topic": "topic-a"},
        )

        assert response.status_code == 200
        # Should route to local-topic-a (from source topic), not local-truck-detected
        call_args = mock_producer.produce.call_args
        assert call_args.args[0] == "local-topic-a"


# =============================================================================
# Tests for _forward_to_recievers
# =============================================================================

class TestForwardToReceivers:
    """Tests for message forwarding to receiver gateways."""

    def test_forwards_to_all_receivers(self, gateway):
        """Message is POSTed to every receiver."""
        mock_message = MagicMock()
        mock_message.to_dict.return_value = {"message_type": "test", "data": "value"}
        mock_message.MESSAGE_TYPE = "test"

        with patch.object(gateway._http_client, "post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            gateway._forward_to_recievers(mock_message, truck_id="T1", source_topic="topic-a")

            assert mock_post.call_count == 2
            calls = mock_post.call_args_list
            assert calls[0].args[0] == "http://receiver1:8000/receive_message"
            assert calls[1].args[0] == "http://receiver2:8000/receive_message"

    def test_includes_truck_id_and_source_topic_headers(self, gateway):
        """HTTP headers include X-Truck-ID and X-Source-Topic."""
        mock_message = MagicMock()
        mock_message.to_dict.return_value = {"data": "value"}
        mock_message.MESSAGE_TYPE = "test"

        with patch.object(gateway._http_client, "post") as mock_post:
            mock_post.return_value = MagicMock()

            gateway._forward_to_recievers(mock_message, truck_id="TRUCK-42", source_topic="src-topic")

            headers = mock_post.call_args_list[0].kwargs["headers"]
            assert headers["X-Truck-ID"] == "TRUCK-42"
            assert headers["X-Source-Topic"] == "src-topic"

    def test_omits_headers_when_none(self, gateway):
        """No X-Truck-ID or X-Source-Topic when values are None."""
        mock_message = MagicMock()
        mock_message.to_dict.return_value = {"data": "value"}
        mock_message.MESSAGE_TYPE = "test"

        with patch.object(gateway._http_client, "post") as mock_post:
            mock_post.return_value = MagicMock()

            gateway._forward_to_recievers(mock_message)

            headers = mock_post.call_args_list[0].kwargs["headers"]
            assert "X-Truck-ID" not in headers
            assert "X-Source-Topic" not in headers

    def test_handles_http_error_gracefully(self, gateway):
        """HTTP errors on one receiver don't prevent forwarding to others."""
        import httpx

        mock_message = MagicMock()
        mock_message.to_dict.return_value = {"data": "value"}
        mock_message.MESSAGE_TYPE = "test"

        with patch.object(gateway._http_client, "post") as mock_post:
            mock_post.side_effect = [
                httpx.HTTPError("Connection refused"),
                MagicMock(),  # second receiver succeeds
            ]

            # Should not raise
            gateway._forward_to_recievers(mock_message, truck_id="T1")

            assert mock_post.call_count == 2

    def test_handles_generic_exception_gracefully(self, gateway):
        """Generic exceptions don't crash the forwarding loop."""
        mock_message = MagicMock()
        mock_message.to_dict.return_value = {"data": "value"}
        mock_message.MESSAGE_TYPE = "test"

        with patch.object(gateway._http_client, "post") as mock_post:
            mock_post.side_effect = [
                RuntimeError("Something unexpected"),
                MagicMock(),
            ]

            gateway._forward_to_recievers(mock_message)

            assert mock_post.call_count == 2

    def test_adds_http_prefix_when_missing(self, gateway):
        """Receiver address without http:// gets prefix added."""
        mock_message = MagicMock()
        mock_message.to_dict.return_value = {"data": "value"}
        mock_message.MESSAGE_TYPE = "test"

        # Override receivers to have a bare address
        gateway.receivers = ["bare-host:9000"]

        with patch.object(gateway._http_client, "post") as mock_post:
            mock_post.return_value = MagicMock()

            gateway._forward_to_recievers(mock_message)

            assert mock_post.call_args.args[0] == "http://bare-host:9000/receive_message"


# =============================================================================
# Tests for _consumer_loop
# =============================================================================

class TestConsumerLoop:
    """Tests for the Kafka consumer loop."""

    def test_clears_stale_messages_on_start(self, gateway, mock_consumer):
        """Consumer loop clears stale messages before processing."""
        gateway.running = False  # Exit immediately
        gateway._consumer_loop()
        mock_consumer.clear_stale_messages.assert_called_once()

    def test_processes_and_forwards_valid_message(self, gateway, mock_consumer):
        """Consumer loop deserializes and forwards valid messages."""
        msg = MagicMock()
        payload = {
            "message_type": "truck_detected",
            "confidence": 0.9,
            "num_detections": 2,
            "timestamp": 1000,
        }
        mock_consumer.parse_message.return_value = ("topic-a", payload, "TRUCK-1")

        call_count = 0
        def consume_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                gateway.running = False
            return msg if call_count == 1 else None

        mock_consumer.consume_message.side_effect = consume_side_effect

        with patch.object(gateway, "_forward_to_recievers") as mock_forward:
            gateway.running = True
            gateway._consumer_loop()

            mock_forward.assert_called_once()
            forwarded_msg = mock_forward.call_args.args[0]
            assert forwarded_msg.confidence == 0.9
            assert mock_forward.call_args.kwargs["truck_id"] == "TRUCK-1"
            assert mock_forward.call_args.kwargs["source_topic"] == "topic-a"

    def test_skips_none_messages(self, gateway, mock_consumer):
        """Consumer loop skips when consume returns None (timeout)."""
        call_count = 0
        def consume_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                gateway.running = False
            return None

        mock_consumer.consume_message.side_effect = consume_side_effect

        with patch.object(gateway, "_forward_to_recievers") as mock_forward:
            gateway.running = True
            gateway._consumer_loop()

            mock_forward.assert_not_called()

    def test_skips_when_parse_returns_none_data(self, gateway, mock_consumer):
        """Consumer loop skips when parse_message returns None data."""
        msg = MagicMock()
        call_count = 0
        def consume_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                gateway.running = False
            return msg if call_count == 1 else None

        mock_consumer.consume_message.side_effect = consume_side_effect
        mock_consumer.parse_message.return_value = (None, None, None)

        with patch.object(gateway, "_forward_to_recievers") as mock_forward:
            gateway.running = True
            gateway._consumer_loop()

            mock_forward.assert_not_called()

    def test_skips_when_deserialization_fails(self, gateway, mock_consumer):
        """Consumer loop skips messages that fail deserialization."""
        msg = MagicMock()
        call_count = 0
        def consume_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                gateway.running = False
            return msg if call_count == 1 else None

        mock_consumer.consume_message.side_effect = consume_side_effect
        mock_consumer.parse_message.return_value = ("topic-a", {"message_type": "invalid"}, "T1")

        with patch.object(gateway, "_forward_to_recievers") as mock_forward:
            gateway.running = True
            gateway._consumer_loop()

            mock_forward.assert_not_called()

    def test_skips_when_process_message_returns_none(self, gateway, mock_consumer):
        """Consumer loop drops messages when process_message returns None."""
        msg = MagicMock()
        payload = {
            "message_type": "truck_detected",
            "confidence": 0.9,
            "num_detections": 1,
            "timestamp": 1000,
        }
        call_count = 0
        def consume_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                gateway.running = False
            return msg if call_count == 1 else None

        mock_consumer.consume_message.side_effect = consume_side_effect
        mock_consumer.parse_message.return_value = ("topic-a", payload, "T1")
        gateway.process_message = MagicMock(return_value=None)

        with patch.object(gateway, "_forward_to_recievers") as mock_forward:
            gateway.running = True
            gateway._consumer_loop()

            mock_forward.assert_not_called()

    def test_loop_crash_sets_running_false_and_reraises(self, gateway, mock_consumer):
        """Unhandled exception in consumer loop sets running=False and re-raises."""
        gateway.running = True
        mock_consumer.consume_message.side_effect = RuntimeError("Fatal")

        with pytest.raises(RuntimeError, match="Fatal"):
            gateway._consumer_loop()

        assert gateway.running is False


# =============================================================================
# Tests for start
# =============================================================================

class TestStart:
    """Tests for the gateway start lifecycle."""

    def test_start_spawns_consumer_thread_and_runs_uvicorn(self, gateway):
        """start() sets running, spawns consumer thread, and runs uvicorn."""
        with patch("base_gateway.uvicorn") as mock_uvicorn:
            mock_uvicorn.run = MagicMock()

            # Mock the consumer thread to not actually run
            with patch("base_gateway.threading.Thread") as MockThread:
                mock_thread = MagicMock()
                MockThread.return_value = mock_thread

                gateway.start()

                # running is False after stop() in finally block
                MockThread.assert_called_once()
                assert MockThread.call_args.kwargs["daemon"] is True
                mock_thread.start.assert_called_once()
                mock_uvicorn.run.assert_called_once()

    def test_start_handles_keyboard_interrupt(self, gateway):
        """start() handles KeyboardInterrupt and calls stop()."""
        with patch("base_gateway.uvicorn") as mock_uvicorn, \
             patch("base_gateway.threading.Thread") as MockThread, \
             patch.object(gateway, "stop") as mock_stop:
            mock_uvicorn.run.side_effect = KeyboardInterrupt()
            MockThread.return_value = MagicMock()

            gateway.start()

            mock_stop.assert_called_once()

    def test_start_calls_stop_on_normal_exit(self, gateway):
        """start() calls stop() in the finally block on normal exit."""
        with patch("base_gateway.uvicorn") as mock_uvicorn, \
             patch("base_gateway.threading.Thread") as MockThread, \
             patch.object(gateway, "stop") as mock_stop:
            mock_uvicorn.run = MagicMock()
            MockThread.return_value = MagicMock()

            gateway.start()

            mock_stop.assert_called_once()


# =============================================================================
# Tests for stop
# =============================================================================

class TestStop:
    """Tests for the gateway stop lifecycle."""

    def test_stop_sets_running_false(self, gateway):
        """stop() sets running to False."""
        gateway.running = True
        gateway.stop()
        assert gateway.running is False

    def test_stop_joins_consumer_thread(self, gateway):
        """stop() joins the consumer thread if alive."""
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        gateway._consumer_thread = mock_thread
        gateway.running = True

        gateway.stop()

        mock_thread.join.assert_called_once_with(timeout=5)

    def test_stop_skips_join_when_thread_dead(self, gateway):
        """stop() doesn't join if consumer thread is not alive."""
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = False
        gateway._consumer_thread = mock_thread
        gateway.running = True

        gateway.stop()

        mock_thread.join.assert_not_called()

    def test_stop_skips_join_when_no_thread(self, gateway):
        """stop() handles None consumer thread."""
        gateway._consumer_thread = None
        gateway.running = True

        # Should not raise
        gateway.stop()

    def test_stop_closes_kafka_and_http(self, gateway, mock_producer, mock_consumer):
        """stop() flushes/closes kafka producer, consumer, and HTTP client."""
        gateway.running = True

        with patch.object(gateway._http_client, "close") as mock_http_close:
            gateway.stop()

            mock_consumer.close.assert_called_once()
            mock_producer.flush.assert_called_once()
            mock_producer.close.assert_called_once()
            mock_http_close.assert_called_once()


# =============================================================================
# Tests for BaseGatewayConfig
# =============================================================================

class TestBaseGatewayConfig:
    """Tests for the configuration model."""

    def test_config_defaults(self):
        """Config uses sane defaults."""
        from base_gateway import BaseGatewayConfig

        config = BaseGatewayConfig(kafka_bootstrap="localhost:9092")

        assert config.kafka_bootstrap == "localhost:9092"
        assert config.gate_ids == ["1"]
        assert config.gateway_port == 8000
        assert config.gateway_host == "0.0.0.0"
        assert config.receivers == [""]

    def test_config_custom_values(self):
        """Config accepts custom values."""
        from base_gateway import BaseGatewayConfig

        config = BaseGatewayConfig(
            kafka_bootstrap="kafka:9093",
            gate_ids=["1", "2"],
            gateway_port=9090,
            gateway_host="127.0.0.1",
            receivers=["http://gw1:8000", "http://gw2:8000"],
        )

        assert config.kafka_bootstrap == "kafka:9093"
        assert config.gate_ids == ["1", "2"]
        assert config.gateway_port == 9090
        assert config.gateway_host == "127.0.0.1"
        assert config.receivers == ["http://gw1:8000", "http://gw2:8000"]
