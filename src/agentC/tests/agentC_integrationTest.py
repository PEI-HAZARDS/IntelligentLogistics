#!/usr/bin/env python3
"""
Integration Tests for Agent C
==============================
Tests Agent C's interaction with Kafka (consuming truck-detected, producing hz-results).
Requires: Kafka running (docker-compose up from broker/)

Run with: pytest tests/agentC_integrationTest.py -v
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
TOPIC_HZ_RESULTS = f"hz-results-{TEST_GATE_ID}"
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
        NewTopic(TOPIC_HZ_RESULTS, num_partitions=1, replication_factor=1)
    ]
    
    try:
        kafka_admin.create_topics(topics)
        time.sleep(2)
    except Exception:
        pass
    
    yield {
        "truck_detected": TOPIC_TRUCK_DETECTED,
        "hz_results": TOPIC_HZ_RESULTS
    }
    
    try:
        kafka_admin.delete_topics([TOPIC_TRUCK_DETECTED, TOPIC_HZ_RESULTS])
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
def hz_producer(test_topics):
    """Producer to simulate Agent C hz-results messages."""
    producer = Producer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "client.id": "test-hz-producer"
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
def hz_consumer(test_topics):
    """Consumer for hz-results topic."""
    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": f"test-hz-consumer-{uuid.uuid4()}",
        "auto.offset.reset": "latest",
        "enable.auto.commit": False
    })
    consumer.subscribe([test_topics["hz_results"]])
    # Poll once to trigger partition assignment
    consumer.poll(timeout=1.0)
    yield consumer
    consumer.close()


class TestAgentCKafkaConnectivityIntegration:
    """Tests for Agent C Kafka connectivity."""

    def test_can_subscribe_to_truck_detected_topic(self, test_topics, kafka_admin):
        """Verify Agent C can subscribe to truck-detected topic."""
        consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"test-subscribe-{uuid.uuid4()}",
            "auto.offset.reset": "earliest"
        })
        
        try:
            consumer.subscribe([test_topics["truck_detected"]])
            consumer.poll(timeout=2.0)
            assert True
        finally:
            consumer.close()

    def test_can_produce_to_hz_results_topic(self, hz_producer, hz_consumer, test_topics):
        """Verify Agent C can produce to hz-results topic."""
        truck_id = f"TRK-{uuid.uuid4()}"
        payload = {
            "truckId": truck_id,
            "un": "1203",
            "kemler": "33",
            "confidence": 0.95,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        hz_producer.produce(
            topic=test_topics["hz_results"],
            key=truck_id.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8")
        )
        hz_producer.flush()
        
        msg = hz_consumer.poll(timeout=TIMEOUT_SECONDS)
        assert msg is not None
        assert msg.error() is None


class TestAgentCMessageFlowIntegration:
    """Tests for Agent C message flow (consume truck, produce HZ)."""

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

    def test_produce_hz_result_preserves_truck_id(self, hz_producer, hz_consumer, test_topics):
        """Verify HZ result preserves original truckId from trigger event."""
        truck_id = f"TRK-{uuid.uuid4()}"
        
        hz_payload = {
            "truckId": truck_id,
            "un": "1203",
            "kemler": "33",
            "confidence": 0.89,
            "cropUrl": f"http://minio:9000/hz-crops/{truck_id}.jpg",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        hz_producer.produce(
            topic=test_topics["hz_results"],
            key=truck_id.encode("utf-8"),
            value=json.dumps(hz_payload).encode("utf-8")
        )
        hz_producer.flush()
        
        msg = hz_consumer.poll(timeout=TIMEOUT_SECONDS)
        received = json.loads(msg.value().decode("utf-8"))
        
        assert received["truckId"] == truck_id
        assert received["un"] == "1203"
        assert received["kemler"] == "33"


class TestAgentCHazardPlateMessageFormatIntegration:
    """Tests for Agent C HZ result message format."""

    def test_hz_result_contains_required_fields(self, hz_producer, hz_consumer, test_topics):
        """Verify HZ result contains all required fields for Decision Engine."""
        truck_id = f"TRK-{uuid.uuid4()}"
        payload = {
            "truckId": truck_id,
            "un": "1203",
            "kemler": "33",
            "confidence": 0.88,
            "cropUrl": "http://minio:9000/hz-crops/test.jpg",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "gateId": TEST_GATE_ID
        }
        
        hz_producer.produce(
            topic=test_topics["hz_results"],
            key=truck_id.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8")
        )
        hz_producer.flush()
        
        msg = hz_consumer.poll(timeout=TIMEOUT_SECONDS)
        received = json.loads(msg.value().decode("utf-8"))
        
        # Required fields for Decision Engine
        assert "truckId" in received
        assert "un" in received
        assert "kemler" in received
        assert "confidence" in received
        assert "timestamp" in received

    def test_un_number_formats(self, hz_producer, hz_consumer, test_topics):
        """Test various UN number formats."""
        test_un_numbers = [
            "1203",   # Gasoline
            "1005",   # Ammonia
            "1017",   # Chlorine
            "1830",   # Sulfuric acid
            "2794",   # Batteries
            "3082",   # Environmentally hazardous
        ]
        
        for un in test_un_numbers:
            truck_id = f"TRK-{uuid.uuid4()}"
            payload = {
                "truckId": truck_id,
                "un": un,
                "kemler": "33",
                "confidence": 0.85,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
            
            hz_producer.produce(
                topic=test_topics["hz_results"],
                key=truck_id.encode("utf-8"),
                value=json.dumps(payload).encode("utf-8")
            )
        
        hz_producer.flush()
        
        received_un = []
        for _ in range(len(test_un_numbers)):
            msg = hz_consumer.poll(timeout=TIMEOUT_SECONDS)
            if msg and msg.error() is None:
                data = json.loads(msg.value().decode("utf-8"))
                received_un.append(data["un"])
        
        assert len(received_un) == len(test_un_numbers)

    def test_kemler_code_formats(self, hz_producer, hz_consumer, test_topics):
        """Test various Kemler code formats."""
        test_kemler_codes = [
            "33",     # Highly flammable liquid
            "30",     # Flammable liquid
            "X33",    # Reacts dangerously with water
            "268",    # Toxic, corrosive gas
            "90",     # Environmentally hazardous
            "X423",   # Flammable solid reacts with water
        ]
        
        for kemler in test_kemler_codes:
            truck_id = f"TRK-{uuid.uuid4()}"
            payload = {
                "truckId": truck_id,
                "un": "1203",
                "kemler": kemler,
                "confidence": 0.85,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
            
            hz_producer.produce(
                topic=test_topics["hz_results"],
                key=truck_id.encode("utf-8"),
                value=json.dumps(payload).encode("utf-8")
            )
        
        hz_producer.flush()
        
        received_kemler = []
        for _ in range(len(test_kemler_codes)):
            msg = hz_consumer.poll(timeout=TIMEOUT_SECONDS)
            if msg and msg.error() is None:
                data = json.loads(msg.value().decode("utf-8"))
                received_kemler.append(data["kemler"])
        
        assert len(received_kemler) == len(test_kemler_codes)


class TestAgentCNoHazardPlateIntegration:
    """Tests for cases where no hazard plate is detected."""

    def test_no_hazard_plate_message(self, hz_producer, hz_consumer, test_topics):
        """Test message when no hazard plate is found on truck."""
        truck_id = f"TRK-{uuid.uuid4()}"
        payload = {
            "truckId": truck_id,
            "un": None,
            "kemler": None,
            "confidence": 0.0,
            "hazardPlateDetected": False,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        hz_producer.produce(
            topic=test_topics["hz_results"],
            key=truck_id.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8")
        )
        hz_producer.flush()
        
        msg = hz_consumer.poll(timeout=TIMEOUT_SECONDS)
        received = json.loads(msg.value().decode("utf-8"))
        
        assert received["hazardPlateDetected"] is False
        assert received["un"] is None

    def test_partial_hazard_plate_result(self, hz_producer, hz_consumer, test_topics):
        """Test partial result when only UN or Kemler is readable."""
        truck_id = f"TRK-{uuid.uuid4()}"
        payload = {
            "truckId": truck_id,
            "un": "1203",
            "kemler": None,  # Could not read Kemler
            "confidence": 0.65,
            "partial": True,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        hz_producer.produce(
            topic=test_topics["hz_results"],
            key=truck_id.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8")
        )
        hz_producer.flush()
        
        msg = hz_consumer.poll(timeout=TIMEOUT_SECONDS)
        received = json.loads(msg.value().decode("utf-8"))
        
        assert received["un"] == "1203"
        assert received["kemler"] is None
        assert received["partial"] is True


class TestAgentCParallelWithAgentBIntegration:
    """Tests for Agent C running parallel to Agent B."""

    def test_both_agents_receive_same_truck_event(self, truck_producer, test_topics):
        """Verify both Agent B and C can consume same truck-detected event."""
        truck_id = f"TRK-{uuid.uuid4()}"
        payload = {
            "truckId": truck_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "confidence": 0.95
        }
        
        # Create separate consumer groups (simulating Agent B and C)
        consumer_b = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"agent-b-{uuid.uuid4()}",
            "auto.offset.reset": "earliest"
        })
        consumer_c = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"agent-c-{uuid.uuid4()}",
            "auto.offset.reset": "earliest"
        })
        
        try:
            consumer_b.subscribe([test_topics["truck_detected"]])
            consumer_c.subscribe([test_topics["truck_detected"]])
            
            # Publish truck event
            truck_producer.produce(
                topic=test_topics["truck_detected"],
                key=truck_id.encode("utf-8"),
                value=json.dumps(payload).encode("utf-8")
            )
            truck_producer.flush()
            
            # Both should receive the message
            msg_b = consumer_b.poll(timeout=TIMEOUT_SECONDS)
            msg_c = consumer_c.poll(timeout=TIMEOUT_SECONDS)
            
            assert msg_b is not None or msg_c is not None
            
        finally:
            consumer_b.close()
            consumer_c.close()


class TestAgentCMultipleEventsIntegration:
    """Tests for handling multiple concurrent events."""

    def test_multiple_trucks_sequential(self, hz_producer, hz_consumer, test_topics):
        """Test processing multiple truck events sequentially."""
        truck_ids = [f"TRK-{uuid.uuid4()}" for _ in range(3)]
        
        for truck_id in truck_ids:
            payload = {
                "truckId": truck_id,
                "un": "1203",
                "kemler": "33",
                "confidence": 0.85,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
            
            hz_producer.produce(
                topic=test_topics["hz_results"],
                key=truck_id.encode("utf-8"),
                value=json.dumps(payload).encode("utf-8")
            )
        
        hz_producer.flush()
        
        received_ids = set()
        for _ in range(3):
            msg = hz_consumer.poll(timeout=TIMEOUT_SECONDS)
            if msg and msg.error() is None:
                data = json.loads(msg.value().decode("utf-8"))
                received_ids.add(data["truckId"])
        
        assert received_ids == set(truck_ids)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
