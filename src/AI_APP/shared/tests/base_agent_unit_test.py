"""
Unit tests for shared/src/base_agent.py

Tests cover:
- BaseAgent initialization
- Configuration loading
- Main loop and message processing
- Frame management
- Detection pipeline
- Publishing
- Cleanup

Since BaseAgent is abstract, we create a concrete TestAgent subclass for testing.
All external dependencies are mocked.
"""

import pytest
import numpy as np
import os
from unittest.mock import patch, MagicMock, PropertyMock
from queue import Queue, Empty
import time


# =============================================================================
# Concrete test implementation of BaseAgent
# =============================================================================

class MockTestAgent:
    """A mock concrete implementation of BaseAgent for testing."""
    
    def get_agent_name(self):
        return "TestAgent"
    
    def get_bbox_color(self):
        return "green"
    
    def get_bbox_label(self):
        return "test"
    
    def get_yolo_model_path(self):
        return "/path/to/model.pt"
    
    def get_annotated_frames_bucket(self):
        return "test-annotated"
    
    def get_crops_bucket(self):
        return "test-crops"
    
    def get_consume_topic(self):
        return "test-consume-topic"
    
    def get_produce_topic(self):
        return "test-produce-topic"
    
    def is_valid_detection(self, crop, confidence, box_index):
        return confidence > 0.5
    
    def build_publish_payload(self, truck_id, detection_result, confidence, crop_url):
        return {
            "truckId": truck_id,
            "result": detection_result,
            "confidence": confidence,
            "cropUrl": crop_url,
        }
    
    def init_metrics(self):
        self.frames_processed_metric = MagicMock()
        self.inference_latency = MagicMock()
    
    def get_object_type(self):
        return "test object"


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_dependencies():
    """Create mock dependencies for BaseAgent testing."""
    return {
        "stream_manager": MagicMock(),
        "object_detector": MagicMock(),
        "ocr": MagicMock(),
        "classifier": MagicMock(),
        "drawer": MagicMock(),
        "annotated_frames_storage": MagicMock(),
        "crop_storage": MagicMock(),
        "kafka_producer": MagicMock(),
        "kafka_consumer": MagicMock(),
        "consensus_algorithm": MagicMock(),
    }


@pytest.fixture
def sample_frame():
    """Create a sample video frame."""
    return np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)


@pytest.fixture
def sample_crop():
    """Create a sample crop image."""
    return np.random.randint(0, 255, (50, 100, 3), dtype=np.uint8)


# =============================================================================
# Helper to create a test agent
# =============================================================================

def create_test_agent(mock_deps):
    """Create a concrete test agent instance with mocked dependencies."""
    from base_agent import BaseAgent
    
    # Create a concrete subclass
    class ConcreteTestAgent(BaseAgent):
        def get_agent_name(self):
            return "TestAgent"
        
        def get_bbox_color(self):
            return "green"
        
        def get_bbox_label(self):
            return "test"
        
        def get_yolo_model_path(self):
            return "/path/to/model.pt"
        
        def get_annotated_frames_bucket(self):
            return "test-annotated"
        
        def get_crops_bucket(self):
            return "test-crops"
        
        def get_consume_topic(self):
            return "test-consume-topic"
        
        def get_produce_topic(self):
            return "test-produce-topic"
        
        def is_valid_detection(self, crop, confidence, box_index):
            return confidence > 0.5
        
        def build_publish_payload(self, truck_id, detection_result, confidence, crop_url):
            return {
                "truckId": truck_id,
                "result": detection_result,
                "confidence": confidence,
                "cropUrl": crop_url,
            }
        
        def init_metrics(self):
            self.frames_processed_metric = MagicMock()
            self.inference_latency = MagicMock()
        
        def get_object_type(self):
            return "test object"
    
    # Pass mocks directly using dependency injection
    return ConcreteTestAgent(**mock_deps)


# =============================================================================
# Tests for __init__ and _load_config
# =============================================================================

