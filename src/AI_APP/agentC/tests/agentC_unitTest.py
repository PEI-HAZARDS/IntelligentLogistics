"""
Unit tests for AgentC class.
Tests hazard plate specific logic: parsing UN/Kemler codes and payload building.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock
import pytest

# Setup paths
TESTS_DIR = Path(__file__).resolve().parent
AGENT_C_ROOT = TESTS_DIR.parent
SRC_DIR = AGENT_C_ROOT / "src"
GLOBAL_SRC = AGENT_C_ROOT.parent  # /src directory

# Add paths to sys.path
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(GLOBAL_SRC))

# Mock prometheus before imports
mock_prometheus = MagicMock()
sys.modules["prometheus_client"] = mock_prometheus

from agentC import AgentC

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
def agent_c(mock_dependencies):
    agent = AgentC(**mock_dependencies)
    agent.running = False
    return agent

# =============================================================================
# Tests
# =============================================================================

class TestAgentCConfig:
    """Tests for AgentC configuration methods."""

    def test_get_agent_name(self, agent_c):
        assert agent_c.get_agent_name() == "AgentC"

    def test_get_bbox_color(self, agent_c):
        assert agent_c.get_bbox_color() == "orange"

    def test_get_object_type(self, agent_c):
        assert agent_c.get_object_type() == "hazard plate"

class TestIsValidDetection:
    """Tests for is_valid_detection method."""

    def test_accepts_any_detection(self, agent_c):
        """Always returns True for hazard plates."""
        # AgentC doesn't filter by classification in is_valid_detection currently
        is_valid = agent_c.is_valid_detection(MagicMock(), 0.9, 0)
        assert is_valid is True

class TestParseDetectionResult:
    """Tests for _parse_detection_result method."""

    def test_parses_un_and_kemler(self, agent_c):
        """Parses standard 'KEMLER UN' format."""
        text = "33 1203"
        result = agent_c._parse_detection_result(text)
        
        assert result["kemler"] == "33"
        assert result["un"] == "1203"
        assert result["text"] == text

    def test_handles_missing_parts(self, agent_c):
        """Handles text that doesn't split into two parts."""
        text = "1203" # Only one part
        result = agent_c._parse_detection_result(text)
        
        assert result["kemler"] == "N/A"
        assert result["un"] == "N/A"
        assert result["text"] == text

    def test_handles_extra_parts(self, agent_c):
        """Handles text with too many parts."""
        text = "33 1203 EXTRA"
        result = agent_c._parse_detection_result(text)
        
        # Current logic expects exactly 2 parts
        assert result["kemler"] == "N/A"
        assert result["un"] == "N/A"

class TestBuildPublishPayload:
    """Tests for build_publish_payload method."""

    def test_builds_correct_payload(self, agent_c):
        """Constructs payload with UN and Kemler codes."""
        result = {"un": "1203", "kemler": "33"}
        payload = agent_c.build_publish_payload(
            truck_id="TRK1",
            detection_result=result,
            confidence=0.85,
            crop_url="http://crop"
        )
        
        assert payload["un"] == "1203"
        assert payload["kemler"] == "33"
        assert payload["confidence"] == 0.85
