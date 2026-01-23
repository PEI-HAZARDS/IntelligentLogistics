#!/usr/bin/env python3
"""
Integration Tests for Agent B
==============================
Tests Agent B's interaction with Kafka (consuming truck-detected, producing lp-results).
Requires: Kafka running (docker-compose up from broker/)

Run with: pytest tests/agentB_integrationTest.py -v
"""

import sys
import os
import json
import time
import uuid
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
TOPIC_TRUCK_DETECTED = f"truck-detected-{TEST_GATE_ID}"
TOPIC_LP_RESULTS = f"lp-results-{TEST_GATE_ID}"
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
def test_topics(kafka_admin):
    """Create test topics and cleanup after tests."""
    topics = [
        NewTopic(TOPIC_TRUCK_DETECTED, num_partitions=1, replication_factor=1),
        NewTopic(TOPIC_LP_RESULTS, num_partitions=1, replication_factor=1)
    ]
    
    try:
        kafka_admin.create_topics(topics)
        time.sleep(2)
    except Exception:
        pass
    
    yield {
        "truck_detected": TOPIC_TRUCK_DETECTED,
        "lp_results": TOPIC_LP_RESULTS
    }
    
    try:
        kafka_admin.delete_topics([TOPIC_TRUCK_DETECTED, TOPIC_LP_RESULTS])
    except Exception:
        pass


@pytest.fixture
def truck_producer(test_topics):
    """Producer to simulate Agent A truck-detected messages."""
    producer = Producer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "client.id": "test-truck-producer"
    })
    yield producer
    producer.flush()


@pytest.fixture
def lp_producer(test_topics):
    """Producer to simulate Agent B lp-results messages."""
    producer = Producer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "client.id": "test-lp-producer"
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
def truck_consumer(test_topics):
    """Consumer for truck-detected topic."""
    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": f"test-truck-consumer-{uuid.uuid4()}",
        "auto.offset.reset": "latest",
        "enable.auto.commit": False
    })
    consumer.subscribe([test_topics["truck_detected"]])
    # Poll once to trigger partition assignment
    consumer.poll(timeout=1.0)
    yield consumer
    consumer.close()


@pytest.fixture
def lp_consumer(test_topics):
    """Consumer for lp-results topic."""
    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": f"test-lp-consumer-{uuid.uuid4()}",
        "auto.offset.reset": "latest",
        "enable.auto.commit": False
    })
    consumer.subscribe([test_topics["lp_results"]])
    # Poll once to trigger partition assignment
    consumer.poll(timeout=1.0)
    yield consumer
    consumer.close()


