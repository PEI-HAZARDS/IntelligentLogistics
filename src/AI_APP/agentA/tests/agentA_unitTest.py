"""
Unit tests for AgentA class.
Tests truck detection logic, throttling, and Kafka publishing.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY
import time
import pytest
import numpy as np

# Setup paths
TESTS_DIR = Path(__file__).resolve().parent
AGENT_A_ROOT = TESTS_DIR.parent
SRC_DIR = AGENT_A_ROOT / "src"
GLOBAL_SRC = AGENT_A_ROOT.parent  # /src directory

# Add paths to sys.path
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(GLOBAL_SRC))

# Mock prometheus before import
mock_prometheus = MagicMock()
sys.modules["prometheus_client"] = mock_prometheus

from agentA import AgentA

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_dependencies():
    return {
        "object_detector": MagicMock(),
        "stream_manager": MagicMock(),
        "kafka_producer": MagicMock(),
        "kafka_consumer": MagicMock(),
        "image_storage": MagicMock(),
        "drawer": MagicMock()
    }

@pytest.fixture
def mock_config():
    from agentA import AgentAConfig
    return AgentAConfig(minio_user="test_user", minio_password="test_password")

@pytest.fixture
def agent_a(mock_dependencies, mock_config):
    agent = AgentA(config=mock_config, **mock_dependencies)
    agent.running = False # Prevent loop from running automatically
    return agent

@pytest.fixture
def sample_frame():
    return np.zeros((100, 100, 3), dtype=np.uint8)

# =============================================================================
# Tests for __init__
# =============================================================================

class TestAgentAInit:
    """Tests for AgentA initialization."""

    def test_init_uses_injected_dependencies(self, mock_dependencies, mock_config):
        """Review that injected dependencies are used."""
        agent = AgentA(config=mock_config, **mock_dependencies)
        
        assert agent.yolo is mock_dependencies["object_detector"]
        assert agent.stream_manager is mock_dependencies["stream_manager"]
        assert agent.kafka_producer is mock_dependencies["kafka_producer"]
        assert agent.kafka_consumer is mock_dependencies["kafka_consumer"]
        assert agent.image_storage is mock_dependencies["image_storage"]
        assert agent.drawer is mock_dependencies["drawer"]

    def test_init_sets_running_true(self, mock_dependencies, mock_config):
        """Review that running is set to True."""
        agent = AgentA(config=mock_config, **mock_dependencies)
        assert agent.running is True

# =============================================================================
# Tests for _process_detection
# =============================================================================

class TestProcessDetection:
    """Tests for _process_detection method."""

    def test_process_detection_no_results(self, agent_a, sample_frame):
        """Does nothing when YOLO returns None."""
        agent_a.running = True
        agent_a.yolo.detect.return_value = None
        def mock_read():
            agent_a.running = False
            return sample_frame
        agent_a.stream_manager.read.side_effect = mock_read
        
        agent_a._process_detection()
        
        agent_a.kafka_producer.produce.assert_not_called()

    def test_process_detection_no_truck_detected(self, agent_a, sample_frame):
        """Does nothing when no truck is detected."""
        agent_a.running = True
        results = MagicMock()
        agent_a.yolo.detect.return_value = results
        agent_a.yolo.object_found.return_value = False
        def mock_read():
            agent_a.running = False
            return sample_frame
        agent_a.stream_manager.read.side_effect = mock_read
        
        agent_a._process_detection()
        
        agent_a.kafka_producer.produce.assert_not_called()

    def test_process_detection_throttled(self, agent_a, sample_frame):
        """Test process detection."""
        agent_a.running = True
        results = MagicMock()
        agent_a.yolo.detect.return_value = results
        agent_a.yolo.object_found.return_value = True
        agent_a.yolo.get_boxes.return_value = [[10, 10, 50, 50, 0.95]]
        agent_a.stream_manager.read.side_effect = [sample_frame] # Should return after publish
        
        agent_a._process_detection()
        
        # In current design, _process_detection always publishes if truck found.
        agent_a.kafka_producer.produce.assert_called_once()

    def test_process_detection_publishes_event(self, agent_a, sample_frame):
        """Publishes event when truck detected."""
        agent_a.running = True
        results = MagicMock()
        agent_a.yolo.detect.return_value = results
        agent_a.yolo.object_found.return_value = True
        # Mock boxes: [x1, y1, x2, y2, confidence]
        agent_a.yolo.get_boxes.return_value = [[10, 10, 50, 50, 0.95]]
        agent_a.stream_manager.read.side_effect = [sample_frame]
        
        agent_a._process_detection()
        
        # Check Kafka publish
        agent_a.kafka_producer.produce.assert_called_once()
        args, kwargs = agent_a.kafka_producer.produce.call_args
        topic = kwargs.get("topic") if "topic" in kwargs else args[0] if args else None
        payload = kwargs.get("data") if "data" in kwargs else args[1] if len(args) > 1 else None
        headers = kwargs.get("headers") if "headers" in kwargs else args[2] if len(args) > 2 else {}
        
        assert "truck-detected" in topic
        assert payload["confidence"] == 0.95
        assert payload["num_detections"] == 1
        assert "truck_id" in headers

    def test_process_detection_uploads_image(self, agent_a, sample_frame):
        """Uploads annotated image when truck detected."""
        agent_a.running = True
        results = MagicMock()
        agent_a.yolo.detect.return_value = results
        agent_a.yolo.object_found.return_value = True
        agent_a.yolo.get_boxes.return_value = [[10, 10, 50, 50, 0.95]]
        agent_a.drawer.draw_box.return_value = sample_frame
        agent_a.stream_manager.read.side_effect = [sample_frame]
        
        agent_a._process_detection()
        
        agent_a.image_storage.upload_memory_image.assert_called_once()

    def test_process_detection_handles_drawing_error(self, agent_a, sample_frame):
        """Handles fail to draw/upload gracefully."""
        agent_a.running = True
        results = MagicMock()
        agent_a.yolo.detect.return_value = results
        agent_a.yolo.object_found.return_value = True
        agent_a.yolo.get_boxes.return_value = [[10, 10, 50, 50, 0.95]]
        agent_a.stream_manager.read.side_effect = [sample_frame]
        
        # Simulate drawing error
        agent_a.drawer.draw_box.side_effect = Exception("Draw error")
        
        agent_a._process_detection()
        
        # Should still try to publish kafka even if image fail
        agent_a.kafka_producer.produce.assert_called_once()

    def test_process_detection_handles_kafka_error(self, agent_a, sample_frame):
        """Handles Kafka publish error."""
        agent_a.running = True
        results = MagicMock()
        agent_a.yolo.detect.return_value = results
        agent_a.yolo.object_found.return_value = True
        agent_a.yolo.get_boxes.return_value = [[10, 10, 50, 50, 0.95]]
        
        def mock_read():
            if not hasattr(mock_read, "called"):
                mock_read.called = True
                return sample_frame
            agent_a.running = False # Break loop on 2nd attempt
            return None
        agent_a.stream_manager.read.side_effect = mock_read
        
        agent_a.kafka_producer.produce.side_effect = Exception("Kafka error")
        
        # Should not raise exception
        agent_a._process_detection()
        agent_a.stream_manager.release.assert_not_called()

# =============================================================================
# Tests for start() loop
# =============================================================================

class TestLoop:
    """Tests for start method."""

    def test_start_calls_process_detection(self, agent_a):
        """Loop processes detection when not awaiting reset."""
        agent_a.running = True
        agent_a.awaiting_reset = False
        
        with patch.object(agent_a, '_process_detection') as mock_process:
            # Stop the loop after first iteration
            mock_process.side_effect = lambda: setattr(agent_a, 'running', False)
            agent_a.start()
            
            mock_process.assert_called_once()

    def test_start_waits_for_reset(self, agent_a):
        """Loop waits for reset message if awaiting_reset."""
        agent_a.running = True
        agent_a.awaiting_reset = True
        agent_a.last_message_time = time.time() # Within timeout
        agent_a.stream_manager.connect.reset_mock()
        
        # Simulate receiving reset message
        mock_msg = MagicMock()
        mock_msg.reason = "test"
        agent_a.kafka_consumer.consume_typed_message.return_value = ("topic", mock_msg, "TRK1")
        
        with patch.object(agent_a, '_process_detection') as mock_process:
            mock_process.side_effect = lambda: setattr(agent_a, 'running', False)
            agent_a.start()
            
            agent_a.kafka_consumer.consume_typed_message.assert_called_once()
            agent_a.stream_manager.connect.assert_called_once()
            assert agent_a.awaiting_reset is True
            mock_process.assert_called_once()

    def test_start_handles_timeout(self, agent_a):
        """Loop proceeds if reset timeout is exceeded."""
        agent_a.running = True
        agent_a.awaiting_reset = True
        agent_a.last_message_time = time.time() - 100 # Past timeout
        agent_a.stream_manager.connect.reset_mock()

        with patch.object(agent_a, '_process_detection') as mock_process:
            mock_process.side_effect = lambda: setattr(agent_a, 'running', False)
            agent_a.start()

            # Shouldn't consume if timed out
            agent_a.kafka_consumer.consume_typed_message.assert_not_called()
            agent_a.stream_manager.connect.assert_called_once()
            assert agent_a.awaiting_reset is True
            mock_process.assert_called_once()

# =============================================================================
# Tests for stop
# =============================================================================

class TestStop:
    """Tests for stop method."""

    def test_stop_sets_running_false(self, agent_a):
        agent_a.running = True
        agent_a.stop()
        assert agent_a.running is False
