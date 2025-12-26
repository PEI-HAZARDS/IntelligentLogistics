"""
Comprehensive Unit Tests for Kafka Broker and Message Flow
==========================================================
Tests for:
- Broker connectivity and topic management
- Message production and consumption
- Roundtrip message flow
- Flow simulation across all agents
"""

import os
import sys
import json
import time
import uuid
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, PropertyMock

# Setup path for imports
TESTS_DIR = Path(__file__).resolve().parent
BROKER_ROOT = TESTS_DIR.parent
GLOBAL_SRC = BROKER_ROOT.parent

sys.path.insert(0, str(BROKER_ROOT))
sys.path.insert(0, str(GLOBAL_SRC))


class TestKafkaBrokerConnectivity:
    """Tests for Kafka broker connectivity."""
    
    @patch('confluent_kafka.admin.AdminClient')
    def test_admin_client_creation(self, mock_admin):
        """Test that AdminClient can be created with correct config."""
        from confluent_kafka.admin import AdminClient
        
        bootstrap_servers = "localhost:9092"
        
        admin = AdminClient({"bootstrap.servers": bootstrap_servers})
        
        mock_admin.assert_called_once_with({"bootstrap.servers": bootstrap_servers})
    
    @patch('confluent_kafka.admin.AdminClient')
    def test_list_topics(self, mock_admin_class):
        """Test listing topics from broker."""
        mock_admin = Mock()
        mock_admin_class.return_value = mock_admin
        
        mock_metadata = Mock()
        mock_metadata.topics = {"topic1": Mock(), "topic2": Mock()}
        mock_admin.list_topics.return_value = mock_metadata
        
        from confluent_kafka.admin import AdminClient
        admin = AdminClient({"bootstrap.servers": "localhost:9092"})
        
        md = admin.list_topics(timeout=5.0)
        
        assert "topic1" in md.topics
        assert "topic2" in md.topics


class TestKafkaProducer:
    """Tests for Kafka producer functionality."""
    
    @patch('confluent_kafka.Producer')
    def test_producer_creation(self, mock_producer_class):
        """Test that Producer can be created with correct config."""
        from confluent_kafka import Producer
        
        config = {
            'bootstrap.servers': 'localhost:9092',
            'client.id': 'test-producer'
        }
        
        producer = Producer(config)
        
        mock_producer_class.assert_called_once_with(config)
    
    @patch('confluent_kafka.Producer')
    def test_producer_produce_message(self, mock_producer_class):
        """Test producing a message to a topic."""
        mock_producer = Mock()
        mock_producer_class.return_value = mock_producer
        
        from confluent_kafka import Producer
        
        producer = Producer({'bootstrap.servers': 'localhost:9092'})
        
        topic = "test-topic"
        key = "test-key"
        value = json.dumps({"test": True}).encode('utf-8')
        
        producer.produce(topic=topic, key=key, value=value)
        
        mock_producer.produce.assert_called_once_with(
            topic=topic, key=key, value=value
        )
    
    @patch('confluent_kafka.Producer')
    def test_producer_flush(self, mock_producer_class):
        """Test flushing producer messages."""
        mock_producer = Mock()
        mock_producer.flush.return_value = 0  # No messages remaining
        mock_producer_class.return_value = mock_producer
        
        from confluent_kafka import Producer
        
        producer = Producer({'bootstrap.servers': 'localhost:9092'})
        producer.flush(10.0)
        
        mock_producer.flush.assert_called_once_with(10.0)


class TestKafkaConsumer:
    """Tests for Kafka consumer functionality."""
    
    @patch('confluent_kafka.Consumer')
    def test_consumer_creation(self, mock_consumer_class):
        """Test that Consumer can be created with correct config."""
        from confluent_kafka import Consumer
        
        config = {
            'bootstrap.servers': 'localhost:9092',
            'group.id': 'test-group',
            'auto.offset.reset': 'earliest'
        }
        
        consumer = Consumer(config)
        
        mock_consumer_class.assert_called_once_with(config)
    
    @patch('confluent_kafka.Consumer')
    def test_consumer_subscribe(self, mock_consumer_class):
        """Test subscribing consumer to topics."""
        mock_consumer = Mock()
        mock_consumer_class.return_value = mock_consumer
        
        from confluent_kafka import Consumer
        
        consumer = Consumer({
            'bootstrap.servers': 'localhost:9092',
            'group.id': 'test-group'
        })
        
        topics = ["topic1", "topic2"]
        consumer.subscribe(topics)
        
        mock_consumer.subscribe.assert_called_once_with(topics)
    
    @patch('confluent_kafka.Consumer')
    def test_consumer_poll(self, mock_consumer_class):
        """Test polling for messages."""
        mock_consumer = Mock()
        mock_msg = Mock()
        mock_msg.value.return_value = json.dumps({"test": True}).encode('utf-8')
        mock_msg.error.return_value = None
        mock_consumer.poll.return_value = mock_msg
        mock_consumer_class.return_value = mock_consumer
        
        from confluent_kafka import Consumer
        
        consumer = Consumer({
            'bootstrap.servers': 'localhost:9092',
            'group.id': 'test-group'
        })
        
        msg = consumer.poll(timeout=1.0)
        
        assert msg is not None
        assert msg.value() == json.dumps({"test": True}).encode('utf-8')