class TestBaseAgentInit:
    """Tests for BaseAgent initialization."""

    def test_initialization_creates_components(self, mock_dependencies):
        """Initialization creates all required components."""
        # Act
        agent = create_test_agent(mock_dependencies)

        # Assert
        assert agent.agent_name == "TestAgent"
        assert agent.running is True
        assert isinstance(agent.frames_queue, Queue)
        # Verify injected mocks are used
        assert agent.stream_manager is mock_dependencies["stream_manager"]
        assert agent.yolo is mock_dependencies["object_detector"]
        assert agent.ocr is mock_dependencies["ocr"]

    def test_load_config_sets_defaults(self, mock_dependencies):
        """_load_config sets default values from environment."""
        # Arrange
        with patch.dict(os.environ, {}, clear=True):
            # Act
            agent = create_test_agent(mock_dependencies)

            # Assert
            assert agent.gate_id == "1"  # Default
            assert "rtmp://" in agent.stream_url
            assert "gate1" in agent.stream_url

    def test_load_config_uses_env_vars(self, mock_dependencies):
        """_load_config uses environment variables when set."""
        # Arrange
        env_vars = {
            "NGINX_RTMP_HOST": "192.168.1.100",
            "NGINX_RTMP_PORT": "2000",
            "GATE_ID": "5",
            "KAFKA_BOOTSTRAP": "kafka-host:9094",
            "MINIO_HOST": "minio-host",
            "MINIO_PORT": "9001",
            "MAX_FRAMES": "100",
            "MIN_DETECTION_CONFIDENCE": "0.6",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            # Act
            agent = create_test_agent(mock_dependencies)

            # Assert
            assert agent.gate_id == "5"
            assert "192.168.1.100" in agent.stream_url
            assert "gate5" in agent.stream_url
            assert agent.kafka_bootstrap == "kafka-host:9094"
            assert agent.MAX_FRAMES == 100.0
            assert agent.MIN_DETECTION_CONFIDENCE == 0.6


# =============================================================================
# Tests for loop
# =============================================================================

class TestLoop:
    """Tests for the main processing loop."""

    def test_loop_clears_stale_messages_on_start(self, mock_dependencies):
        """Loop clears stale messages on startup."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent.running = False  # Stop immediately
        
        # Act
        agent.loop()

        # Assert
        agent.kafka_consumer.clear_stale_messages.assert_called_once()

    def test_loop_processes_valid_messages(self, mock_dependencies):
        """Loop processes valid messages."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        
        mock_msg = MagicMock()
        mock_msg.error.return_value = None
        mock_msg.headers.return_value = [("truckId", b"TRUCK123")]
        
        agent.kafka_consumer.consume_message.side_effect = [mock_msg, None]
        agent.consensus_algorithm.consensus_reached = False
        agent.consensus_algorithm.best_crop = None
        agent.consensus_algorithm.get_best_partial_result.return_value = (None, None, None)
        
        # Mock _process_message to stop the loop
        call_count = [0]
        original_running = [True]
        
        def stop_after_first(*args):
            call_count[0] += 1
            if call_count[0] >= 1:
                agent.running = False
        
        agent._process_message = MagicMock(side_effect=stop_after_first)
        
        # Act
        agent.loop()

        # Assert
        agent._process_message.assert_called_once_with(mock_msg)

    def test_loop_recovers_from_keyboard_interrupt(self, mock_dependencies):
        """Loop handles KeyboardInterrupt gracefully."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent.kafka_consumer.consume_message.side_effect = KeyboardInterrupt()

        # Act - should not raise
        agent.loop()

        # Assert
        agent.stream_manager.release.assert_called_once()


# =============================================================================
# Tests for stop
# =============================================================================

class TestStop:
    """Tests for the stop method."""

    def test_stop_sets_running_false(self, mock_dependencies):
        """Stop sets running to False."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        assert agent.running is True

        # Act
        agent.stop()

        # Assert
        assert agent.running is False


# =============================================================================
# Tests for frame management
# =============================================================================

class TestFrameManagement:
    """Tests for frame management methods."""

    def test_get_next_frame_from_queue(self, mock_dependencies, sample_frame):
        """_get_next_frame returns frame from queue."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent.frames_queue.put(sample_frame)

        # Act
        result = agent._get_next_frame()

        # Assert
        assert np.array_equal(result, sample_frame)

    def test_get_next_frame_captures_more_when_empty(self, mock_dependencies, sample_frame):
        """_get_next_frame captures more frames when queue is empty."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent.stream_manager.read.return_value = sample_frame

        # Act
        result = agent._get_next_frame()

        # Assert
        agent.stream_manager.read.assert_called()

    def test_get_next_frame_returns_none_on_empty(self, mock_dependencies):
        """_get_next_frame returns None when no frames available."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent.stream_manager.read.return_value = None
        agent.running = False  # Prevent infinite loop in _get_frames

        # Act
        result = agent._get_next_frame()

        # Assert
        assert result is None

    def test_clear_frames_queue_empties_queue(self, mock_dependencies, sample_frame):
        """_clear_frames_queue removes all frames."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        for i in range(5):
            agent.frames_queue.put(sample_frame)
        assert agent.frames_queue.qsize() == 5

        # Act
        agent._clear_frames_queue()

        # Assert
        assert agent.frames_queue.empty()


# =============================================================================
# Tests for detection pipeline
# =============================================================================

class TestDetectionPipeline:
    """Tests for detection pipeline methods."""

    def test_should_continue_processing_happy_path(self, mock_dependencies):
        """_should_continue_processing returns True when conditions met."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent.running = True
        agent.consensus_algorithm.consensus_reached = False
        agent.frames_processed = 10
        agent.MAX_FRAMES = 40

        # Act
        result = agent._should_continue_processing()

        # Assert
        assert result is True

    def test_should_continue_processing_stops_at_max_frames(self, mock_dependencies):
        """_should_continue_processing returns False at max frames."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent.running = True
        agent.consensus_algorithm.consensus_reached = False
        agent.frames_processed = 40
        agent.MAX_FRAMES = 40

        # Act
        result = agent._should_continue_processing()

        # Assert
        assert result is False

    def test_should_continue_processing_stops_on_consensus(self, mock_dependencies):
        """_should_continue_processing returns False when consensus reached."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent.running = True
        agent.consensus_algorithm.consensus_reached = True
        agent.frames_processed = 10
        agent.MAX_FRAMES = 40

        # Act
        result = agent._should_continue_processing()

        # Assert
        assert result is False

    def test_run_yolo_detection_returns_boxes(self, mock_dependencies, sample_frame):
        """_run_yolo_detection returns detected boxes."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        mock_results = MagicMock()
        agent.yolo.detect.return_value = mock_results
        agent.yolo.object_found.return_value = True
        agent.yolo.get_boxes.return_value = [[10, 20, 50, 60, 0.9]]
        agent.drawer.draw_box.return_value = sample_frame

        # Act
        result = agent._run_yolo_detection(sample_frame)

        # Assert
        assert result == [[10, 20, 50, 60, 0.9]]

    def test_run_yolo_detection_returns_none_no_object(self, mock_dependencies, sample_frame):
        """_run_yolo_detection returns None when no object found."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        mock_results = MagicMock()
        agent.yolo.detect.return_value = mock_results
        agent.yolo.object_found.return_value = False

        # Act
        result = agent._run_yolo_detection(sample_frame)

        # Assert
        assert result is None

    def test_extract_crop_valid_detection(self, mock_dependencies, sample_frame):
        """_extract_crop returns crop for valid detection."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent.MIN_DETECTION_CONFIDENCE = 0.4
        box = [10, 20, 50, 60, 0.9]  # High confidence

        # Act
        crop, conf = agent._extract_crop(box, sample_frame, 1)

        # Assert
        assert crop is not None
        assert conf == 0.9

    def test_extract_crop_low_confidence_ignored(self, mock_dependencies, sample_frame):
        """_extract_crop returns None for low confidence."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent.MIN_DETECTION_CONFIDENCE = 0.5
        box = [10, 20, 50, 60, 0.3]  # Low confidence

        # Act
        crop, conf = agent._extract_crop(box, sample_frame, 1)

        # Assert
        assert crop is None
        assert conf is None


# =============================================================================
# Tests for OCR processing
# =============================================================================

class TestOCRProcessing:
    """Tests for OCR processing."""

    def test_process_ocr_result_on_consensus(self, mock_dependencies, sample_crop):
        """_process_ocr_result returns result when consensus reached."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent.ocr._extract_text.return_value = ("ABC123", 0.95)
        agent.consensus_algorithm.check_full_consensus.return_value = True
        agent.consensus_algorithm.build_final_text.return_value = "ABC123"
        agent.consensus_algorithm.select_best_crop.return_value = sample_crop

        # Act
        result = agent._process_ocr_result(sample_crop, 1)

        # Assert
        assert result is not None
        text, conf, crop = result
        assert text == "ABC123"
        assert conf == 1.0

    def test_process_ocr_result_no_consensus(self, mock_dependencies, sample_crop):
        """_process_ocr_result returns None when no consensus."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent.ocr._extract_text.return_value = ("ABC123", 0.95)
        agent.consensus_algorithm.check_full_consensus.return_value = False

        # Act
        result = agent._process_ocr_result(sample_crop, 1)

        # Assert
        assert result is None

    def test_process_ocr_result_empty_text(self, mock_dependencies, sample_crop):
        """_process_ocr_result returns None for empty text."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent.ocr._extract_text.return_value = ("", 0.0)

        # Act
        result = agent._process_ocr_result(sample_crop, 1)

        # Assert
        assert result is None


# =============================================================================
# Tests for truck ID extraction
# =============================================================================

class TestTruckIdExtraction:
    """Tests for truck ID extraction from headers."""

    def test_extract_truck_id_from_bytes(self, mock_dependencies):
        """Extracts truck ID from bytes header."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        mock_msg = MagicMock()
        mock_msg.headers.return_value = [("truckId", b"TRUCK-123")]

        # Act
        result = agent._extract_truck_id(mock_msg)

        # Assert
        assert result == "TRUCK-123"

    def test_extract_truck_id_from_string(self, mock_dependencies):
        """Extracts truck ID from string header."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        mock_msg = MagicMock()
        mock_msg.headers.return_value = [("truckId", "TRUCK-456")]

        # Act
        result = agent._extract_truck_id(mock_msg)

        # Assert
        assert result == "TRUCK-456"

    def test_extract_truck_id_generates_uuid_if_missing(self, mock_dependencies):
        """Generates UUID if truckId header missing."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        mock_msg = MagicMock()
        mock_msg.headers.return_value = []

        # Act
        result = agent._extract_truck_id(mock_msg)

        # Assert
        assert result is not None
        assert len(result) > 0  # UUID generated


# =============================================================================
# Tests for upload and publish
# =============================================================================

class TestUploadAndPublish:
    """Tests for upload and publish methods."""

    def test_upload_crop_to_storage_success(self, mock_dependencies, sample_crop):
        """_upload_crop_to_storage uploads crop and returns URL."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent.truck_id = "TRUCK-123"
        agent.consensus_algorithm.best_crop = sample_crop
        agent.crop_storage.upload_memory_image.return_value = "http://minio/crop.jpg"

        # Act
        result = agent._upload_crop_to_storage("ABC123")

        # Assert
        assert result == "http://minio/crop.jpg"
        agent.crop_storage.upload_memory_image.assert_called_once()

    def test_upload_crop_to_storage_no_crop(self, mock_dependencies):
        """_upload_crop_to_storage returns None when no best crop."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent.truck_id = "TRUCK-123"
        agent.consensus_algorithm.best_crop = None

        # Act
        result = agent._upload_crop_to_storage("ABC123")

        # Assert
        assert result is None

    def test_publish_detection_sends_to_kafka(self, mock_dependencies):
        """_publish_detection publishes to Kafka."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent.truck_id = "TRUCK-123"

        # Act
        agent._publish_detection({"text": "ABC123"}, 0.95, "http://minio/crop.jpg")

        # Assert
        agent.kafka_producer.produce.assert_called_once()
        call_args = agent.kafka_producer.produce.call_args
        assert call_args[0][0] == "test-produce-topic"


# =============================================================================
# Tests for message processing
# =============================================================================

class TestMessageProcessing:
    """Tests for message processing."""

    def test_process_message_full_pipeline(self, mock_dependencies, sample_crop):
        """_process_message runs full detection pipeline."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        
        mock_msg = MagicMock()
        mock_msg.headers.return_value = [("truckId", b"TRUCK-123")]
        
        # Mock process_detection to return a result
        agent.consensus_algorithm.consensus_reached = False
        agent.consensus_algorithm.get_best_partial_result.return_value = ("ABC123", 0.95, sample_crop)
        agent.crop_storage.upload_memory_image.return_value = "http://minio/crop.jpg"
        
        # Make process_detection return immediately
        original_process = agent.process_detection
        agent.process_detection = MagicMock(return_value=("ABC123", 0.95, sample_crop))

        # Act
        agent._process_message(mock_msg)

        # Assert
        agent.kafka_producer.produce.assert_called_once()

    def test_process_message_handles_no_text(self, mock_dependencies, sample_crop):
        """_process_message handles missing text."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        
        mock_msg = MagicMock()
        mock_msg.headers.return_value = [("truckId", b"TRUCK-123")]
        
        # Return no text but has crop
        agent.process_detection = MagicMock(return_value=(None, 0.5, sample_crop))
        agent.crop_storage.upload_memory_image.return_value = "http://minio/crop.jpg"

        # Act
        agent._process_message(mock_msg)

        # Assert
        # Should publish with N/A text
        call_args = agent.kafka_producer.produce.call_args
        payload = call_args[0][1]
        assert payload["result"]["text"] == "N/A"


# =============================================================================
# Tests for cleanup
# =============================================================================

class TestCleanup:
    """Tests for resource cleanup."""

    def test_cleanup_resources_releases_stream(self, mock_dependencies):
        """_cleanup_resources releases stream manager."""
        # Arrange
        agent = create_test_agent(mock_dependencies)

        # Act
        agent._cleanup_resources()

        # Assert
        agent.stream_manager.release.assert_called_once()

    def test_cleanup_resources_flushes_kafka(self, mock_dependencies):
        """_cleanup_resources flushes Kafka producer."""
        # Arrange
        agent = create_test_agent(mock_dependencies)

        # Act
        agent._cleanup_resources()

        # Assert
        agent.kafka_producer.flush.assert_called_once()


# =============================================================================
# Tests for parse_detection_result
# =============================================================================

class TestParseDetectionResult:
    """Tests for detection result parsing."""

    def test_parse_detection_result_default(self, mock_dependencies):
        """_parse_detection_result returns text as dict."""
        # Arrange
        agent = create_test_agent(mock_dependencies)

        # Act
        result = agent._parse_detection_result("ABC123")

        # Assert
        assert result == {"text": "ABC123"}


# =============================================================================
# Tests for process_detection
# =============================================================================

class TestProcessDetection:
    """Tests for the main detection pipeline."""

    def test_process_detection_resets_consensus(self, mock_dependencies):
        """process_detection resets consensus at start."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent.running = False
        agent.consensus_algorithm.get_best_partial_result.return_value = (None, None, None)

        # Act
        agent.process_detection()

        # Assert
        agent.consensus_algorithm.reset.assert_called_once()

    def test_process_detection_returns_on_consensus(self, mock_dependencies, sample_frame, sample_crop):
        """process_detection processes frames and returns result."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent.running = False  # Stop immediately to test return path
        agent.consensus_algorithm.get_best_partial_result.return_value = ("ABC123", 0.95, sample_crop)

        # Act
        result = agent.process_detection()

        # Assert
        assert agent.consensus_algorithm.reset.called
        assert result == ("ABC123", 0.95, sample_crop)

    def test_process_detection_returns_partial_at_max_frames(self, mock_dependencies, sample_crop):
        """process_detection returns partial result at max frames."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent.MAX_FRAMES = 1
        agent.frames_queue.put(np.zeros((480, 640, 3), dtype=np.uint8))
        
        # Mock no detection
        agent.yolo.detect.return_value = None
        agent.consensus_algorithm.get_best_partial_result.return_value = ("AB_123", 0.7, sample_crop)

        # Act
        text, conf, crop = agent.process_detection()

        # Assert
        assert text == "AB_123"
        assert conf == 0.7


# =============================================================================
# Tests for _process_single_frame
# =============================================================================

class TestProcessSingleFrame:
    """Tests for _process_single_frame method."""

    def test_process_single_frame_returns_none_when_no_boxes(self, mock_dependencies, sample_frame):
        """_process_single_frame returns None when YOLO finds no boxes."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent._run_yolo_detection = MagicMock(return_value=None)

        # Act
        result = agent._process_single_frame(sample_frame)

        # Assert
        assert result is None

    def test_process_single_frame_processes_boxes(self, mock_dependencies, sample_frame, sample_crop):
        """_process_single_frame processes detected boxes."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent._run_yolo_detection = MagicMock(return_value=[[10, 20, 50, 60, 0.9]])
        agent._extract_crop = MagicMock(return_value=(sample_crop, 0.9))
        agent._process_ocr_result = MagicMock(return_value=("ABC123", 1.0, sample_crop))

        # Act
        result = agent._process_single_frame(sample_frame)

        # Assert
        assert result == ("ABC123", 1.0, sample_crop)
        agent.consensus_algorithm.add_candidate_crop.assert_called()

    def test_process_single_frame_skips_invalid_crops(self, mock_dependencies, sample_frame):
        """_process_single_frame skips boxes with invalid crops."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent._run_yolo_detection = MagicMock(return_value=[[10, 20, 50, 60, 0.9]])
        agent._extract_crop = MagicMock(return_value=(None, None))

        # Act
        result = agent._process_single_frame(sample_frame)

        # Assert
        assert result is None

    def test_process_single_frame_handles_ocr_exception(self, mock_dependencies, sample_frame, sample_crop):
        """_process_single_frame handles OCR exceptions gracefully."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent._run_yolo_detection = MagicMock(return_value=[[10, 20, 50, 60, 0.9]])
        agent._extract_crop = MagicMock(return_value=(sample_crop, 0.9))
        agent._process_ocr_result = MagicMock(side_effect=Exception("OCR Error"))

        # Act
        result = agent._process_single_frame(sample_frame)

        # Assert
        assert result is None

    def test_process_single_frame_handles_frame_exception(self, mock_dependencies, sample_frame):
        """_process_single_frame handles frame processing exceptions."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent._run_yolo_detection = MagicMock(side_effect=Exception("Detection Error"))

        # Act
        result = agent._process_single_frame(sample_frame)

        # Assert
        assert result is None


# =============================================================================
# Tests for _get_frames
# =============================================================================

class TestGetFrames:
    """Tests for _get_frames method."""

    def test_get_frames_captures_frames(self, mock_dependencies, sample_frame):
        """_get_frames captures specified number of frames."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent.stream_manager.read.return_value = sample_frame

        # Act
        agent._get_frames(3)

        # Assert
        assert agent.frames_queue.qsize() == 3

    def test_get_frames_handles_none_frames(self, mock_dependencies):
        """_get_frames handles None from stream gracefully."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent.running = False  # Prevent infinite loop
        agent.stream_manager.read.return_value = None

        # Act
        agent._get_frames(3)

        # Assert
        assert agent.frames_queue.empty()

    def test_get_frames_handles_exception(self, mock_dependencies):
        """_get_frames handles stream exceptions gracefully."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent.running = False  # Prevent infinite loop
        agent.stream_manager.read.side_effect = Exception("Stream error")

        # Act - should not raise
        agent._get_frames(3)

        # Assert
        assert agent.frames_queue.empty()


# =============================================================================
# Tests for loop error handling
# =============================================================================

class TestLoopErrorHandling:
    """Tests for error handling in the main loop."""

    def test_loop_handles_kafka_exception(self, mock_dependencies):
        """Loop handles KafkaException gracefully."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        from confluent_kafka import KafkaException
        agent.kafka_consumer.consume_message.side_effect = KafkaException("Kafka error")

        # Act - should not raise
        agent.loop()

        # Assert
        agent.stream_manager.release.assert_called()

    def test_loop_handles_unexpected_exception(self, mock_dependencies):
        """Loop handles unexpected exceptions gracefully."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent.kafka_consumer.consume_message.side_effect = RuntimeError("Unexpected")

        # Act - should not raise
        agent.loop()

        # Assert
        agent.stream_manager.release.assert_called()


# =============================================================================
# Tests for _upload_crop_to_storage error path
# =============================================================================

class TestUploadCropErrors:
    """Tests for _upload_crop_to_storage error handling."""

    def test_upload_crop_handles_exception(self, mock_dependencies, sample_crop):
        """_upload_crop_to_storage handles upload exceptions."""
        # Arrange
        agent = create_test_agent(mock_dependencies)
        agent.truck_id = "TRUCK-123"
        agent.consensus_algorithm.best_crop = sample_crop
        agent.crop_storage.upload_memory_image.side_effect = Exception("Upload failed")

        # Act
        result = agent._upload_crop_to_storage("ABC123")

        # Assert
        assert result is None
