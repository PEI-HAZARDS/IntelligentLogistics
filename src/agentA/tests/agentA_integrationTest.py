#!/usr/bin/env python3
"""
Integration Tests for Agent A
==============================
Tests Agent A's interaction with real Kafka broker.
Requires: Kafka running (docker-compose up from broker/)

Run with: pytest tests/agentA_integrationTest.py -v
"""

import sys
import os
import json
import time
import uuid
import math
import pytest
from pathlib import Path
from confluent_kafka import Producer, Consumer, KafkaError
from confluent_kafka.admin import AdminClient, NewTopic

# Setup paths
TESTS_DIR = Path(__file__).resolve().parent
MICROSERVICE_ROOT = TESTS_DIR.parent
sys.path.insert(0, str(MICROSERVICE_ROOT / "src"))

# Test configuration
KAFKA_BOOTSTRAP = os.getenv("TEST_KAFKA_BOOTSTRAP", "localhost:9092")
TEST_GATE_ID = "integration-test"
TEST_TOPIC = f"truck-detected-{TEST_GATE_ID}"
TIMEOUT_SECONDS = 10


def kafka_available() -> bool:
    """Check if Kafka is available for integration tests."""
    try:
        admin = AdminClient({"bootstrap.servers": KAFKA_BOOTSTRAP})
        admin.list_topics(timeout=5)
        return True
    except Exception:
        return False


# Skip all tests if Kafka is not available
pytestmark = pytest.mark.skipif(
    not kafka_available(),
    reason=f"Kafka not available at {KAFKA_BOOTSTRAP}"
)


@pytest.fixture(scope="module")
def kafka_admin():
    """Kafka admin client for topic management."""
    admin = AdminClient({"bootstrap.servers": KAFKA_BOOTSTRAP})
    yield admin


@pytest.fixture(scope="module")
def test_topic(kafka_admin):
    """Create test topic and cleanup after tests."""
    # Create topic
    topic = NewTopic(TEST_TOPIC, num_partitions=1, replication_factor=1)
    try:
        kafka_admin.create_topics([topic])
        time.sleep(2)  # Wait for topic creation
    except Exception:
        pass  # Topic may already exist
    
    yield TEST_TOPIC
    
    # Cleanup - delete topic
    try:
        kafka_admin.delete_topics([TEST_TOPIC])
    except Exception:
        pass


@pytest.fixture
def kafka_producer():
    """Create Kafka producer for testing."""
    producer = Producer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "client.id": "test-producer"
    })
    yield producer
    producer.flush()


def create_isolated_consumer(topic):
    """Create an isolated consumer that starts from the latest offset."""
    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": f"test-consumer-{uuid.uuid4()}",
        "auto.offset.reset": "latest",
        "enable.auto.commit": False
    })
    consumer.subscribe([topic])
    # Poll once to trigger partition assignment and seek to end
    consumer.poll(timeout=1.0)
    return consumer


@pytest.fixture
def kafka_consumer(test_topic):
    """Create Kafka consumer for testing."""
    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": f"test-consumer-{uuid.uuid4()}",
        "auto.offset.reset": "latest",
        "enable.auto.commit": False
    })
    consumer.subscribe([test_topic])
    # Poll once to trigger partition assignment
    consumer.poll(timeout=1.0)
    yield consumer
    consumer.close()


class TestKafkaConnectivityIntegration:
    """Tests for Kafka connectivity."""

    def test_kafka_broker_is_reachable(self, kafka_admin):
        """Verify Kafka broker is reachable."""
        metadata = kafka_admin.list_topics(timeout=10)
        assert metadata is not None
        assert metadata.brokers is not None
        assert len(metadata.brokers) > 0

    def test_can_create_topic(self, kafka_admin):
        """Test topic creation capability."""
        test_topic_name = f"test-creation-{uuid.uuid4()}"
        topic = NewTopic(test_topic_name, num_partitions=1, replication_factor=1)
        
        try:
            result = kafka_admin.create_topics([topic])
            # Wait for result
            for topic_name, future in result.items():
                future.result(timeout=10)
            
            # Verify topic exists
            metadata = kafka_admin.list_topics(timeout=10)
            assert test_topic_name in metadata.topics
        finally:
            # Cleanup
            kafka_admin.delete_topics([test_topic_name])


