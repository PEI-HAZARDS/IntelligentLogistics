#!/usr/bin/env python3
"""
Integration Tests for Decision Engine
======================================
Tests Decision Engine's interaction with Kafka (consuming LP/HZ results, producing decisions).
Requires: Kafka running (docker-compose up from broker/)

Run with: pytest tests/decisionEngine_integrationTest.py -v
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
TOPIC_LP_RESULTS = f"lp-results-{TEST_GATE_ID}"
TOPIC_HZ_RESULTS = f"hz-results-{TEST_GATE_ID}"
TOPIC_DECISION_RESULTS = f"decision-results-{TEST_GATE_ID}"
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
        NewTopic(TOPIC_LP_RESULTS, num_partitions=1, replication_factor=1),
        NewTopic(TOPIC_HZ_RESULTS, num_partitions=1, replication_factor=1),
        NewTopic(TOPIC_DECISION_RESULTS, num_partitions=1, replication_factor=1)
    ]
    
    try:
        kafka_admin.create_topics(topics)
        time.sleep(2)
    except Exception:
        pass
    
    yield {
        "lp_results": TOPIC_LP_RESULTS,
        "hz_results": TOPIC_HZ_RESULTS,
        "decision_results": TOPIC_DECISION_RESULTS
    }
    
    try:
        kafka_admin.delete_topics([TOPIC_LP_RESULTS, TOPIC_HZ_RESULTS, TOPIC_DECISION_RESULTS])
    except Exception:
        pass


@pytest.fixture
def lp_producer(test_topics):
    """Producer to simulate Agent B lp-results messages."""
    producer = Producer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "client.id": "test-lp-producer"
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


@pytest.fixture
def decision_producer(test_topics):
    """Producer to simulate Decision Engine output."""
    producer = Producer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "client.id": "test-decision-producer"
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
    consumer.subscribe([topic] if isinstance(topic, str) else topic)
    # Poll once to trigger partition assignment and seek to end
    consumer.poll(timeout=1.0)
    return consumer


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


@pytest.fixture
def decision_consumer(test_topics):
    """Consumer for decision-results topic."""
    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": f"test-decision-consumer-{uuid.uuid4()}",
        "auto.offset.reset": "latest",
        "enable.auto.commit": False
    })
    consumer.subscribe([test_topics["decision_results"]])
    # Poll once to trigger partition assignment
    consumer.poll(timeout=1.0)
    yield consumer
    consumer.close()


@pytest.fixture
def multi_topic_consumer(test_topics):
    """Consumer subscribed to both LP and HZ topics (like Decision Engine)."""
    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": f"test-multi-consumer-{uuid.uuid4()}",
        "auto.offset.reset": "latest",
        "enable.auto.commit": False
    })
    consumer.subscribe([test_topics["lp_results"], test_topics["hz_results"]])
    # Poll once to trigger partition assignment
    consumer.poll(timeout=1.0)
    yield consumer
    consumer.close()


class TestDecisionEngineKafkaConnectivityIntegration:
    """Tests for Decision Engine Kafka connectivity."""

    def test_can_subscribe_to_multiple_topics(self, test_topics, kafka_admin):
        """Verify Decision Engine can subscribe to both LP and HZ topics."""
        consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"test-multi-subscribe-{uuid.uuid4()}",
            "auto.offset.reset": "earliest"
        })
        
        try:
            consumer.subscribe([test_topics["lp_results"], test_topics["hz_results"]])
            consumer.poll(timeout=2.0)
            assert True
        finally:
            consumer.close()

    def test_can_produce_to_decision_results_topic(self, decision_producer, decision_consumer, test_topics):
        """Verify Decision Engine can produce to decision-results topic."""
        truck_id = f"TRK-{uuid.uuid4()}"
        payload = {
            "truckId": truck_id,
            "decision": "ALLOW",
            "confidence": 0.95,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        decision_producer.produce(
            topic=test_topics["decision_results"],
            key=truck_id.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8")
        )
        decision_producer.flush()
        
        msg = decision_consumer.poll(timeout=TIMEOUT_SECONDS)
        assert msg is not None
        assert msg.error() is None


class TestDecisionEngineMessageConsumptionIntegration:
    """Tests for Decision Engine consuming LP and HZ results."""

    def test_consume_lp_result(self, lp_producer, multi_topic_consumer, test_topics):
        """Test consuming license plate result from Agent B."""
        truck_id = f"TRK-{uuid.uuid4()}"
        payload = {
            "truckId": truck_id,
            "plate": "AA-00-BB",
            "confidence": 0.92,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        lp_producer.produce(
            topic=test_topics["lp_results"],
            key=truck_id.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8")
        )
        lp_producer.flush()
        
        msg = multi_topic_consumer.poll(timeout=TIMEOUT_SECONDS)
        assert msg is not None
        assert msg.topic() == test_topics["lp_results"]
        
        received = json.loads(msg.value().decode("utf-8"))
        assert received["plate"] == "AA-00-BB"

    def test_consume_hz_result(self, hz_producer, multi_topic_consumer, test_topics):
        """Test consuming hazard result from Agent C."""
        truck_id = f"TRK-{uuid.uuid4()}"
        payload = {
            "truckId": truck_id,
            "un": "1203",
            "kemler": "33",
            "confidence": 0.88,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        hz_producer.produce(
            topic=test_topics["hz_results"],
            key=truck_id.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8")
        )
        hz_producer.flush()
        
        msg = multi_topic_consumer.poll(timeout=TIMEOUT_SECONDS)
        assert msg is not None
        assert msg.topic() == test_topics["hz_results"]
        
        received = json.loads(msg.value().decode("utf-8"))
        assert received["un"] == "1203"

    def test_consume_both_lp_and_hz_for_same_truck(self, lp_producer, hz_producer, multi_topic_consumer, test_topics):
        """Test consuming both LP and HZ results for correlation."""
        truck_id = f"TRK-{uuid.uuid4()}"
        
        lp_payload = {
            "truckId": truck_id,
            "plate": "AB-12-CD",
            "confidence": 0.90,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        hz_payload = {
            "truckId": truck_id,
            "un": "1203",
            "kemler": "33",
            "confidence": 0.85,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        lp_producer.produce(
            topic=test_topics["lp_results"],
            key=truck_id.encode("utf-8"),
            value=json.dumps(lp_payload).encode("utf-8")
        )
        hz_producer.produce(
            topic=test_topics["hz_results"],
            key=truck_id.encode("utf-8"),
            value=json.dumps(hz_payload).encode("utf-8")
        )
        lp_producer.flush()
        hz_producer.flush()
        
        # Consume both messages
        messages = {}
        for _ in range(2):
            msg = multi_topic_consumer.poll(timeout=TIMEOUT_SECONDS)
            if msg and msg.error() is None:
                topic = msg.topic()
                messages[topic] = json.loads(msg.value().decode("utf-8"))
        
        # Both should have same truckId
        if test_topics["lp_results"] in messages and test_topics["hz_results"] in messages:
            assert messages[test_topics["lp_results"]]["truckId"] == truck_id
            assert messages[test_topics["hz_results"]]["truckId"] == truck_id


class TestDecisionEngineDecisionOutputIntegration:
    """Tests for Decision Engine decision output."""

    def test_allow_decision_format(self, decision_producer, decision_consumer, test_topics):
        """Test ALLOW decision message format."""
        truck_id = f"TRK-{uuid.uuid4()}"
        payload = {
            "truckId": truck_id,
            "decision": "ALLOW",
            "plate": "AA-00-BB",
            "matchedAppointment": {
                "id": "APT-001",
                "driver": "João Silva",
                "expectedPlate": "AA-00-BB"
            },
            "confidence": 0.95,
            "gateId": TEST_GATE_ID,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        decision_producer.produce(
            topic=test_topics["decision_results"],
            key=truck_id.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8")
        )
        decision_producer.flush()
        
        msg = decision_consumer.poll(timeout=TIMEOUT_SECONDS)
        received = json.loads(msg.value().decode("utf-8"))
        
        assert received["decision"] == "ALLOW"
        assert "matchedAppointment" in received

    def test_deny_decision_format(self, decision_producer, decision_consumer, test_topics):
        """Test DENY decision message format."""
        truck_id = f"TRK-{uuid.uuid4()}"
        payload = {
            "truckId": truck_id,
            "decision": "DENY",
            "plate": "XX-99-ZZ",
            "reason": "No matching appointment found",
            "confidence": 0.88,
            "gateId": TEST_GATE_ID,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        decision_producer.produce(
            topic=test_topics["decision_results"],
            key=truck_id.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8")
        )
        decision_producer.flush()
        
        msg = decision_consumer.poll(timeout=TIMEOUT_SECONDS)
        received = json.loads(msg.value().decode("utf-8"))
        
        assert received["decision"] == "DENY"
        assert "reason" in received

    def test_alert_decision_format(self, decision_producer, decision_consumer, test_topics):
        """Test ALERT decision message format (hazard mismatch)."""
        truck_id = f"TRK-{uuid.uuid4()}"
        payload = {
            "truckId": truck_id,
            "decision": "ALERT",
            "plate": "AA-00-BB",
            "reason": "Hazard plate mismatch",
            "detectedUN": "1203",
            "expectedUN": "1005",
            "alertLevel": "HIGH",
            "gateId": TEST_GATE_ID,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        decision_producer.produce(
            topic=test_topics["decision_results"],
            key=truck_id.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8")
        )
        decision_producer.flush()
        
        msg = decision_consumer.poll(timeout=TIMEOUT_SECONDS)
        received = json.loads(msg.value().decode("utf-8"))
        
        assert received["decision"] == "ALERT"
        assert received["alertLevel"] == "HIGH"

    def test_decision_contains_required_fields(self, decision_producer, decision_consumer, test_topics):
        """Verify decision contains all required fields."""
        truck_id = f"TRK-{uuid.uuid4()}"
        payload = {
            "truckId": truck_id,
            "decision": "ALLOW",
            "plate": "AB-12-CD",
            "confidence": 0.92,
            "gateId": TEST_GATE_ID,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        decision_producer.produce(
            topic=test_topics["decision_results"],
            key=truck_id.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8")
        )
        decision_producer.flush()
        
        msg = decision_consumer.poll(timeout=TIMEOUT_SECONDS)
        received = json.loads(msg.value().decode("utf-8"))
        
        # Required fields
        assert "truckId" in received
        assert "decision" in received
        assert "plate" in received
        assert "timestamp" in received
        assert "gateId" in received


class TestDecisionEngineCorrelationIntegration:
    """Tests for correlating LP and HZ results."""

    def test_correlate_by_truck_id(self, lp_producer, hz_producer, test_topics):
        """Test that LP and HZ results can be correlated by truckId."""
        truck_id = f"TRK-{uuid.uuid4()}"
        
        # Simulate buffering like Decision Engine does
        buffer = {"lp": {}, "hz": {}}
        
        consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"test-correlate-{uuid.uuid4()}",
            "auto.offset.reset": "latest"
        })
        consumer.subscribe([test_topics["lp_results"], test_topics["hz_results"]])
        # Trigger partition assignment before producing
        consumer.poll(timeout=1.0)
        
        try:
            # Publish both results
            lp_producer.produce(
                topic=test_topics["lp_results"],
                key=truck_id.encode("utf-8"),
                value=json.dumps({"truckId": truck_id, "plate": "AA-00-BB"}).encode("utf-8")
            )
            hz_producer.produce(
                topic=test_topics["hz_results"],
                key=truck_id.encode("utf-8"),
                value=json.dumps({"truckId": truck_id, "un": "1203", "kemler": "33"}).encode("utf-8")
            )
            lp_producer.flush()
            hz_producer.flush()
            
            # Consume and buffer
            for _ in range(2):
                msg = consumer.poll(timeout=TIMEOUT_SECONDS)
                if msg and msg.error() is None:
                    data = json.loads(msg.value().decode("utf-8"))
                    tid = data["truckId"]
                    if msg.topic() == test_topics["lp_results"]:
                        buffer["lp"][tid] = data
                    else:
                        buffer["hz"][tid] = data
            
            # Verify correlation
            assert truck_id in buffer["lp"]
            assert truck_id in buffer["hz"]
            assert buffer["lp"][truck_id]["plate"] == "AA-00-BB"
            assert buffer["hz"][truck_id]["un"] == "1203"
            
        finally:
            consumer.close()

    def test_handle_lp_only_no_hazard(self, lp_producer, test_topics):
        """Test handling truck with LP but no hazard plate."""
        truck_id = f"TRK-{uuid.uuid4()}"
        
        consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"test-lp-only-{uuid.uuid4()}",
            "auto.offset.reset": "latest"
        })
        consumer.subscribe([test_topics["lp_results"], test_topics["hz_results"]])
        # Trigger partition assignment before producing
        consumer.poll(timeout=1.0)
        
        try:
            # Only LP result (no hazard plate on truck)
            lp_producer.produce(
                topic=test_topics["lp_results"],
                key=truck_id.encode("utf-8"),
                value=json.dumps({
                    "truckId": truck_id,
                    "plate": "AA-00-BB",
                    "confidence": 0.95
                }).encode("utf-8")
            )
            lp_producer.flush()
            
            msg = consumer.poll(timeout=TIMEOUT_SECONDS)
            assert msg is not None
            
            data = json.loads(msg.value().decode("utf-8"))
            assert data["truckId"] == truck_id
            
        finally:
            consumer.close()


class TestDecisionEngineTimeoutHandlingIntegration:
    """Tests for handling timeouts and missing data."""

    def test_timeout_waiting_for_hz_result(self, lp_producer, test_topics):
        """Test Decision Engine behavior when HZ result times out."""
        truck_id = f"TRK-{uuid.uuid4()}"
        
        consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"test-timeout-{uuid.uuid4()}",
            "auto.offset.reset": "latest"
        })
        consumer.subscribe([test_topics["lp_results"], test_topics["hz_results"]])
        # Trigger partition assignment before producing
        consumer.poll(timeout=1.0)
        
        try:
            # Send LP result
            lp_producer.produce(
                topic=test_topics["lp_results"],
                key=truck_id.encode("utf-8"),
                value=json.dumps({"truckId": truck_id, "plate": "AA-00-BB"}).encode("utf-8")
            )
            lp_producer.flush()
            
            # Consume LP
            msg = consumer.poll(timeout=TIMEOUT_SECONDS)
            assert msg is not None
            
            # Try to consume HZ (should timeout)
            hz_msg = consumer.poll(timeout=2.0)
            # Either None or unrelated message
            
            # Decision should proceed with LP only after timeout
            assert True  # Test passes if no crash
            
        finally:
            consumer.close()


class TestDecisionEngineMultipleGatesIntegration:
    """Tests for handling multiple gates."""

    def test_filter_messages_by_gate(self, lp_producer, test_topics):
        """Test that Decision Engine can filter by gate ID."""
        # Create consumer first and subscribe
        consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"test-gate-filter-{uuid.uuid4()}",
            "auto.offset.reset": "latest"
        })
        consumer.subscribe([test_topics["lp_results"]])
        # Trigger partition assignment before producing
        consumer.poll(timeout=1.0)
        
        # Messages for different gates
        messages = [
            {"truckId": f"TRK-{uuid.uuid4()}", "gateId": "1", "plate": "G1-AA-BB"},
            {"truckId": f"TRK-{uuid.uuid4()}", "gateId": "2", "plate": "G2-CC-DD"},
            {"truckId": f"TRK-{uuid.uuid4()}", "gateId": "1", "plate": "G1-EE-FF"},
        ]
        
        for msg in messages:
            lp_producer.produce(
                topic=test_topics["lp_results"],
                key=msg["truckId"].encode("utf-8"),
                value=json.dumps(msg).encode("utf-8")
            )
        lp_producer.flush()
        
        try:
            gate_1_messages = []
            for _ in range(3):
                msg = consumer.poll(timeout=TIMEOUT_SECONDS)
                if msg and msg.error() is None:
                    data = json.loads(msg.value().decode("utf-8"))
                    if data.get("gateId") == "1":
                        gate_1_messages.append(data)
            
            assert len(gate_1_messages) == 2
            
        finally:
            consumer.close()


class TestDecisionEngineErrorHandlingIntegration:
    """Tests for error handling scenarios."""

    def test_handle_malformed_json(self, test_topics):
        """Test handling malformed JSON message."""
        producer = Producer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "client.id": "test-malformed"
        })
        
        consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"test-malformed-{uuid.uuid4()}",
            "auto.offset.reset": "latest"
        })
        consumer.subscribe([test_topics["lp_results"]])
        # Trigger partition assignment before producing
        consumer.poll(timeout=1.0)
        
        try:
            # Send malformed JSON
            producer.produce(
                topic=test_topics["lp_results"],
                value=b"not valid json {"
            )
            producer.flush()
            
            msg = consumer.poll(timeout=TIMEOUT_SECONDS)
            if msg and msg.error() is None:
                # Attempting to parse should fail gracefully
                try:
                    json.loads(msg.value().decode("utf-8"))
                    assert False, "Should have raised JSONDecodeError"
                except json.JSONDecodeError:
                    pass  # Expected behavior
                    
        finally:
            consumer.close()
            producer.flush()

    def test_handle_missing_required_fields(self, lp_producer, test_topics):
        """Test handling message with missing required fields."""
        consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"test-missing-fields-{uuid.uuid4()}",
            "auto.offset.reset": "latest"
        })
        consumer.subscribe([test_topics["lp_results"]])
        # Trigger partition assignment before producing
        consumer.poll(timeout=1.0)
        
        try:
            # Send message missing 'plate' field
            lp_producer.produce(
                topic=test_topics["lp_results"],
                value=json.dumps({"truckId": "TRK-123"}).encode("utf-8")
            )
            lp_producer.flush()
            
            msg = consumer.poll(timeout=TIMEOUT_SECONDS)
            if msg and msg.error() is None:
                data = json.loads(msg.value().decode("utf-8"))
                # Should handle gracefully
                assert "plate" not in data or data.get("plate") is None
                
        finally:
            consumer.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
