"""
Comprehensive Unit Tests for Agent A
=====================================
Agent A: Truck Detection Agent
- Monitors low-quality RTSP stream
- Detects trucks using YOLO
- Publishes 'truck-detected-GATE_ID' events to Kafka
"""

import sys
import types
import math
from pathlib import Path
import json
import time
import threading
import pytest
from unittest.mock import Mock, MagicMock, patch, PropertyMock
import numpy as np

# Setup path for imports
TESTS_DIR = Path(__file__).resolve().parent
MICROSERVICE_ROOT = TESTS_DIR.parent
GLOBAL_SRC = MICROSERVICE_ROOT.parent

sys.path.insert(0, str(MICROSERVICE_ROOT / "src"))
sys.path.insert(0, str(GLOBAL_SRC))

# Mock ultralytics before importing AgentA
if "ultralytics" not in sys.modules:
    ultralytics_stub = types.ModuleType("ultralytics")
    class YOLOStub:
        def __init__(self, *args, **kwargs):
            pass
    ultralytics_stub.YOLO = YOLOStub
    sys.modules["ultralytics"] = ultralytics_stub


class TestAgentAInitialization:
    """Tests for Agent A initialization."""
    
    @patch('AgentA.Producer')
    @patch('AgentA.YOLO_Truck')
    def test_init_creates_yolo_model(self, mock_yolo, mock_producer):
        """Test that Agent A initializes YOLO model on creation."""
        from AgentA import AgentA
        
        agent = AgentA()
        
        mock_yolo.assert_called_once()
        assert agent.yolo is not None
    
    @patch('AgentA.Producer')
    @patch('AgentA.YOLO_Truck')
    def test_init_creates_kafka_producer(self, mock_yolo, mock_producer):
        """Test that Agent A initializes Kafka producer."""
        from AgentA import AgentA
        
        agent = AgentA()
        
        mock_producer.assert_called_once()
        assert agent.producer is not None
    
    @patch('AgentA.Producer')
    @patch('AgentA.YOLO_Truck')
    def test_init_sets_running_true(self, mock_yolo, mock_producer):
        """Test that Agent A starts in running state."""
        from AgentA import AgentA
        
        agent = AgentA()
        
        assert agent.running is True
    
    @patch('AgentA.Producer')
    @patch('AgentA.YOLO_Truck')
    def test_init_sets_last_message_time_to_zero(self, mock_yolo, mock_producer):
        """Test that last message time is initialized to zero."""
        from AgentA import AgentA
        
        agent = AgentA()
        
        assert agent.last_message_time == 0


class TestAgentAPublishTruckDetected:
    """Tests for the _publish_truck_detected method."""
    
    @patch('AgentA.Producer')
    @patch('AgentA.YOLO_Truck')
    def test_publish_truck_detected_sends_correct_payload(self, mock_yolo, mock_producer):
        """Test that publish sends correct JSON payload to Kafka."""
        from AgentA import AgentA
        
        mock_producer_instance = Mock()
        mock_producer.return_value = mock_producer_instance
        
        agent = AgentA()
        agent._publish_truck_detected(max_conf=0.95, num_boxes=2)
        
        # Verify produce was called
        mock_producer_instance.produce.assert_called_once()
        
        # Get the call arguments
        call_kwargs = mock_producer_instance.produce.call_args[1]
        
        # Parse the payload
        payload = json.loads(call_kwargs['value'].decode('utf-8'))
        
        assert math.isclose(payload['confidence'], 0.95, rel_tol=1e-09, abs_tol=1e-09)
        assert payload['detections'] == 2
        assert 'timestamp' in payload
    
    @patch('AgentA.Producer')
    @patch('AgentA.YOLO_Truck')
    def test_publish_truck_detected_includes_truck_id_header(self, mock_yolo, mock_producer):
        """Test that publish includes truckId in headers."""
        from AgentA import AgentA
        
        mock_producer_instance = Mock()
        mock_producer.return_value = mock_producer_instance
        
        agent = AgentA()
        agent._publish_truck_detected(max_conf=0.85, num_boxes=1)
        
        call_kwargs = mock_producer_instance.produce.call_args[1]
        headers = call_kwargs['headers']
        
        assert 'truckId' in headers
        assert headers['truckId'].startswith('TRK')
    
    @patch('AgentA.Producer')
    @patch('AgentA.YOLO_Truck')
    def test_publish_truck_detected_polls_producer(self, mock_yolo, mock_producer):
        """Test that publish calls poll(0) to trigger delivery callbacks."""
        from AgentA import AgentA
        
        mock_producer_instance = Mock()
        mock_producer.return_value = mock_producer_instance
        
        agent = AgentA()
        agent._publish_truck_detected(max_conf=0.9, num_boxes=1)
        
        mock_producer_instance.poll.assert_called_once_with(0)
    
    @patch('AgentA.Producer')
    @patch('AgentA.YOLO_Truck')
    def test_publish_truck_detected_uses_correct_topic(self, mock_yolo, mock_producer):
        """Test that message is published to correct topic."""
        from AgentA import AgentA, KAFKA_TOPIC
        
        mock_producer_instance = Mock()
        mock_producer.return_value = mock_producer_instance
        
        agent = AgentA()
        agent._publish_truck_detected(max_conf=0.9, num_boxes=1)
        
        call_kwargs = mock_producer_instance.produce.call_args[1]
        assert call_kwargs['topic'] == KAFKA_TOPIC


