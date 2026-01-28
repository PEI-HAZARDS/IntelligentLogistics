"""
Pytest configuration and fixtures for decision_engine tests.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Mock prometheus_client before any imports
prometheus_mock = MagicMock()
prometheus_mock.Counter = MagicMock(return_value=MagicMock())
prometheus_mock.Histogram = MagicMock(return_value=MagicMock())
prometheus_mock.Gauge = MagicMock(return_value=MagicMock())
prometheus_mock.start_http_server = MagicMock()
sys.modules['prometheus_client'] = prometheus_mock

# Setup paths - DECISION ENGINE STRUCTURE
# /src/decision_engine/tests/conftest.py <- This file
# /src/decision_engine/src/decision_engine.py <- Module to test
TESTS_DIR = Path(__file__).resolve().parent
DECISION_ENGINE_ROOT = TESTS_DIR.parent
DECISION_ENGINE_SRC = DECISION_ENGINE_ROOT / "src"
GLOBAL_SRC = DECISION_ENGINE_ROOT.parent  # /src directory

# Add paths to sys.path - order matters!
sys.path.insert(0, str(DECISION_ENGINE_SRC))  # decision_engine/src
sys.path.insert(0, str(GLOBAL_SRC))  # /src for shared module access

import pytest
import numpy as np

