#!/usr/bin/env python3
"""
pytest configuration file for Data Module tests
"""

import pytest
import os
import sys
from pathlib import Path

# Adicionar src ao path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

@pytest.fixture(scope="session")
def test_config():
    """Configuração de testes"""
    return {
        "base_url": os.getenv("TEST_BASE_URL", "http://localhost:8080/api/v1"),
        "timeout": 30,
        "database_url": os.getenv("DATABASE_URL", "postgresql://porto:porto_password@localhost:5432/porto_logistica"),
        "mongo_url": os.getenv("MONGO_URL", "mongodb://admin:admin123@localhost:27017"),
        "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379"),
    }

@pytest.fixture(scope="session")
def anyio_backend():
    """Configure anyio backend for async tests"""
    return "asyncio"

def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "unit: mark test as unit test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow"
    )

def pytest_collection_modifyitems(config, items):
    """Modify test items during collection"""
    for item in items:
        # Adicionar marker de integração a todos os testes
        if "test_integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
