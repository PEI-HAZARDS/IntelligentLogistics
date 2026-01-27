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
        "image_storage": MagicMock(),
        "drawer": MagicMock()
    }

@pytest.fixture
def agent_a(mock_dependencies):
    agent = AgentA(**mock_dependencies)
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

    def test_init_uses_injected_dependencies(self, mock_dependencies):
        """Review that injected dependencies are used."""
        agent = AgentA(**mock_dependencies)
        
        assert agent.yolo is mock_dependencies["object_detector"]
        assert agent.stream_manager is mock_dependencies["stream_manager"]
        assert agent.kafka_producer is mock_dependencies["kafka_producer"]
        assert agent.image_storage is mock_dependencies["image_storage"]
        assert agent.drawer is mock_dependencies["drawer"]

    def test_init_sets_running_true(self, mock_dependencies):
        """Review that running is set to True."""
        agent = AgentA(**mock_dependencies)
        assert agent.running is True

# =============================================================================
# Tests for _process_detection
# =============================================================================

class TestProcessDetection:
    """Tests for _process_detection method."""

    def test_process_detection_no_results(self, agent_a, sample_frame):
        """Does nothing when YOLO returns None."""
        agent_a.yolo.detect.return_value = None
        
        agent_a._process_detection(sample_frame)
        
        agent_a.kafka_producer.produce.assert_not_called()

    def test_process_detection_no_truck_detected(self, agent_a, sample_frame):
        """Does nothing when no truck is detected."""
        results = MagicMock()
        agent_a.yolo.detect.return_value = results
        agent_a.yolo.object_found.return_value = False
        
        agent_a._process_detection(sample_frame)
        
        agent_a.kafka_producer.produce.assert_not_called()

    def test_process_detection_throttled(self, agent_a, sample_frame):
        """Does not publish if within message interval."""
        results = MagicMock()
        agent_a.yolo.detect.return_value = results
        agent_a.yolo.object_found.return_value = True
        
        # Simulate recent message
        agent_a.last_message_time = time.time()
        
        agent_a._process_detection(sample_frame)
        
        agent_a.kafka_producer.produce.assert_not_called()

    def test_process_detection_publishes_event(self, agent_a, sample_frame):
        """Publishes event when truck detected and not throttled."""
        results = MagicMock()
        agent_a.yolo.detect.return_value = results
        agent_a.yolo.object_found.return_value = True
        # Mock boxes: [x1, y1, x2, y2, confidence]
        agent_a.yolo.get_boxes.return_value = [[10, 10, 50, 50, 0.95]]
        
        # Ensure not throttled
        agent_a.last_message_time = 0
        
        agent_a._process_detection(sample_frame)
        
        # Check Kafka publish
        agent_a.kafka_producer.produce.assert_called_once()
        args = agent_a.kafka_producer.produce.call_args
        topic, payload = args[0]
        headers = args[1]["headers"]
        
        assert "truck-detected" in topic
        assert payload["confidence"] == 0.95
        assert payload["detections"] == 1
        assert "truckId" in headers

    def test_process_detection_uploads_image(self, agent_a, sample_frame):
        """Uploads annotated image when truck detected."""
        results = MagicMock()
        agent_a.yolo.detect.return_value = results
        agent_a.yolo.object_found.return_value = True
        agent_a.yolo.get_boxes.return_value = [[10, 10, 50, 50, 0.95]]
        agent_a.last_message_time = 0
        agent_a.drawer.draw_box.return_value = sample_frame
        
        agent_a._process_detection(sample_frame)
        
        agent_a.image_storage.upload_memory_image.assert_called_once()

    def test_process_detection_handles_drawing_error(self, agent_a, sample_frame):
        """Handles fail to draw/upload gracefully."""
        results = MagicMock()
        agent_a.yolo.detect.return_value = results
        agent_a.yolo.object_found.return_value = True
        agent_a.yolo.get_boxes.return_value = [[10, 10, 50, 50, 0.95]]
        agent_a.last_message_time = 0
        
        # Simulate drawing error
        agent_a.drawer.draw_box.side_effect = Exception("Draw error")
        
        agent_a._process_detection(sample_frame)
        
        # Should still try to publish kafka even if image fail
        agent_a.kafka_producer.produce.assert_called_once()

    def test_process_detection_handles_kafka_error(self, agent_a, sample_frame):
        """Handles Kafka publish error."""
        results = MagicMock()
        agent_a.yolo.detect.return_value = results
        agent_a.yolo.object_found.return_value = True
        agent_a.yolo.get_boxes.return_value = [[10, 10, 50, 50, 0.95]]
        agent_a.last_message_time = 0
        
        agent_a.kafka_producer.produce.side_effect = Exception("Kafka error")
        
        # Should not raise exception
        agent_a._process_detection(sample_frame)

# =============================================================================
# Tests for loop
# =============================================================================

class TestLoop:
    """Tests for _loop method."""

    def test_loop_reads_frames(self, agent_a, sample_frame):
        """Loop reads frames and processes them."""
        # Run one iteration
        agent_a.running = True
        agent_a.stream_manager.read.side_effect = [sample_frame, KeyboardInterrupt()] # Frame then stop
        
        # Mock process to verify call
        with patch.object(agent_a, '_process_detection') as mock_process:
            try:
               agent_a._loop()
            except KeyboardInterrupt:
                pass
            
            mock_process.assert_called_once_with(sample_frame)

    def test_loop_handles_none_frame(self, agent_a):
        """Loop handles None frames (retries)."""
        agent_a.running = True
        agent_a.stream_manager.read.side_effect = [None, KeyboardInterrupt()]
        
        with patch.object(agent_a, '_process_detection') as mock_process:
            try:
                agent_a._loop()
            except KeyboardInterrupt:
                pass
            
            mock_process.assert_not_called()

    def test_loop_handles_exception(self, agent_a):
        """Loop robust to exceptions."""
        agent_a.running = True
        agent_a.stream_manager.read.side_effect = [Exception("Stream error"), KeyboardInterrupt()]
        
        with patch.object(agent_a, '_process_detection') as mock_process:
            try:
                agent_a._loop()
            except KeyboardInterrupt:
                pass
            
            mock_process.assert_not_called()

# =============================================================================
# Tests for stop
# =============================================================================

class TestStop:
    """Tests for stop method."""

    def test_stop_sets_running_false(self, agent_a):
        agent_a.running = True
        agent_a.stop()
        assert agent_a.running is False