class TestAgentADeliveryCallback:
    """Tests for the Kafka delivery callback."""
    
    @patch('AgentA.Producer')
    @patch('AgentA.YOLO_Truck')
    def test_delivery_callback_handles_success(self, mock_yolo, mock_producer):
        """Test delivery callback handles successful delivery."""
        from AgentA import AgentA
        
        agent = AgentA()
        
        mock_msg = Mock()
        mock_msg.topic.return_value = 'test-topic'
        mock_msg.partition.return_value = 0
        mock_msg.offset.return_value = 42
        
        # Should not raise
        agent._delivery_callback(None, mock_msg)
    
    @patch('AgentA.Producer')
    @patch('AgentA.YOLO_Truck')
    def test_delivery_callback_handles_error(self, mock_yolo, mock_producer):
        """Test delivery callback logs error on failure."""
        from AgentA import AgentA
        
        agent = AgentA()
        
        mock_msg = Mock()
        mock_msg.topic.return_value = 'test-topic'
        mock_msg.partition.return_value = 0
        
        mock_error = Mock()
        mock_error.__str__ = lambda self: "Connection error"
        
        # Should not raise, just log
        agent._delivery_callback(mock_error, mock_msg)


class TestAgentAConnectionRetry:
    """Tests for stream connection with retry logic."""
    
    @patch('AgentA.Producer')
    @patch('AgentA.YOLO_Truck')
    @patch('AgentA.RTSPStream')
    def test_connect_succeeds_on_first_attempt(self, mock_rtsp, mock_yolo, mock_producer):
        """Test successful connection on first attempt."""
        from AgentA import AgentA
        
        mock_stream = Mock()
        mock_rtsp.return_value = mock_stream
        
        agent = AgentA()
        result = agent._connect_to_stream_with_retry(max_retries=3)
        
        assert result == mock_stream
        mock_rtsp.assert_called_once()
    
    @patch('AgentA.Producer')
    @patch('AgentA.YOLO_Truck')
    @patch('AgentA.RTSPStream')
    @patch('AgentA.time.sleep')
    def test_connect_retries_on_failure(self, mock_sleep, mock_rtsp, mock_yolo, mock_producer):
        """Test connection retries on failure."""
        from AgentA import AgentA
        
        mock_stream = Mock()
        mock_rtsp.side_effect = [
            ConnectionError("Failed"),
            ConnectionError("Failed"),
            mock_stream
        ]
        
        agent = AgentA()
        result = agent._connect_to_stream_with_retry(max_retries=3)
        
        assert result == mock_stream
        assert mock_rtsp.call_count == 3
        assert mock_sleep.call_count == 2
    
    @patch('AgentA.Producer')
    @patch('AgentA.YOLO_Truck')
    @patch('AgentA.RTSPStream')
    @patch('AgentA.time.sleep')
    def test_connect_raises_after_max_retries(self, mock_sleep, mock_rtsp, mock_yolo, mock_producer):
        """Test that connection raises after max retries exhausted."""
        from AgentA import AgentA
        
        mock_rtsp.side_effect = ConnectionError("Failed")
        
        agent = AgentA()
        
        with pytest.raises(ConnectionError):
            agent._connect_to_stream_with_retry(max_retries=2)
        
        assert mock_rtsp.call_count == 2


class TestAgentAStop:
    """Tests for stop functionality."""
    
    @patch('AgentA.Producer')
    @patch('AgentA.YOLO_Truck')
    def test_stop_sets_running_false(self, mock_yolo, mock_producer):
        """Test that stop sets running to False."""
        from AgentA import AgentA
        
        agent = AgentA()
        assert agent.running is True
        
        agent.stop()
        
        assert agent.running is False


