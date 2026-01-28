"""
Pytest configuration and shared fixtures for shared module tests.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Mock prometheus_client before any imports that might use it
prometheus_mock = MagicMock()
prometheus_mock.Counter = MagicMock(return_value=MagicMock())
prometheus_mock.Histogram = MagicMock(return_value=MagicMock())
prometheus_mock.Gauge = MagicMock(return_value=MagicMock())
sys.modules['prometheus_client'] = prometheus_mock

# Setup paths for imports
TESTS_DIR = Path(__file__).resolve().parent
SHARED_ROOT = TESTS_DIR.parent
SRC_DIR = SHARED_ROOT / "src"
GLOBAL_SRC = SHARED_ROOT.parent  # /src directory

# Add paths to sys.path for imports
sys.path.insert(0, str(SRC_DIR))  # shared/src
sys.path.insert(0, str(SHARED_ROOT))  # shared
sys.path.insert(0, str(GLOBAL_SRC))  # src

import pytest
import numpy as np



@pytest.fixture
def sample_image():
    """Create a sample image as numpy array (BGR format)."""
    return np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)


@pytest.fixture
def sample_frame():
    """Create a sample video frame (480p resolution)."""
    return np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)


@pytest.fixture
def sample_crop():
    """Create a sample cropped plate image."""
    return np.random.randint(0, 255, (50, 150, 3), dtype=np.uint8)


@pytest.fixture
def mock_kafka_message():
    """Create a mock Kafka message."""
    msg = MagicMock()
    msg.error.return_value = None
    msg.topic.return_value = "test-topic"
    msg.value.return_value = b'{"key": "value"}'
    msg.headers.return_value = [("truckId", b"TRUCK-123")]
    return msg