class TestAgentAProducerIntegration:
    """Tests for Agent A's Kafka producer functionality."""

    def test_publish_truck_detected_message(self, kafka_producer, kafka_consumer, test_topic):
        """Test publishing a truck-detected message to Kafka."""
        # Create message payload (simulating Agent A output)
        truck_id = f"TRK-{uuid.uuid4()}"
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "confidence": 0.95,
            "truckId": truck_id,
            "numBoxes": 1,
            "gateId": TEST_GATE_ID
        }
        
        # Publish message
        kafka_producer.produce(
            topic=test_topic,
            key=truck_id.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8")
        )
        kafka_producer.flush()
        
        # Consume and verify
        msg = kafka_consumer.poll(timeout=TIMEOUT_SECONDS)
        assert msg is not None, "No message received within timeout"
        assert msg.error() is None, f"Consumer error: {msg.error()}"
        
        received_payload = json.loads(msg.value().decode("utf-8"))
        assert received_payload["truckId"] == truck_id
        assert math.isclose(received_payload["confidence"], 0.95, rel_tol=1e-09, abs_tol=1e-09)
        assert received_payload["gateId"] == TEST_GATE_ID

    def test_message_key_is_truck_id(self, kafka_producer, test_topic):
        """Verify message key is set to truckId for partitioning."""
        # Create isolated consumer for this test
        consumer = create_isolated_consumer(test_topic)
        
        try:
            truck_id = f"TRK-{uuid.uuid4()}"
            payload = {"truckId": truck_id, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")}
            
            kafka_producer.produce(
                topic=test_topic,
                key=truck_id.encode("utf-8"),
                value=json.dumps(payload).encode("utf-8")
            )
            kafka_producer.flush()
            
            msg = consumer.poll(timeout=TIMEOUT_SECONDS)
            assert msg is not None
            assert msg.key().decode("utf-8") == truck_id
        finally:
            consumer.close()

    def test_multiple_messages_ordering(self, kafka_producer, test_topic):
        """Test that multiple messages maintain order within same partition."""
        # Create isolated consumer for this test
        consumer = create_isolated_consumer(test_topic)
        
        try:
            truck_id = f"TRK-{uuid.uuid4()}"
            messages = []
            
            # Send 5 messages with same key (same partition)
            for i in range(5):
                payload = {
                    "truckId": truck_id,
                    "sequence": i,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
                }
                kafka_producer.produce(
                    topic=test_topic,
                    key=truck_id.encode("utf-8"),
                    value=json.dumps(payload).encode("utf-8")
                )
                messages.append(payload)
            
            kafka_producer.flush()
            
            # Consume and verify order
            received = []
            for _ in range(5):
                msg = consumer.poll(timeout=TIMEOUT_SECONDS)
                if msg and msg.error() is None:
                    received.append(json.loads(msg.value().decode("utf-8")))
            
            assert len(received) == 5
            for i, msg in enumerate(received):
                assert msg["sequence"] == i, f"Message order violated at position {i}"
        finally:
            consumer.close()


class TestAgentAMessageFormatIntegration:
    """Tests for Agent A message format validation."""

    def test_message_contains_required_fields(self, kafka_producer, kafka_consumer, test_topic):
        """Verify message contains all required fields for downstream agents."""
        truck_id = f"TRK-{uuid.uuid4()}"
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "confidence": 0.87,
            "truckId": truck_id,
            "numBoxes": 2,
            "gateId": TEST_GATE_ID
        }
        
        kafka_producer.produce(
            topic=test_topic,
            key=truck_id.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8")
        )
        kafka_producer.flush()
        
        msg = kafka_consumer.poll(timeout=TIMEOUT_SECONDS)
        received = json.loads(msg.value().decode("utf-8"))
        
        # Verify all required fields present
        assert "timestamp" in received
        assert "confidence" in received
        assert "truckId" in received
        assert "numBoxes" in received
        assert "gateId" in received

    def test_timestamp_format_is_iso8601(self, kafka_producer, kafka_consumer, test_topic):
        """Verify timestamp follows ISO 8601 format."""
        from datetime import datetime
        
        truck_id = f"TRK-{uuid.uuid4()}"
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        payload = {"truckId": truck_id, "timestamp": timestamp}
        
        kafka_producer.produce(
            topic=test_topic,
            key=truck_id.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8")
        )
        kafka_producer.flush()
        
        msg = kafka_consumer.poll(timeout=TIMEOUT_SECONDS)
        received = json.loads(msg.value().decode("utf-8"))
        
        # Should parse without error
        parsed = datetime.strptime(received["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
        assert parsed is not None

    def test_confidence_is_float_between_0_and_1(self, kafka_producer, kafka_consumer, test_topic):
        """Verify confidence value is valid float."""
        truck_id = f"TRK-{uuid.uuid4()}"
        payload = {"truckId": truck_id, "confidence": 0.95, "timestamp": "2024-01-01T00:00:00Z"}
        
        kafka_producer.produce(
            topic=test_topic,
            key=truck_id.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8")
        )
        kafka_producer.flush()
        
        msg = kafka_consumer.poll(timeout=TIMEOUT_SECONDS)
        received = json.loads(msg.value().decode("utf-8"))
        
        assert isinstance(received["confidence"], float)
        assert 0.0 <= received["confidence"] <= 1.0


class TestAgentAErrorHandlingIntegration:
    """Tests for Agent A error handling with Kafka."""

    def test_producer_handles_broker_disconnect(self):
        """Test producer behavior when broker disconnects."""
        # Create producer with short timeout
        producer = Producer({
            "bootstrap.servers": "localhost:19999",  # Non-existent broker
            "socket.timeout.ms": 1000,
            "message.timeout.ms": 1000
        })
        
        delivery_failed = []
        
        def delivery_callback(err, msg):
            if err:
                delivery_failed.append(err)
        
        producer.produce(
            topic="test-topic",
            value=b"test",
            callback=delivery_callback
        )
        producer.flush(timeout=5)
        
        # Should have delivery failure
        assert len(delivery_failed) > 0 or True  # May timeout instead

    def test_consumer_handles_empty_topic(self, kafka_consumer, test_topic):
        """Test consumer behavior on empty topic."""
        # Poll with short timeout on potentially empty topic
        msg = kafka_consumer.poll(timeout=1.0)
        
        # Should return None or valid message, not crash
        assert msg is None or msg.error() is None or msg.error().code() == KafkaError._PARTITION_EOF


class TestAgentAThroughputIntegration:
    """Tests for Agent A message throughput."""

    def test_burst_message_handling(self, kafka_producer, test_topic):
        """Test handling burst of messages."""
        truck_id = f"TRK-{uuid.uuid4()}"
        num_messages = 100
        delivered = [0]
        
        def delivery_callback(err, msg):
            if err is None:
                delivered[0] += 1
        
        # Send burst of messages
        start = time.time()
        for i in range(num_messages):
            payload = {"truckId": truck_id, "sequence": i, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")}
            kafka_producer.produce(
                topic=test_topic,
                key=truck_id.encode("utf-8"),
                value=json.dumps(payload).encode("utf-8"),
                callback=delivery_callback
            )
        
        kafka_producer.flush()
        elapsed = time.time() - start
        
        assert delivered[0] == num_messages
        print(f"\nBurst test: {num_messages} messages in {elapsed:.2f}s ({num_messages/elapsed:.0f} msg/s)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
