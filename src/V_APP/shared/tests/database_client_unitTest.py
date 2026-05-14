"""
Unit tests for DatabaseClient class.
Tests for API communication with the data module.
"""
import pytest
from unittest.mock import patch, MagicMock

from V_APP.shared.src.database_client import DatabaseClient


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def db_client():
    """Create a DatabaseClient instance."""
    return DatabaseClient(api_url="http://localhost:8000", gate_id="1")


# =============================================================================
# Tests for __init__
# =============================================================================

class TestDatabaseClientInit:
    """Tests for DatabaseClient initialization."""

    def test_init_sets_api_url(self):
        """Initialization sets API URL correctly."""
        client = DatabaseClient(api_url="http://test:8000", gate_id="1")
        assert client.api_url == "http://test:8000"

    def test_init_sets_gate_id(self):
        """Initialization sets gate ID correctly."""
        client = DatabaseClient(api_url="http://test:8000", gate_id="5")
        assert client.gate_id == "5"


# =============================================================================
# Tests for get_appointments
# =============================================================================

class TestGetAppointments:
    """Tests for get_appointments method."""

    @patch("V_APP.shared.src.database_client.requests.post")
    def test_get_appointments_success(self, mock_post, db_client):
        """Successfully retrieves appointments from API."""
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "found": True,
            "candidates": [{"id": 1, "plate": "AB-12-CD"}]
        }
        mock_post.return_value = mock_response

        # Act
        result = db_client.get_appointments()

        # Assert
        assert result["found"] is True
        assert len(result["candidates"]) == 1
        mock_post.assert_called_once()

    @patch("V_APP.shared.src.database_client.requests.post")
    def test_get_appointments_api_error(self, mock_post, db_client):
        """Handles API error response."""
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        # Act
        result = db_client.get_appointments()

        # Assert
        assert result["found"] is False
        assert result["candidates"] == []
        assert result["message"] == "API Error"

    @patch("V_APP.shared.src.database_client.requests.post")
    def test_get_appointments_connection_error(self, mock_post, db_client):
        """Handles connection error."""
        # Arrange
        mock_post.side_effect = Exception("Connection refused")

        # Act
        result = db_client.get_appointments()

        # Assert
        assert result["found"] is False
        assert result["candidates"] == []
        assert "Connection refused" in result["message"]


# =============================================================================
# Tests for is_api_unavailable
# =============================================================================

class TestIsApiUnavailable:
    """Tests for is_api_unavailable method."""

    def test_connection_refused(self, db_client):
        """'Connection refused' indicates unavailable."""
        result = db_client.is_api_unavailable("Connection refused")
        assert result is True

    def test_max_retries(self, db_client):
        """'Max retries' indicates unavailable."""
        result = db_client.is_api_unavailable("Max retries exceeded")
        assert result is True

    def test_other_error_not_unavailable(self, db_client):
        """Other errors don't indicate API unavailable."""
        result = db_client.is_api_unavailable("Some other error")
        assert result is False

    def test_empty_message(self, db_client):
        """Empty message returns False."""
        result = db_client.is_api_unavailable("")
        assert result is False