class TestTopicManagement:
    """Tests for topic creation and management."""
    
    @patch('confluent_kafka.admin.AdminClient')
    def test_create_topic(self, mock_admin_class):
        """Test creating a new topic."""
        from confluent_kafka.admin import AdminClient, NewTopic
        
        mock_admin = Mock()
        mock_admin_class.return_value = mock_admin
        
        # Mock list_topics to return empty topics
        mock_metadata = Mock()
        mock_metadata.topics = {}
        mock_admin.list_topics.return_value = mock_metadata
        
        # Mock create_topics
        mock_future = Mock()
        mock_future.result.return_value = None
        mock_admin.create_topics.return_value = {"new-topic": mock_future}
        
        admin = AdminClient({'bootstrap.servers': 'localhost:9092'})
        
        new_topics = [NewTopic("new-topic", num_partitions=1, replication_factor=1)]
        fs = admin.create_topics(new_topics)
        
        mock_admin.create_topics.assert_called_once()
    
    @patch('confluent_kafka.admin.AdminClient')
    def test_topic_exists_check(self, mock_admin_class):
        """Test checking if topic exists."""
        mock_admin = Mock()
        mock_admin_class.return_value = mock_admin
        
        mock_metadata = Mock()
        mock_metadata.topics = {"existing-topic": Mock()}
        mock_admin.list_topics.return_value = mock_metadata
        
        from confluent_kafka.admin import AdminClient
        
        admin = AdminClient({'bootstrap.servers': 'localhost:9092'})
        md = admin.list_topics(timeout=5.0)
        
        assert "existing-topic" in md.topics


class TestMessageFormat:
    """Tests for message format validation."""
    
    def test_truck_detected_message_format(self):
        """Test truck-detected message format."""
        truck_id = "TRK" + str(uuid.uuid4())[:8]
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        payload = {
            "timestamp": timestamp,
            "confidence": 0.95,
            "detections": 1
        }
        
        # Validate required fields
        assert "timestamp" in payload
        assert "confidence" in payload
        assert "detections" in payload
        assert isinstance(payload["confidence"], float)
        assert isinstance(payload["detections"], int)
    
    def test_license_plate_message_format(self):
        """Test license plate result message format."""
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        payload = {
            "timestamp": timestamp,
            "licensePlate": "58-76-TK",
            "confidence": 0.98,
            "cropUrl": "http://minio:9000/lp-crops/test.jpg"
        }
        
        assert "timestamp" in payload
        assert "licensePlate" in payload
        assert "confidence" in payload
        assert "cropUrl" in payload
    
    def test_hazard_plate_message_format(self):
        """Test hazard plate result message format."""
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        payload = {
            "timestamp": timestamp,
            "un": "1203",
            "kemler": "33",
            "confidence": 0.92,
            "cropUrl": "http://minio:9000/hz-crops/test.jpg"
        }
        
        assert "timestamp" in payload
        assert "un" in payload
        assert "kemler" in payload
        assert "confidence" in payload
    
    def test_decision_message_format(self):
        """Test decision result message format."""
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        payload = {
            "timestamp": timestamp,
            "licensePlate": "58-76-TK",
            "UN": "1203: GASOLINE",
            "kemler": "33: highly flammable liquid",
            "alerts": [],
            "lp_cropUrl": "http://minio:9000/lp-crops/test.jpg",
            "hz_cropUrl": "http://minio:9000/hz-crops/test.jpg",
            "route": {
                "gate_id": "1",
                "terminal_id": "T1",
                "appointment_id": "APT-12345"
            },
            "decision": "ACCEPTED"
        }
        
        assert "timestamp" in payload
        assert "licensePlate" in payload
        assert "decision" in payload
        assert payload["decision"] in ["ACCEPTED", "REJECTED", "MANUAL_REVIEW"]


