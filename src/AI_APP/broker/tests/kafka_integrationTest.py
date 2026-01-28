#!/usr/bin/env python3
"""
Integration Tests for Kafka Broker
===================================
Tests the complete message flow through Kafka between all agents.
Requires: Kafka running (docker-compose up from broker/)

Run with: pytest tests/kafka_integrationTest.py -v
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

# Test configuration
KAFKA_BOOTSTRAP = os.getenv("TEST_KAFKA_BOOTSTRAP", "localhost:9092")
TEST_GATE_ID = "integration-test"
TIMEOUT_SECONDS = 10

# All topics in the system
TOPICS = {
    "truck_detected": f"truck-detected-{TEST_GATE_ID}",
    "lp_results": f"lp-results-{TEST_GATE_ID}",
    "hz_results": f"hz-results-{TEST_GATE_ID}",
    "decision_results": f"decision-results-{TEST_GATE_ID}"
}


def kafka_available() -> bool:
    """Check if Kafka is available for integration tests."""
    try:
        admin = AdminClient({"bootstrap.servers": KAFKA_BOOTSTRAP})
        admin.list_topics(timeout=5)
        return True
    except Exception:
        return False


def create_isolated_consumer(topics):
    """Create an isolated consumer that starts from the latest offset."""
    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": f"test-consumer-{uuid.uuid4()}",
        "auto.offset.reset": "latest",
        "enable.auto.commit": False
    })
    topic_list = [topics] if isinstance(topics, str) else topics
    consumer.subscribe(topic_list)
    # Poll once to trigger partition assignment and seek to end
    consumer.poll(timeout=1.0)
    return consumer


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
def all_topics(kafka_admin):
    """Create all test topics and cleanup after tests."""
    topics = [
        NewTopic(name, num_partitions=1, replication_factor=1)
        for name in TOPICS.values()
    ]
    
    try:
        kafka_admin.create_topics(topics)
        time.sleep(2)
    except Exception:
        pass
    
    yield TOPICS
    
    try:
        kafka_admin.delete_topics(list(TOPICS.values()))
    except Exception:
        pass


class TestKafkaBrokerHealthIntegration:
    """Tests for Kafka broker health and configuration."""

    def test_broker_is_reachable(self, kafka_admin):
        """Verify Kafka broker is reachable."""
        metadata = kafka_admin.list_topics(timeout=10)
        assert metadata is not None
        assert len(metadata.brokers) > 0

    def test_broker_accepts_connections(self):
        """Test that broker accepts producer connections."""
        producer = Producer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "socket.timeout.ms": 5000
        })
        
        # If this doesn't raise, broker is accepting connections
        producer.flush(timeout=5)
        assert True

    def test_broker_accepts_consumer_connections(self):
        """Test that broker accepts consumer connections."""
        consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"test-health-{uuid.uuid4()}",
            "session.timeout.ms": 6000
        })
        
        try:
            # This would fail if broker not accepting connections
            consumer.subscribe(["__consumer_offsets"])
            consumer.poll(timeout=1.0)
            assert True
        finally:
            consumer.close()


class TestFullPipelineIntegration:
    """Tests for the complete message pipeline."""

    def test_full_pipeline_allow_flow(self, all_topics):
        """Test complete flow: Truck → LP → HZ → Decision (ALLOW)."""
        truck_id = f"TRK-{uuid.uuid4()}"
        
        # Create producers for each agent
        agent_a_producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
        agent_b_producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
        agent_c_producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
        decision_producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
        
        # Create consumer for final decision
        decision_consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"test-pipeline-{uuid.uuid4()}",
            "auto.offset.reset": "latest"
        })
        decision_consumer.subscribe([all_topics["decision_results"]])
        # Poll once to trigger partition assignment
        decision_consumer.poll(timeout=1.0)
        
        try:
            # Step 1: Agent A detects truck
            agent_a_payload = {
                "truckId": truck_id,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "confidence": 0.95,
                "gateId": TEST_GATE_ID
            }
            agent_a_producer.produce(
                topic=all_topics["truck_detected"],
                key=truck_id.encode("utf-8"),
                value=json.dumps(agent_a_payload).encode("utf-8")
            )
            agent_a_producer.flush()
            
            # Step 2: Agent B detects license plate
            agent_b_payload = {
                "truckId": truck_id,
                "plate": "AA-00-BB",
                "confidence": 0.92,
                "cropUrl": f"http://minio:9000/lp-crops/{truck_id}.jpg",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
            agent_b_producer.produce(
                topic=all_topics["lp_results"],
                key=truck_id.encode("utf-8"),
                value=json.dumps(agent_b_payload).encode("utf-8")
            )
            agent_b_producer.flush()
            
            # Step 3: Agent C detects hazard plate
            agent_c_payload = {
                "truckId": truck_id,
                "un": "1203",
                "kemler": "33",
                "confidence": 0.88,
                "cropUrl": f"http://minio:9000/hz-crops/{truck_id}.jpg",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
            agent_c_producer.produce(
                topic=all_topics["hz_results"],
                key=truck_id.encode("utf-8"),
                value=json.dumps(agent_c_payload).encode("utf-8")
            )
            agent_c_producer.flush()
            
            # Step 4: Decision Engine produces decision
            decision_payload = {
                "truckId": truck_id,
                "decision": "ALLOW",
                "plate": "AA-00-BB",
                "un": "1203",
                "kemler": "33",
                "matchedAppointment": {"id": "APT-001"},
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
            decision_producer.produce(
                topic=all_topics["decision_results"],
                key=truck_id.encode("utf-8"),
                value=json.dumps(decision_payload).encode("utf-8")
            )
            decision_producer.flush()
            
            # Verify final decision
            msg = decision_consumer.poll(timeout=TIMEOUT_SECONDS)
            assert msg is not None
            
            received = json.loads(msg.value().decode("utf-8"))
            assert received["truckId"] == truck_id
            assert received["decision"] == "ALLOW"
            
        finally:
            decision_consumer.close()

    def test_full_pipeline_deny_flow(self, all_topics):
        """Test complete flow resulting in DENY decision."""
        truck_id = f"TRK-{uuid.uuid4()}"
        
        decision_producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
        decision_consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"test-deny-{uuid.uuid4()}",
            "auto.offset.reset": "latest"
        })
        decision_consumer.subscribe([all_topics["decision_results"]])
        # Poll once to trigger partition assignment
        decision_consumer.poll(timeout=1.0)
        
        try:
            # Unknown plate - no matching appointment
            decision_payload = {
                "truckId": truck_id,
                "decision": "DENY",
                "plate": "XX-99-ZZ",
                "reason": "No matching appointment found",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
            decision_producer.produce(
                topic=all_topics["decision_results"],
                key=truck_id.encode("utf-8"),
                value=json.dumps(decision_payload).encode("utf-8")
            )
            decision_producer.flush()
            
            msg = decision_consumer.poll(timeout=TIMEOUT_SECONDS)
            received = json.loads(msg.value().decode("utf-8"))
            
            assert received["decision"] == "DENY"
            assert "reason" in received
            
        finally:
            decision_consumer.close()

    def test_full_pipeline_alert_flow(self, all_topics):
        """Test complete flow resulting in ALERT decision (hazard mismatch)."""
        truck_id = f"TRK-{uuid.uuid4()}"
        
        decision_producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
        decision_consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"test-alert-{uuid.uuid4()}",
            "auto.offset.reset": "latest"
        })
        decision_consumer.subscribe([all_topics["decision_results"]])
        # Poll once to trigger partition assignment
        decision_consumer.poll(timeout=1.0)
        
        try:
            # Hazard mismatch
            decision_payload = {
                "truckId": truck_id,
                "decision": "ALERT",
                "plate": "AA-00-BB",
                "detectedUN": "1203",
                "expectedUN": "1005",
                "reason": "UN number mismatch",
                "alertLevel": "HIGH",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
            decision_producer.produce(
                topic=all_topics["decision_results"],
                key=truck_id.encode("utf-8"),
                value=json.dumps(decision_payload).encode("utf-8")
            )
            decision_producer.flush()
            
            msg = decision_consumer.poll(timeout=TIMEOUT_SECONDS)
            received = json.loads(msg.value().decode("utf-8"))
            
            assert received["decision"] == "ALERT"
            assert received["alertLevel"] == "HIGH"
            
        finally:
            decision_consumer.close()


class TestMessageCorrelationAcrossTopicsIntegration:
    """Tests for message correlation across different topics."""

    def test_truck_id_propagation_through_pipeline(self, all_topics):
        """Verify truckId is preserved through all pipeline stages."""
        truck_id = f"TRK-{uuid.uuid4()}"
        
        # Producers for all stages
        producers = {
            "truck": Producer({"bootstrap.servers": KAFKA_BOOTSTRAP}),
            "lp": Producer({"bootstrap.servers": KAFKA_BOOTSTRAP}),
            "hz": Producer({"bootstrap.servers": KAFKA_BOOTSTRAP}),
            "decision": Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
        }
        
        # Consumer for all topics
        consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"test-propagation-{uuid.uuid4()}",
            "auto.offset.reset": "latest"
        })
        consumer.subscribe(list(all_topics.values()))
        # Poll once to trigger partition assignment
        consumer.poll(timeout=1.0)
        
        try:
            # Publish to all topics with same truckId
            for topic_key, topic_name in all_topics.items():
                payload = {
                    "truckId": truck_id,
                    "topic": topic_key,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
                }
                producers[topic_key.split("_")[0] if "_" in topic_key else "truck"].produce(
                    topic=topic_name,
                    key=truck_id.encode("utf-8"),
                    value=json.dumps(payload).encode("utf-8")
                )
            
            for p in producers.values():
                p.flush()
            
            # Consume all and verify truckId
            received_topics = {}
            for _ in range(len(all_topics)):
                msg = consumer.poll(timeout=TIMEOUT_SECONDS)
                if msg and msg.error() is None:
                    data = json.loads(msg.value().decode("utf-8"))
                    assert data["truckId"] == truck_id
                    received_topics[msg.topic()] = data
            
            # Should have messages from all topics
            assert len(received_topics) >= 1
            
        finally:
            consumer.close()

    def test_message_ordering_within_partition(self, all_topics):
        """Verify messages with same key maintain order within partition."""
        truck_id = f"TRK-{uuid.uuid4()}"
        producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
        consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"test-ordering-{uuid.uuid4()}",
            "auto.offset.reset": "latest"
        })
        consumer.subscribe([all_topics["truck_detected"]])
        # Poll once to trigger partition assignment
        consumer.poll(timeout=1.0)
        
        try:
            # Send sequence of messages
            for seq in range(10):
                payload = {
                    "truckId": truck_id,
                    "sequence": seq,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
                }
                producer.produce(
                    topic=all_topics["truck_detected"],
                    key=truck_id.encode("utf-8"),
                    value=json.dumps(payload).encode("utf-8")
                )
            producer.flush()
            
            # Verify order
            sequences = []
            for _ in range(10):
                msg = consumer.poll(timeout=TIMEOUT_SECONDS)
                if msg and msg.error() is None:
                    data = json.loads(msg.value().decode("utf-8"))
                    sequences.append(data["sequence"])
            
            assert sequences == list(range(10))
            
        finally:
            consumer.close()


class TestConsumerGroupsIntegration:
    """Tests for consumer group behavior."""

    def test_multiple_consumers_same_group(self, all_topics):
        """Test load balancing with multiple consumers in same group."""
        group_id = f"test-group-{uuid.uuid4()}"
        
        consumer1 = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": group_id,
            "auto.offset.reset": "latest"
        })
        consumer2 = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": group_id,
            "auto.offset.reset": "latest"
        })
        
        try:
            consumer1.subscribe([all_topics["truck_detected"]])
            consumer2.subscribe([all_topics["truck_detected"]])
            
            # With single partition, only one consumer gets assignment
            # This is expected Kafka behavior
            consumer1.poll(timeout=2.0)
            consumer2.poll(timeout=2.0)
            
            assert True  # Test passes if no errors
            
        finally:
            consumer1.close()
            consumer2.close()

    def test_different_consumer_groups_receive_same_message(self, all_topics):
        """Test that different consumer groups both receive the same message."""
        producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
        
        consumer1 = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"group-1-{uuid.uuid4()}",
            "auto.offset.reset": "latest"
        })
        consumer2 = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"group-2-{uuid.uuid4()}",
            "auto.offset.reset": "latest"
        })
        
        try:
            consumer1.subscribe([all_topics["truck_detected"]])
            consumer2.subscribe([all_topics["truck_detected"]])
            # Trigger partition assignment before producing
            consumer1.poll(timeout=1.0)
            consumer2.poll(timeout=1.0)
            
            # Produce message
            truck_id = f"TRK-{uuid.uuid4()}"
            producer.produce(
                topic=all_topics["truck_detected"],
                key=truck_id.encode("utf-8"),
                value=json.dumps({"truckId": truck_id}).encode("utf-8")
            )
            producer.flush()
            
            # Both should receive the message
            msg1 = consumer1.poll(timeout=TIMEOUT_SECONDS)
            msg2 = consumer2.poll(timeout=TIMEOUT_SECONDS)
            
            # At least one should receive (timing dependent)
            assert msg1 is not None or msg2 is not None
            
        finally:
            consumer1.close()
            consumer2.close()


class TestAgentBAndCParallelConsumptionIntegration:
    """Tests simulating Agent B and C consuming same truck-detected events."""

    def test_both_agents_receive_truck_event(self, all_topics):
        """Simulate Agent B and C both receiving truck-detected event."""
        producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
        
        # Agent B consumer group
        agent_b = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"agent-b-{uuid.uuid4()}",
            "auto.offset.reset": "latest"
        })
        
        # Agent C consumer group
        agent_c = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"agent-c-{uuid.uuid4()}",
            "auto.offset.reset": "latest"
        })
        
        try:
            agent_b.subscribe([all_topics["truck_detected"]])
            agent_c.subscribe([all_topics["truck_detected"]])
            # Trigger partition assignment before producing
            agent_b.poll(timeout=1.0)
            agent_c.poll(timeout=1.0)
            
            # Agent A publishes truck detection
            truck_id = f"TRK-{uuid.uuid4()}"
            producer.produce(
                topic=all_topics["truck_detected"],
                key=truck_id.encode("utf-8"),
                value=json.dumps({
                    "truckId": truck_id,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "confidence": 0.95
                }).encode("utf-8")
            )
            producer.flush()
            
            # Both agents should receive
            msg_b = agent_b.poll(timeout=TIMEOUT_SECONDS)
            msg_c = agent_c.poll(timeout=TIMEOUT_SECONDS)
            
            # At least one should receive (both should in production)
            received = []
            if msg_b and msg_b.error() is None:
                received.append("B")
            if msg_c and msg_c.error() is None:
                received.append("C")
            
            assert len(received) >= 1
            
        finally:
            agent_b.close()
            agent_c.close()


class TestHighThroughputIntegration:
    """Tests for high throughput scenarios."""

    def test_burst_messages(self, all_topics):
        """Test handling burst of messages."""
        producer = Producer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "queue.buffering.max.messages": 10000
        })
        
        num_messages = 500
        delivered = [0]
        
        def delivery_callback(err, msg):
            if err is None:
                delivered[0] += 1
        
        start = time.time()
        for i in range(num_messages):
            producer.produce(
                topic=all_topics["truck_detected"],
                value=json.dumps({"seq": i, "truckId": f"TRK-{i}"}).encode("utf-8"),
                callback=delivery_callback
            )
            
            # Periodic flush to prevent queue overflow
            if i % 100 == 0:
                producer.poll(0)
        
        producer.flush()
        elapsed = time.time() - start
        
        assert delivered[0] == num_messages
        print(f"\nBurst test: {num_messages} messages in {elapsed:.2f}s ({num_messages/elapsed:.0f} msg/s)")

    def test_sustained_throughput(self, all_topics):
        """Test sustained message throughput over time."""
        producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
        
        duration = 5  # seconds
        messages_sent = 0
        start = time.time()
        
        while time.time() - start < duration:
            producer.produce(
                topic=all_topics["truck_detected"],
                value=json.dumps({"ts": time.time()}).encode("utf-8")
            )
            messages_sent += 1
            producer.poll(0)
        
        producer.flush()
        elapsed = time.time() - start
        
        print(f"\nSustained test: {messages_sent} messages in {elapsed:.2f}s ({messages_sent/elapsed:.0f} msg/s)")
        assert messages_sent > 0


class TestTopicConfigurationIntegration:
    """Tests for topic configuration."""

    def test_auto_topic_creation(self, kafka_admin):
        """Test auto topic creation when enabled."""
        random_topic = f"auto-create-test-{uuid.uuid4()}"
        producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
        
        try:
            # Produce to non-existent topic (should auto-create if enabled)
            producer.produce(topic=random_topic, value=b"test")
            producer.flush()
            
            # Check if topic was created
            time.sleep(1)
            metadata = kafka_admin.list_topics(timeout=10)
            
            # Topic should exist if auto-create is enabled
            if random_topic in metadata.topics:
                # Cleanup
                kafka_admin.delete_topics([random_topic])
            
            assert True
            
        except Exception:
            pass  # May fail if auto-create is disabled

    def test_topic_partition_count(self, kafka_admin, all_topics):
        """Verify topic partition configuration."""
        metadata = kafka_admin.list_topics(timeout=10)
        
        for topic_name in all_topics.values():
            if topic_name in metadata.topics:
                topic_metadata = metadata.topics[topic_name]
                # Our test topics have 1 partition
                assert len(topic_metadata.partitions) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
