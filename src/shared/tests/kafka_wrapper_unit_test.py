"""
Unit tests for shared/src/kafka_wrapper.py

Tests cover:
- KafkaProducerWrapper: initialization, message production, callbacks, flush
- KafkaConsumerWrapper: initialization, message consumption, parsing, header extraction

All Kafka client calls are mocked.
"""

import pytest
import json
from unittest.mock import patch, MagicMock, call


# =============================================================================
# Tests for KafkaProducerWrapper
# =============================================================================

class TestKafkaProducerWrapper:
    """Tests for the Kafka producer wrapper."""

    def test_initialization_creates_producer(self):
        """Initialization creates confluent_kafka Producer."""
        # Arrange & Act
        with patch("kafka_wrapper.Producer") as MockProducer:
            from kafka_wrapper import KafkaProducerWrapper
            
            wrapper = KafkaProducerWrapper("localhost:9092")

            # Assert
            MockProducer.assert_called_once()
            call_config = MockProducer.call_args[0][0]
            assert call_config["bootstrap.servers"] == "localhost:9092"

    def test_produce_encodes_data_as_json(self):
        """Produce method JSON-encodes the data."""
        # Arrange
        with patch("kafka_wrapper.Producer") as MockProducer:
            mock_producer = MagicMock()
            MockProducer.return_value = mock_producer
            
            from kafka_wrapper import KafkaProducerWrapper
            wrapper = KafkaProducerWrapper("localhost:9092")
            data = {"key": "value", "number": 42}

            # Act
            wrapper.produce("test-topic", data)

            # Assert
            mock_producer.produce.assert_called_once()
            call_kwargs = mock_producer.produce.call_args[1]
            assert call_kwargs["topic"] == "test-topic"
            assert call_kwargs["value"] == json.dumps(data).encode("utf-8")

    def test_produce_includes_key_and_headers(self):
        """Produce includes optional key and headers."""
        # Arrange
        with patch("kafka_wrapper.Producer") as MockProducer:
            mock_producer = MagicMock()
            MockProducer.return_value = mock_producer
            
            from kafka_wrapper import KafkaProducerWrapper
            wrapper = KafkaProducerWrapper("localhost:9092")

            # Act
            wrapper.produce(
                "test-topic",
                {"data": "test"},
                key="msg-key",
                headers={"truckId": "T123"}
            )

            # Assert
            call_kwargs = mock_producer.produce.call_args[1]
            assert call_kwargs["key"] == "msg-key"
            assert call_kwargs["headers"] == {"truckId": "T123"}

    def test_produce_polls_after_send(self):
        """Produce calls poll(0) to trigger callbacks."""
        # Arrange
        with patch("kafka_wrapper.Producer") as MockProducer:
            mock_producer = MagicMock()
            MockProducer.return_value = mock_producer
            
            from kafka_wrapper import KafkaProducerWrapper
            wrapper = KafkaProducerWrapper("localhost:9092")

            # Act
            wrapper.produce("topic", {"test": "data"})

            # Assert
            mock_producer.poll.assert_called_once_with(0)

    def test_produce_handles_exception(self):
        """Produce handles exception gracefully."""
        # Arrange
        with patch("kafka_wrapper.Producer") as MockProducer:
            mock_producer = MagicMock()
            MockProducer.return_value = mock_producer
            mock_producer.produce.side_effect = Exception("Kafka error")
            
            from kafka_wrapper import KafkaProducerWrapper
            wrapper = KafkaProducerWrapper("localhost:9092")

            # Act - should not raise
            wrapper.produce("topic", {"test": "data"})

            # Assert - no exception raised

    def test_flush_calls_producer_flush(self):
        """Flush method calls producer flush with timeout."""
        # Arrange
        with patch("kafka_wrapper.Producer") as MockProducer:
            mock_producer = MagicMock()
            MockProducer.return_value = mock_producer
            
            from kafka_wrapper import KafkaProducerWrapper
            wrapper = KafkaProducerWrapper("localhost:9092")

            # Act
            wrapper.flush(timeout=5)

            # Assert
            mock_producer.flush.assert_called_once_with(5)

    def test_delivery_callback_logs_error(self):
        """Delivery callback logs errors and successes."""
        # Arrange
        with patch("kafka_wrapper.Producer") as MockProducer:
            mock_producer = MagicMock()
            MockProducer.return_value = mock_producer
            
            from kafka_wrapper import KafkaProducerWrapper
            wrapper = KafkaProducerWrapper("localhost:9092")
            
            mock_msg = MagicMock()
            mock_msg.topic.return_value = "test-topic"

            # Act - test error case
            wrapper._delivery_callback("Error occurred", mock_msg)

            # Act - test success case
            wrapper._delivery_callback(None, mock_msg)

            # Assert - no exceptions raised, logging happens internally