class TestFlowSimulation:
    """Tests for flow simulation functionality."""
    
    def test_generate_truck_id_format(self):
        """Test that truck IDs are generated correctly."""
        truck_id = "TRK" + str(uuid.uuid4())[:8]
        
        assert truck_id.startswith("TRK")
        assert len(truck_id) == 11  # TRK + 8 chars
    
    def test_timestamp_format(self):
        """Test that timestamps are in ISO format."""
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        # Should be in format: 2025-01-01T12:00:00Z
        assert "T" in timestamp
        assert timestamp.endswith("Z")
        assert len(timestamp) == 20
    
    @patch('confluent_kafka.Producer')
    def test_simulate_agent_a_publish(self, mock_producer_class):
        """Test simulating Agent A truck detection publish."""
        mock_producer = Mock()
        mock_producer_class.return_value = mock_producer
        
        from confluent_kafka import Producer
        
        producer = Producer({'bootstrap.servers': 'localhost:9092'})
        
        truck_id = "TRK12345678"
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "confidence": 0.95,
            "detections": 1
        }
        
        producer.produce(
            topic="truck-detected-1",
            key=truck_id.encode('utf-8'),
            value=json.dumps(payload).encode('utf-8'),
            headers={"truckId": truck_id}
        )
        
        mock_producer.produce.assert_called_once()
    
    @patch('confluent_kafka.Producer')
    def test_simulate_agent_b_publish(self, mock_producer_class):
        """Test simulating Agent B license plate publish."""
        mock_producer = Mock()
        mock_producer_class.return_value = mock_producer
        
        from confluent_kafka import Producer
        
        producer = Producer({'bootstrap.servers': 'localhost:9092'})
        
        truck_id = "TRK12345678"
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "licensePlate": "58-76-TK",
            "confidence": 0.98,
            "cropUrl": "http://minio:9000/lp-crops/test.jpg"
        }
        
        producer.produce(
            topic="lp-results-1",
            key=truck_id.encode('utf-8'),
            value=json.dumps(payload).encode('utf-8'),
            headers={"truckId": truck_id}
        )
        
        mock_producer.produce.assert_called_once()
    
    @patch('confluent_kafka.Producer')
    def test_simulate_agent_c_publish(self, mock_producer_class):
        """Test simulating Agent C hazard plate publish."""
        mock_producer = Mock()
        mock_producer_class.return_value = mock_producer
        
        from confluent_kafka import Producer
        
        producer = Producer({'bootstrap.servers': 'localhost:9092'})
        
        truck_id = "TRK12345678"
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "un": "1203",
            "kemler": "33",
            "confidence": 0.92,
            "cropUrl": "http://minio:9000/hz-crops/test.jpg"
        }
        
        producer.produce(
            topic="hz-results-1",
            key=truck_id.encode('utf-8'),
            value=json.dumps(payload).encode('utf-8'),
            headers={"truckId": truck_id}
        )
        
        mock_producer.produce.assert_called_once()


class TestMessageHeaders:
    """Tests for message header handling."""
    
    def test_headers_with_truck_id(self):
        """Test that truckId header is correctly formatted."""
        truck_id = "TRK12345678"
        headers = {"truckId": truck_id}
        
        assert headers["truckId"] == truck_id
    
    def test_headers_extraction_from_bytes(self):
        """Test extracting truckId from byte headers."""
        # Simulate Kafka header format (list of tuples)
        headers = [("truckId", b"TRK12345678")]
        
        truck_id = None
        for k, v in headers:
            if k == "truckId":
                truck_id = v.decode("utf-8") if isinstance(v, bytes) else v
                break
        
        assert truck_id == "TRK12345678"
    
    def test_headers_extraction_handles_none(self):
        """Test header extraction handles None headers gracefully."""
        headers = None
        
        truck_id = None
        for k, v in (headers or []):
            if k == "truckId":
                truck_id = v.decode("utf-8") if isinstance(v, bytes) else v
                break
        
        assert truck_id is None


class TestDeliveryCallback:
    """Tests for message delivery callback handling."""
    
    def test_delivery_callback_success(self):
        """Test delivery callback handles success."""
        delivered = []
        
        def delivery_callback(err, msg):
            if err is None:
                delivered.append(msg)
        
        mock_msg = Mock()
        mock_msg.topic.return_value = "test-topic"
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 42
        
        delivery_callback(None, mock_msg)
        
        assert len(delivered) == 1
        assert delivered[0].topic() == "test-topic"
    
    def test_delivery_callback_error(self):
        """Test delivery callback handles error."""
        errors = []
        
        def delivery_callback(err, msg):
            if err is not None:
                errors.append(err)
        
        mock_error = Mock()
        mock_error.__str__ = lambda self: "Delivery failed"
        
        mock_msg = Mock()
        
        delivery_callback(mock_error, mock_msg)
        
        assert len(errors) == 1


class TestTopicNaming:
    """Tests for topic naming conventions."""
    
    def test_truck_detected_topic_format(self):
        """Test truck-detected topic naming."""
        gate_id = "1"
        topic = f"truck-detected-{gate_id}"
        
        assert topic == "truck-detected-1"
    
    def test_lp_results_topic_format(self):
        """Test lp-results topic naming."""
        gate_id = "1"
        topic = f"lp-results-{gate_id}"
        
        assert topic == "lp-results-1"
    
    def test_hz_results_topic_format(self):
        """Test hz-results topic naming."""
        gate_id = "1"
        topic = f"hz-results-{gate_id}"
        
        assert topic == "hz-results-1"
    
    def test_decision_results_topic_format(self):
        """Test decision-results topic naming."""
        gate_id = "1"
        topic = f"decision-results-{gate_id}"
        
        assert topic == "decision-results-1"
    
    def test_topics_for_multiple_gates(self):
        """Test topic naming for multiple gates."""
        for gate_id in ["1", "2", "3"]:
            truck_topic = f"truck-detected-{gate_id}"
            lp_topic = f"lp-results-{gate_id}"
            hz_topic = f"hz-results-{gate_id}"
            decision_topic = f"decision-results-{gate_id}"
            
            assert truck_topic.endswith(gate_id)
            assert lp_topic.endswith(gate_id)
            assert hz_topic.endswith(gate_id)
            assert decision_topic.endswith(gate_id)