class TestAgentAMainLoop:
    """Tests for the main detection loop."""
    
    @patch('AgentA.Producer')
    @patch('AgentA.YOLO_Truck')
    @patch('AgentA.RTSPStream')
    def test_loop_publishes_when_truck_detected(self, mock_rtsp, mock_yolo_class, mock_producer):
        """Test that loop publishes message when truck is detected."""
        from AgentA import AgentA
        import AgentA as agentA_module
        
        # Setup mocks
        mock_stream = Mock()
        mock_stream.read.side_effect = [np.zeros((100, 100, 3)), None]
        mock_rtsp.return_value = mock_stream
        
        mock_yolo = Mock()
        mock_results = Mock()
        mock_yolo.detect.return_value = mock_results
        mock_yolo.truck_found.return_value = True
        mock_yolo.get_boxes.return_value = [[0, 0, 100, 100, 0.95]]
        mock_yolo_class.return_value = mock_yolo
        
        mock_producer_instance = Mock()
        mock_producer.return_value = mock_producer_instance
        
        # Temporarily set MESSAGE_INTERVAL to 0
        original_interval = agentA_module.MESSAGE_INTERVAL
        agentA_module.MESSAGE_INTERVAL = 0
        
        try:
            agent = AgentA()
            agent.yolo = mock_yolo
            
            # Stop after a short time
            def stopper():
                time.sleep(0.1)
                agent.stop()
            
            threading.Thread(target=stopper, daemon=True).start()
            agent._loop()
            
            # Verify produce was called
            mock_producer_instance.produce.assert_called()
        finally:
            agentA_module.MESSAGE_INTERVAL = original_interval
    
    @patch('AgentA.Producer')
    @patch('AgentA.YOLO_Truck')
    @patch('AgentA.RTSPStream')
    def test_loop_does_not_publish_when_no_truck(self, mock_rtsp, mock_yolo_class, mock_producer):
        """Test that loop does not publish when no truck is detected."""
        from AgentA import AgentA
        
        # Setup mocks
        mock_stream = Mock()
        mock_stream.read.side_effect = [np.zeros((100, 100, 3)), None]
        mock_rtsp.return_value = mock_stream
        
        mock_yolo = Mock()
        mock_results = Mock()
        mock_yolo.detect.return_value = mock_results
        mock_yolo.truck_found.return_value = False
        mock_yolo_class.return_value = mock_yolo
        
        mock_producer_instance = Mock()
        mock_producer.return_value = mock_producer_instance
        
        agent = AgentA()
        agent.yolo = mock_yolo
        
        # Stop after a short time
        def stopper():
            time.sleep(0.1)
            agent.stop()
        
        threading.Thread(target=stopper, daemon=True).start()
        agent._loop()
        
        # Verify produce was NOT called
        mock_producer_instance.produce.assert_not_called()
    
    @patch('AgentA.Producer')
    @patch('AgentA.YOLO_Truck')
    @patch('AgentA.RTSPStream')
    def test_loop_respects_message_interval(self, mock_rtsp, mock_yolo_class, mock_producer):
        """Test that loop respects MESSAGE_INTERVAL throttling."""
        from AgentA import AgentA
        import AgentA as agentA_module
        
        # Setup mocks
        mock_stream = Mock()
        mock_stream.read.side_effect = [
            np.zeros((100, 100, 3)),
            np.zeros((100, 100, 3)),
            np.zeros((100, 100, 3)),
            None
        ]
        mock_rtsp.return_value = mock_stream
        
        mock_yolo = Mock()
        mock_results = Mock()
        mock_yolo.detect.return_value = mock_results
        mock_yolo.truck_found.return_value = True
        mock_yolo.get_boxes.return_value = [[0, 0, 100, 100, 0.95]]
        mock_yolo_class.return_value = mock_yolo
        
        mock_producer_instance = Mock()
        mock_producer.return_value = mock_producer_instance
        
        # Set high MESSAGE_INTERVAL
        original_interval = agentA_module.MESSAGE_INTERVAL
        agentA_module.MESSAGE_INTERVAL = 9999
        
        try:
            agent = AgentA()
            agent.yolo = mock_yolo
            
            def stopper():
                time.sleep(0.2)
                agent.stop()
            
            threading.Thread(target=stopper, daemon=True).start()
            agent._loop()
            
            # Should only produce once due to throttling
            assert mock_producer_instance.produce.call_count == 1
        finally:
            agentA_module.MESSAGE_INTERVAL = original_interval
    
    @patch('AgentA.Producer')
    @patch('AgentA.YOLO_Truck')
    @patch('AgentA.RTSPStream')
    def test_loop_flushes_producer_on_exit(self, mock_rtsp, mock_yolo_class, mock_producer):
        """Test that loop flushes Kafka producer on exit."""
        from AgentA import AgentA
        
        mock_stream = Mock()
        mock_stream.read.return_value = None
        mock_rtsp.return_value = mock_stream
        
        mock_producer_instance = Mock()
        mock_producer.return_value = mock_producer_instance
        
        agent = AgentA()
        
        def stopper():
            time.sleep(0.1)
            agent.stop()
        
        threading.Thread(target=stopper, daemon=True).start()
        agent._loop()
        
        mock_producer_instance.flush.assert_called_once_with(10)
    
    @patch('AgentA.Producer')
    @patch('AgentA.YOLO_Truck')
    @patch('AgentA.RTSPStream')
    def test_loop_releases_stream_on_exit(self, mock_rtsp, mock_yolo_class, mock_producer):
        """Test that loop releases RTSP stream on exit."""
        from AgentA import AgentA
        
        mock_stream = Mock()
        mock_stream.read.return_value = None
        mock_rtsp.return_value = mock_stream
        
        agent = AgentA()
        
        def stopper():
            time.sleep(0.1)
            agent.stop()
        
        threading.Thread(target=stopper, daemon=True).start()
        agent._loop()
        
        mock_stream.release.assert_called_once()