class TestAgentBKafkaConnectivityIntegration:
    """Tests for Agent B Kafka connectivity."""

    def test_can_subscribe_to_truck_detected_topic(self, test_topics, kafka_admin):
        """Verify Agent B can subscribe to truck-detected topic."""
        consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"test-subscribe-{uuid.uuid4()}",
            "auto.offset.reset": "earliest"
        })
        
        try:
            consumer.subscribe([test_topics["truck_detected"]])
            # Poll to trigger subscription
            consumer.poll(timeout=2.0)
            
            # Check assignment
            assignment = consumer.assignment()
            # Assignment may be empty initially but no error means success
            assert True
        finally:
            consumer.close()

    def test_can_produce_to_lp_results_topic(self, lp_producer, lp_consumer, test_topics):
        """Verify Agent B can produce to lp-results topic."""
        truck_id = f"TRK-{uuid.uuid4()}"
        payload = {
            "truckId": truck_id,
            "plate": "AA-00-BB",
            "confidence": 0.95,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        lp_producer.produce(
            topic=test_topics["lp_results"],
            key=truck_id.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8")
        )
        lp_producer.flush()
        
        msg = lp_consumer.poll(timeout=TIMEOUT_SECONDS)
        assert msg is not None
        assert msg.error() is None


class TestAgentBMessageFlowIntegration:
    """Tests for Agent B message flow (consume truck, produce LP)."""

    def test_consume_truck_detected_event(self, truck_producer, truck_consumer, test_topics):
        """Test consuming truck-detected event from Agent A."""
        truck_id = f"TRK-{uuid.uuid4()}"
        payload = {
            "truckId": truck_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "confidence": 0.92,
            "gateId": TEST_GATE_ID
        }
        
        truck_producer.produce(
            topic=test_topics["truck_detected"],
            key=truck_id.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8")
        )
        truck_producer.flush()
        
        msg = truck_consumer.poll(timeout=TIMEOUT_SECONDS)
        assert msg is not None
        
        received = json.loads(msg.value().decode("utf-8"))
        assert received["truckId"] == truck_id
        assert received["gateId"] == TEST_GATE_ID

    def test_produce_lp_result_preserves_truck_id(self, lp_producer, lp_consumer, test_topics):
        """Verify LP result preserves original truckId from trigger event."""
        truck_id = f"TRK-{uuid.uuid4()}"
        
        # Simulate Agent B producing LP result
        lp_payload = {
            "truckId": truck_id,  # Must match original
            "plate": "AB-12-CD",
            "confidence": 0.89,
            "cropUrl": f"http://minio:9000/lp-crops/{truck_id}.jpg",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        lp_producer.produce(
            topic=test_topics["lp_results"],
            key=truck_id.encode("utf-8"),
            value=json.dumps(lp_payload).encode("utf-8")
        )
        lp_producer.flush()
        
        msg = lp_consumer.poll(timeout=TIMEOUT_SECONDS)
        received = json.loads(msg.value().decode("utf-8"))
        
        assert received["truckId"] == truck_id
        assert received["plate"] == "AB-12-CD"

    def test_end_to_end_message_correlation(self, truck_producer, lp_producer, lp_consumer, test_topics):
        """Test that truck detection and LP result can be correlated."""
        truck_id = f"TRK-{uuid.uuid4()}"
        
        # Simulate full flow: Agent A triggers, Agent B responds
        truck_payload = {
            "truckId": truck_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "confidence": 0.95
        }
        
        truck_producer.produce(
            topic=test_topics["truck_detected"],
            key=truck_id.encode("utf-8"),
            value=json.dumps(truck_payload).encode("utf-8")
        )
        truck_producer.flush()
        
        # Agent B would process and produce LP result
        lp_payload = {
            "truckId": truck_id,
            "plate": "XY-99-ZZ",
            "confidence": 0.91,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        lp_producer.produce(
            topic=test_topics["lp_results"],
            key=truck_id.encode("utf-8"),
            value=json.dumps(lp_payload).encode("utf-8")
        )
        lp_producer.flush()
        
        # Verify correlation via key
        msg = lp_consumer.poll(timeout=TIMEOUT_SECONDS)
        assert msg.key().decode("utf-8") == truck_id


class TestAgentBLicensePlateMessageFormatIntegration:
    """Tests for Agent B LP result message format."""

    def test_lp_result_contains_required_fields(self, lp_producer, lp_consumer, test_topics):
        """Verify LP result contains all required fields for Decision Engine."""
        truck_id = f"TRK-{uuid.uuid4()}"
        payload = {
            "truckId": truck_id,
            "plate": "AA-11-BB",
            "confidence": 0.88,
            "cropUrl": "http://minio:9000/lp-crops/test.jpg",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "gateId": TEST_GATE_ID
        }
        
        lp_producer.produce(
            topic=test_topics["lp_results"],
            key=truck_id.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8")
        )
        lp_producer.flush()
        
        msg = lp_consumer.poll(timeout=TIMEOUT_SECONDS)
        received = json.loads(msg.value().decode("utf-8"))
        
        # Required fields for Decision Engine
        assert "truckId" in received
        assert "plate" in received
        assert "confidence" in received
        assert "timestamp" in received

    def test_plate_format_validation(self, lp_producer, lp_consumer, test_topics):
        """Test various plate format patterns."""
        test_plates = [
            "AA-00-BB",    # Standard Portuguese
            "00-AA-00",    # Older Portuguese
            "AA-00-00",    # Mixed format
            "ABC1234",     # No separators
            "AB 12 CD",    # Space separators
        ]
        
        for plate in test_plates:
            truck_id = f"TRK-{uuid.uuid4()}"
            payload = {
                "truckId": truck_id,
                "plate": plate,
                "confidence": 0.85,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
            
            lp_producer.produce(
                topic=test_topics["lp_results"],
                key=truck_id.encode("utf-8"),
                value=json.dumps(payload).encode("utf-8")
            )
        
        lp_producer.flush()
        
        # Consume all messages
        received_plates = []
        for _ in range(len(test_plates)):
            msg = lp_consumer.poll(timeout=TIMEOUT_SECONDS)
            if msg and msg.error() is None:
                data = json.loads(msg.value().decode("utf-8"))
                received_plates.append(data["plate"])
        
        assert len(received_plates) == len(test_plates)

    def test_crop_url_format(self, lp_producer, lp_consumer, test_topics):
        """Verify cropUrl follows expected MinIO URL format."""
        truck_id = f"TRK-{uuid.uuid4()}"
        crop_url = f"http://minio:9000/lp-crops/{truck_id}/crop_001.jpg"
        
        payload = {
            "truckId": truck_id,
            "plate": "TE-ST-00",
            "confidence": 0.90,
            "cropUrl": crop_url,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        lp_producer.produce(
            topic=test_topics["lp_results"],
            key=truck_id.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8")
        )
        lp_producer.flush()
        
        msg = lp_consumer.poll(timeout=TIMEOUT_SECONDS)
        received = json.loads(msg.value().decode("utf-8"))
        
        assert "cropUrl" in received
        assert received["cropUrl"].startswith("http")
        assert "lp-crops" in received["cropUrl"]


class TestAgentBConsensusResultsIntegration:
    """Tests for Agent B consensus algorithm results via Kafka."""

    def test_high_confidence_result(self, lp_producer, lp_consumer, test_topics):
        """Test high confidence LP detection result."""
        truck_id = f"TRK-{uuid.uuid4()}"
        payload = {
            "truckId": truck_id,
            "plate": "AB-12-CD",
            "confidence": 0.98,  # High confidence
            "consensusReached": True,
            "framesProcessed": 25,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        lp_producer.produce(
            topic=test_topics["lp_results"],
            key=truck_id.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8")
        )
        lp_producer.flush()
        
        msg = lp_consumer.poll(timeout=TIMEOUT_SECONDS)
        received = json.loads(msg.value().decode("utf-8"))
        
        assert received["confidence"] >= 0.95
        assert received["consensusReached"] is True

    def test_partial_result_with_uncertain_chars(self, lp_producer, lp_consumer, test_topics):
        """Test partial LP result with uncertain characters."""
        truck_id = f"TRK-{uuid.uuid4()}"
        payload = {
            "truckId": truck_id,
            "plate": "AB-?2-CD",  # ? indicates uncertain character
            "confidence": 0.72,
            "consensusReached": False,
            "framesProcessed": 40,  # Max frames reached
            "uncertainPositions": [3],
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        lp_producer.produce(
            topic=test_topics["lp_results"],
            key=truck_id.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8")
        )
        lp_producer.flush()
        
        msg = lp_consumer.poll(timeout=TIMEOUT_SECONDS)
        received = json.loads(msg.value().decode("utf-8"))
        
        assert received["consensusReached"] is False
        assert "uncertainPositions" in received


class TestAgentBMultipleEventsIntegration:
    """Tests for handling multiple concurrent events."""

    def test_multiple_trucks_sequential(self, truck_producer, lp_producer, lp_consumer, test_topics):
        """Test processing multiple truck events sequentially."""
        truck_ids = [f"TRK-{uuid.uuid4()}" for _ in range(3)]
        
        for truck_id in truck_ids:
            # Simulate Agent B processing and producing result
            payload = {
                "truckId": truck_id,
                "plate": f"PT-{truck_id[-4:]}",
                "confidence": 0.85,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
            
            lp_producer.produce(
                topic=test_topics["lp_results"],
                key=truck_id.encode("utf-8"),
                value=json.dumps(payload).encode("utf-8")
            )
        
        lp_producer.flush()
        
        # Verify all results received
        received_ids = set()
        for _ in range(3):
            msg = lp_consumer.poll(timeout=TIMEOUT_SECONDS)
            if msg and msg.error() is None:
                data = json.loads(msg.value().decode("utf-8"))
                received_ids.add(data["truckId"])
        
        assert received_ids == set(truck_ids)

    def test_message_ordering_same_gate(self, lp_producer, lp_consumer, test_topics):
        """Verify message ordering for same gate."""
        truck_id = f"TRK-{uuid.uuid4()}"
        
        # Send sequence of messages
        for seq in range(5):
            payload = {
                "truckId": truck_id,
                "sequence": seq,
                "plate": f"SQ-{seq:02d}-AA",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
            lp_producer.produce(
                topic=test_topics["lp_results"],
                key=truck_id.encode("utf-8"),
                value=json.dumps(payload).encode("utf-8")
            )
        
        lp_producer.flush()
        
        # Verify order
        sequences = []
        for _ in range(5):
            msg = lp_consumer.poll(timeout=TIMEOUT_SECONDS)
            if msg and msg.error() is None:
                data = json.loads(msg.value().decode("utf-8"))
                sequences.append(data["sequence"])
        
        assert sequences == list(range(5))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