# =============================================================================
# Tests for KafkaConsumerWrapper
# =============================================================================

class TestKafkaConsumerWrapper:
    """Tests for the Kafka consumer wrapper."""

    def test_initialization_creates_consumer(self):
        """Initialization creates consumer with correct config."""
        # Arrange & Act
        with patch("kafka_wrapper.Consumer") as MockConsumer:
            mock_consumer = MagicMock()
            MockConsumer.return_value = mock_consumer
            
            from kafka_wrapper import KafkaConsumerWrapper
            wrapper = KafkaConsumerWrapper(
                "localhost:9092",
                "test-group",
                ["topic1", "topic2"]
            )

            # Assert
            MockConsumer.assert_called_once()
            call_config = MockConsumer.call_args[0][0]
            assert call_config["bootstrap.servers"] == "localhost:9092"
            assert call_config["group.id"] == "test-group"
            mock_consumer.subscribe.assert_called_once_with(["topic1", "topic2"])

    def test_consume_message_returns_message(self):
        """consume_message returns valid message."""
        # Arrange
        with patch("kafka_wrapper.Consumer") as MockConsumer:
            mock_consumer = MagicMock()
            MockConsumer.return_value = mock_consumer
            
            mock_msg = MagicMock()
            mock_msg.error.return_value = None
            mock_msg.topic.return_value = "test-topic"
            mock_consumer.poll.return_value = mock_msg
            
            from kafka_wrapper import KafkaConsumerWrapper
            wrapper = KafkaConsumerWrapper("localhost:9092", "group", ["topic"])

            # Act
            result = wrapper.consume_message(timeout=1.0)

            # Assert
            assert result == mock_msg
            mock_consumer.poll.assert_called_once_with(timeout=1.0)

    def test_consume_message_returns_none_on_timeout(self):
        """consume_message returns None on timeout."""
        # Arrange
        with patch("kafka_wrapper.Consumer") as MockConsumer:
            mock_consumer = MagicMock()
            MockConsumer.return_value = mock_consumer
            mock_consumer.poll.return_value = None
            
            from kafka_wrapper import KafkaConsumerWrapper
            wrapper = KafkaConsumerWrapper("localhost:9092", "group", ["topic"])

            # Act
            result = wrapper.consume_message()

            # Assert
            assert result is None

    def test_consume_message_returns_none_on_error(self):
        """consume_message returns None when message has error."""
        # Arrange
        with patch("kafka_wrapper.Consumer") as MockConsumer:
            mock_consumer = MagicMock()
            MockConsumer.return_value = mock_consumer
            
            mock_msg = MagicMock()
            mock_msg.error.return_value = MagicMock()  # Has error
            mock_consumer.poll.return_value = mock_msg
            
            from kafka_wrapper import KafkaConsumerWrapper
            wrapper = KafkaConsumerWrapper("localhost:9092", "group", ["topic"])

            # Act
            result = wrapper.consume_message()

            # Assert
            assert result is None

    def test_clear_stale_messages_drains_queue(self):
        """clear_stale_messages removes all pending messages."""
        # Arrange
        with patch("kafka_wrapper.Consumer") as MockConsumer:
            mock_consumer = MagicMock()
            MockConsumer.return_value = mock_consumer
            
            # Return 3 messages then None
            mock_msg = MagicMock()
            mock_msg.error.return_value = None
            mock_consumer.poll.side_effect = [mock_msg, mock_msg, mock_msg, None]
            
            from kafka_wrapper import KafkaConsumerWrapper
            wrapper = KafkaConsumerWrapper("localhost:9092", "group", ["topic"])

            # Act
            count = wrapper.clear_stale_messages()

            # Assert
            assert count == 3

    def test_clear_stale_messages_handles_errors(self):
        """clear_stale_messages continues on message errors."""
        # Arrange
        with patch("kafka_wrapper.Consumer") as MockConsumer:
            mock_consumer = MagicMock()
            MockConsumer.return_value = mock_consumer
            
            # Return error message, then valid, then None
            error_msg = MagicMock()
            error_msg.error.return_value = MagicMock()
            valid_msg = MagicMock()
            valid_msg.error.return_value = None
            
            mock_consumer.poll.side_effect = [error_msg, valid_msg, None]
            
            from kafka_wrapper import KafkaConsumerWrapper
            wrapper = KafkaConsumerWrapper("localhost:9092", "group", ["topic"])

            # Act
            count = wrapper.clear_stale_messages()

            # Assert
            assert count == 1  # Only valid message counted

    def test_parse_message_extracts_data(self):
        """parse_message extracts topic, data, and truck_id."""
        # Arrange
        with patch("kafka_wrapper.Consumer") as MockConsumer:
            mock_consumer = MagicMock()
            MockConsumer.return_value = mock_consumer
            
            mock_msg = MagicMock()
            mock_msg.error.return_value = None
            mock_msg.topic.return_value = "test-topic"
            mock_msg.value.return_value = json.dumps({"key": "value"}).encode()
            mock_msg.headers.return_value = [("truckId", b"TRUCK123")]
            
            from kafka_wrapper import KafkaConsumerWrapper
            wrapper = KafkaConsumerWrapper("localhost:9092", "group", ["topic"])

            # Act
            topic, data, truck_id = wrapper.parse_message(mock_msg)

            # Assert
            assert topic == "test-topic"
            assert data == {"key": "value"}
            assert truck_id == "TRUCK123"

    def test_parse_message_returns_none_for_none_message(self):
        """parse_message returns (None, None, None) for None message."""
        # Arrange
        with patch("kafka_wrapper.Consumer") as MockConsumer:
            mock_consumer = MagicMock()
            MockConsumer.return_value = mock_consumer
            
            from kafka_wrapper import KafkaConsumerWrapper
            wrapper = KafkaConsumerWrapper("localhost:9092", "group", ["topic"])

            # Act
            topic, data, truck_id = wrapper.parse_message(None)

            # Assert
            assert topic is None
            assert data is None
            assert truck_id is None

    def test_parse_message_returns_none_on_error(self):
        """parse_message returns (None, None, None) when message has error."""
        # Arrange
        with patch("kafka_wrapper.Consumer") as MockConsumer:
            mock_consumer = MagicMock()
            MockConsumer.return_value = mock_consumer
            
            mock_msg = MagicMock()
            mock_msg.error.return_value = MagicMock()
            
            from kafka_wrapper import KafkaConsumerWrapper
            wrapper = KafkaConsumerWrapper("localhost:9092", "group", ["topic"])

            # Act
            topic, data, truck_id = wrapper.parse_message(mock_msg)

            # Assert
            assert topic is None
            assert data is None
            assert truck_id is None

    def test_parse_message_handles_invalid_json(self):
        """parse_message handles invalid JSON gracefully."""
        # Arrange
        with patch("kafka_wrapper.Consumer") as MockConsumer:
            mock_consumer = MagicMock()
            MockConsumer.return_value = mock_consumer
            
            mock_msg = MagicMock()
            mock_msg.error.return_value = None
            mock_msg.value.return_value = b"not valid json"
            
            from kafka_wrapper import KafkaConsumerWrapper
            wrapper = KafkaConsumerWrapper("localhost:9092", "group", ["topic"])

            # Act
            topic, data, truck_id = wrapper.parse_message(mock_msg)

            # Assert
            assert topic is None
            assert data is None
            assert truck_id is None

    def test_parse_message_handles_missing_truck_id(self):
        """parse_message returns None for missing truck_id header."""
        # Arrange
        with patch("kafka_wrapper.Consumer") as MockConsumer:
            mock_consumer = MagicMock()
            MockConsumer.return_value = mock_consumer
            
            mock_msg = MagicMock()
            mock_msg.error.return_value = None
            mock_msg.value.return_value = json.dumps({"key": "value"}).encode()
            mock_msg.headers.return_value = [("other_header", b"value")]
            
            from kafka_wrapper import KafkaConsumerWrapper
            wrapper = KafkaConsumerWrapper("localhost:9092", "group", ["topic"])

            # Act
            topic, data, truck_id = wrapper.parse_message(mock_msg)

            # Assert
            assert topic is None
            assert data is None
            assert truck_id is None

    def test_extract_truck_id_accepts_truck_id_key(self):
        """_extract_truck_id_from_headers accepts 'truck_id' key."""
        # Arrange
        with patch("kafka_wrapper.Consumer") as MockConsumer:
            mock_consumer = MagicMock()
            MockConsumer.return_value = mock_consumer
            
            from kafka_wrapper import KafkaConsumerWrapper
            wrapper = KafkaConsumerWrapper("localhost:9092", "group", ["topic"])
            headers = [("truck_id", b"TRUCK456")]

            # Act
            result = wrapper._extract_truck_id_from_headers(headers)

            # Assert
            assert result == "TRUCK456"

    def test_extract_truck_id_accepts_truckId_key(self):
        """_extract_truck_id_from_headers accepts 'truckId' key."""
        # Arrange
        with patch("kafka_wrapper.Consumer") as MockConsumer:
            mock_consumer = MagicMock()
            MockConsumer.return_value = mock_consumer
            
            from kafka_wrapper import KafkaConsumerWrapper
            wrapper = KafkaConsumerWrapper("localhost:9092", "group", ["topic"])
            headers = [("truckId", b"TRUCK789")]

            # Act
            result = wrapper._extract_truck_id_from_headers(headers)

            # Assert
            assert result == "TRUCK789"

    def test_extract_truck_id_handles_string_value(self):
        """_extract_truck_id_from_headers handles string values."""
        # Arrange
        with patch("kafka_wrapper.Consumer") as MockConsumer:
            mock_consumer = MagicMock()
            MockConsumer.return_value = mock_consumer
            
            from kafka_wrapper import KafkaConsumerWrapper
            wrapper = KafkaConsumerWrapper("localhost:9092", "group", ["topic"])
            headers = [("truckId", "STRING-TRUCK")]  # String, not bytes

            # Act
            result = wrapper._extract_truck_id_from_headers(headers)

            # Assert
            assert result == "STRING-TRUCK"

    def test_extract_truck_id_returns_none_for_empty_headers(self):
        """_extract_truck_id_from_headers returns None for empty headers."""
        # Arrange
        with patch("kafka_wrapper.Consumer") as MockConsumer:
            mock_consumer = MagicMock()
            MockConsumer.return_value = mock_consumer
            
            from kafka_wrapper import KafkaConsumerWrapper
            wrapper = KafkaConsumerWrapper("localhost:9092", "group", ["topic"])

            # Act
            result = wrapper._extract_truck_id_from_headers([])

            # Assert
            assert result is None

    def test_extract_truck_id_returns_none_for_none_headers(self):
        """_extract_truck_id_from_headers returns None for None headers."""
        # Arrange
        with patch("kafka_wrapper.Consumer") as MockConsumer:
            mock_consumer = MagicMock()
            MockConsumer.return_value = mock_consumer
            
            from kafka_wrapper import KafkaConsumerWrapper
            wrapper = KafkaConsumerWrapper("localhost:9092", "group", ["topic"])

            # Act
            result = wrapper._extract_truck_id_from_headers(None)

            # Assert
            assert result is None

    def test_close_calls_consumer_close(self):
        """close method calls consumer close."""
        # Arrange
        with patch("kafka_wrapper.Consumer") as MockConsumer:
            mock_consumer = MagicMock()
            MockConsumer.return_value = mock_consumer
            
            from kafka_wrapper import KafkaConsumerWrapper
            wrapper = KafkaConsumerWrapper("localhost:9092", "group", ["topic"])

            # Act
            wrapper.close()

            # Assert
            mock_consumer.close.assert_called_once()
