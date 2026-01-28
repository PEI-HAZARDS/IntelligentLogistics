"""
Unit tests for AgentB class.
Tests license plate specific logic: validation, payload building, and metrics.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

# Setup paths
TESTS_DIR = Path(__file__).resolve().parent
AGENT_B_ROOT = TESTS_DIR.parent
SRC_DIR = AGENT_B_ROOT / "src"
GLOBAL_SRC = AGENT_B_ROOT.parent  # /src directory

# Add paths to sys.path
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(GLOBAL_SRC))

# Mock prometheus before imports
mock_prometheus = MagicMock()
sys.modules["prometheus_client"] = mock_prometheus

from agentB import AgentB
from shared.src.plate_classifier import PlateClassifier

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_dependencies():
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
def agent_b(mock_dependencies):
    with patch("agentB.ImageStorage"): # Mock internal ImageStorage creation
        agent = AgentB(**mock_dependencies)
        agent.running = False
        return agent

# =============================================================================
# Tests
# =============================================================================

class TestAgentBConfig:
    """Tests for AgentB configuration methods."""

    def test_get_agent_name(self, agent_b):
        assert agent_b.get_agent_name() == "AgentB"

    def test_get_bbox_color(self, agent_b):
        assert agent_b.get_bbox_color() == "blue"

    def test_get_object_type(self, agent_b):
        assert agent_b.get_object_type() == "license plate"

class TestIsValidDetection:
    """Tests for is_valid_detection method."""

    def test_rejects_hazard_plate(self, agent_b):
        """Rejects crop classified as hazard plate."""
        crop = MagicMock()
        agent_b.classifier.classify.return_value = PlateClassifier.HAZARD_PLATE
        
        is_valid = agent_b.is_valid_detection(crop, 0.9, 0)
        
        assert is_valid is False
        agent_b.classifier.classify.assert_called_with(crop)

    def test_accepts_license_plate(self, agent_b):
        """Accepts crop classified as license plate."""
        crop = MagicMock()
        agent_b.classifier.classify.return_value = "LICENSE_PLATE"
        
        is_valid = agent_b.is_valid_detection(crop, 0.9, 0)
        
        assert is_valid is True
        agent_b.classifier.classify.assert_called_with(crop)

class TestBuildPublishPayload:
    """Tests for build_publish_payload method."""

    def test_builds_correct_payload(self, agent_b):
        """Constructs payload with license plate text."""
        result = {"text": "AB-12-CD"}
        payload = agent_b.build_publish_payload(
            truck_id="TRK1",
            detection_result=result,
            confidence=0.99,
            crop_url="http://crop"
        )
        
        assert payload["licensePlate"] == "AB-12-CD"
        assert payload["confidence"] == 0.99
        assert payload["cropUrl"] == "http://crop"
        
    def test_handles_none_confidence(self, agent_b):
        """Handles None detection confidence."""
        result = {"text": "AB-12-CD"}
        payload = agent_b.build_publish_payload(
            truck_id="TRK1",
            detection_result=result,
            confidence=None,
            crop_url=None
        )
        
        assert payload["confidence"] == 0.0

class TestParseDetectionResult:
    """Tests for _parse_detection_result method."""
    
    def test_returns_text_dict(self, agent_b):
        """Simply wraps text in dictionary."""
        res = agent_b._parse_detection_result("HELLO")
        assert res == {"text": "HELLO"}