class TestAgentAYOLOIntegration:
    """Tests for YOLO model integration."""
    
    @patch('AgentA.Producer')
    @patch('AgentA.YOLO_Truck')
    def test_get_boxes_extracts_confidence(self, mock_yolo_class, mock_producer):
        """Test that get_boxes correctly extracts confidence values."""
        from AgentA import AgentA
        
        mock_yolo = Mock()
        mock_yolo.get_boxes.return_value = [
            [0, 0, 100, 100, 0.85],
            [50, 50, 150, 150, 0.92]
        ]
        mock_yolo_class.return_value = mock_yolo
        
        agent = AgentA()
        agent.yolo = mock_yolo
        
        boxes = agent.yolo.get_boxes(Mock())
        max_conf = max((b[4] for b in boxes), default=0.0)
        
        assert abs(max_conf - 0.92) < 1e-6
    
    @patch('AgentA.Producer')
    @patch('AgentA.YOLO_Truck')
    def test_handles_empty_detection_results(self, mock_yolo_class, mock_producer):
        """Test handling of empty detection results."""
        from AgentA import AgentA
        
        mock_yolo = Mock()
        mock_yolo.get_boxes.return_value = []
        mock_yolo_class.return_value = mock_yolo
        
        agent = AgentA()
        agent.yolo = mock_yolo
        
        boxes = agent.yolo.get_boxes(Mock())
        max_conf = max((b[4] for b in boxes), default=0.0)
        
        assert math.isclose(max_conf, 0.0, rel_tol=1e-09, abs_tol=1e-09)


class TestYOLOTruckUnit:
    """Unit tests for YOLO_Truck class."""
    
    @patch('YOLO_Truck.YOLO')
    def test_truck_found_returns_true_when_boxes_exist(self, mock_yolo):
        """Test truck_found returns True when boxes detected."""
        from YOLO_Truck import YOLO_Truck
        
        mock_model = Mock()
        mock_yolo.return_value = mock_model
        
        yolo = YOLO_Truck()
        
        mock_result = Mock()
        mock_result.boxes = [Mock(), Mock()]  # Two boxes
        mock_results = [mock_result]
        
        assert yolo.truck_found(mock_results) is True
    
    @patch('YOLO_Truck.YOLO')
    def test_truck_found_returns_false_when_no_boxes(self, mock_yolo):
        """Test truck_found returns False when no boxes detected."""
        from YOLO_Truck import YOLO_Truck
        
        mock_model = Mock()
        mock_yolo.return_value = mock_model
        
        yolo = YOLO_Truck()
        
        mock_result = Mock()
        mock_result.boxes = []  # No boxes
        mock_results = [mock_result]
        
        assert yolo.truck_found(mock_results) is False
    
    @patch('YOLO_Truck.YOLO')
    def test_get_boxes_extracts_coordinates_and_confidence(self, mock_yolo):
        """Test get_boxes extracts correct data from results."""
        from YOLO_Truck import YOLO_Truck
        import torch
        
        mock_model = Mock()
        mock_yolo.return_value = mock_model
        
        yolo = YOLO_Truck()
        
        # Create mock box
        mock_box = Mock()
        mock_box.xyxy = [torch.tensor([10.0, 20.0, 100.0, 200.0])]
        mock_box.conf = [torch.tensor([0.95])]
        
        mock_result = Mock()
        mock_result.boxes = [mock_box]
        mock_results = [mock_result]
        
        boxes = yolo.get_boxes(mock_results)
        
        assert len(boxes) == 1
        assert boxes[0][4] == pytest.approx(0.95)  # Confidence (use approx for float precision)
