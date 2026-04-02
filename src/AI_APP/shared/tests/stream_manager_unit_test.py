"""
Unit tests for shared/src/stream_manager.py

Tests cover:
- StreamManager initialization
- Connection with retry logic
- Reconnection handling
- Frame reading
- Resource cleanup

All cv2.VideoCapture calls are mocked.
"""

import queue
import pytest
import numpy as np
from unittest.mock import patch, MagicMock, PropertyMock
import threading


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_frame():
    """Create a sample video frame."""
    return np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)


@pytest.fixture
def mock_video_capture():
    """Create a mock VideoCapture that succeeds immediately."""
    with patch("AI_APP.shared.src.stream_manager.cv2") as mock_cv2:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cv2.CAP_FFMPEG = 1900
        mock_cv2.CAP_PROP_BUFFERSIZE = 38
        yield mock_cv2, mock_cap


# =============================================================================
# Tests for __init__
# =============================================================================

class TestStreamManagerInit:
    """Tests for StreamManager initialization."""

    def test_initialization_stores_url(self):
        """Initialization stores the stream URL."""
        # Arrange & Act
        with patch("AI_APP.shared.src.stream_manager.cv2") as mock_cv2:
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
            mock_cv2.VideoCapture.return_value = mock_cap
            mock_cv2.CAP_FFMPEG = 1900
            mock_cv2.CAP_PROP_BUFFERSIZE = 38
            
            from AI_APP.shared.src.stream_manager import StreamManager
            manager = StreamManager("rtmp://test-stream")
            
            # Assert
            assert manager.url == "rtmp://test-stream"

    def test_initialization_sets_defaults(self):
        """Initialization sets default values."""
        # Arrange & Act
        with patch("AI_APP.shared.src.stream_manager.cv2") as mock_cv2:
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
            mock_cv2.VideoCapture.return_value = mock_cap
            mock_cv2.CAP_FFMPEG = 1900
            mock_cv2.CAP_PROP_BUFFERSIZE = 38
            
            from AI_APP.shared.src.stream_manager import StreamManager
            manager = StreamManager("rtmp://test", max_retries=5, retry_delay=2)

            # Assert
            assert manager.max_retries == 5
            assert manager.retry_delay == 2
            assert manager.running is False

    def test_connect_starts_update_thread(self):
        """Connect method starts the update thread."""
        # Arrange & Act
        with patch("AI_APP.shared.src.stream_manager.cv2") as mock_cv2:
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
            mock_cv2.VideoCapture.return_value = mock_cap
            mock_cv2.CAP_FFMPEG = 1900
            mock_cv2.CAP_PROP_BUFFERSIZE = 38
            
            from AI_APP.shared.src.stream_manager import StreamManager
            manager = StreamManager("rtmp://test")
            manager.connect()
            
            import time
            time.sleep(0.2)

            # Assert
            assert manager.thread.is_alive()

            # Cleanup
            manager.running = False
            manager.thread.join(timeout=1.0)


# =============================================================================
# Tests for _connect_with_retry
# =============================================================================

class TestConnectWithRetry:
    """Tests for connection retry logic."""

    def test_returns_cap_on_first_success(self):
        """Returns capture object on first successful connection."""
        # Arrange
        with patch("AI_APP.shared.src.stream_manager.cv2") as mock_cv2:
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cv2.VideoCapture.return_value = mock_cap
            mock_cv2.CAP_FFMPEG = 1900
            mock_cv2.CAP_PROP_BUFFERSIZE = 38
            
            from AI_APP.shared.src.stream_manager import StreamManager
            
            # Create without starting thread
            with patch.object(StreamManager, '__init__', lambda self, *args, **kwargs: None):
                manager = StreamManager.__new__(StreamManager)
                manager.url = "rtmp://test"
                manager.max_retries = 3
                manager.retry_delay = 0.1
                manager.running = True

                # Act
                result = manager._connect_with_retry()

                # Assert
                assert result is mock_cap
                mock_cv2.VideoCapture.assert_called_once()

    def test_retries_on_failure(self):
        """Retries connection on failure."""
        # Arrange
        with patch("AI_APP.shared.src.stream_manager.cv2") as mock_cv2:
            with patch("AI_APP.shared.src.stream_manager.time") as mock_time:
                mock_cap_fail = MagicMock()
                mock_cap_fail.isOpened.return_value = False
                mock_cap_success = MagicMock()
                mock_cap_success.isOpened.return_value = True
                
                # First two fail, third succeeds
                mock_cv2.VideoCapture.side_effect = [mock_cap_fail, mock_cap_fail, mock_cap_success]
                mock_cv2.CAP_FFMPEG = 1900
                mock_cv2.CAP_PROP_BUFFERSIZE = 38
                
                from AI_APP.shared.src.stream_manager import StreamManager
                
                with patch.object(StreamManager, '__init__', lambda self, *args, **kwargs: None):
                    manager = StreamManager.__new__(StreamManager)
                    manager.url = "rtmp://test"
                    manager.max_retries = 5
                    manager.retry_delay = 0.1
                    manager.running = True

                    # Act
                    result = manager._connect_with_retry()

                    # Assert
                    assert result is mock_cap_success
                    assert mock_cv2.VideoCapture.call_count == 3

    def test_returns_none_after_max_retries(self):
        """Returns None after max retries exhausted."""
        # Arrange
        with patch("AI_APP.shared.src.stream_manager.cv2") as mock_cv2:
            with patch("AI_APP.shared.src.stream_manager.time") as mock_time:
                mock_cap = MagicMock()
                mock_cap.isOpened.return_value = False
                mock_cv2.VideoCapture.return_value = mock_cap
                mock_cv2.CAP_FFMPEG = 1900
                mock_cv2.CAP_PROP_BUFFERSIZE = 38
                
                from AI_APP.shared.src.stream_manager import StreamManager
                
                with patch.object(StreamManager, '__init__', lambda self, *args, **kwargs: None):
                    manager = StreamManager.__new__(StreamManager)
                    manager.url = "rtmp://test"
                    manager.max_retries = 2
                    manager.retry_delay = 0.01
                    manager.running = True

                    # Act
                    result = manager._connect_with_retry()

                    # Assert
                    assert result is None
                    assert mock_cv2.VideoCapture.call_count == 2

    def test_stops_on_running_false(self):
        """Stops retry loop when running is False."""
        # Arrange
        with patch("AI_APP.shared.src.stream_manager.cv2") as mock_cv2:
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = False
            mock_cv2.VideoCapture.return_value = mock_cap
            mock_cv2.CAP_FFMPEG = 1900
            mock_cv2.CAP_PROP_BUFFERSIZE = 38
            
            from AI_APP.shared.src.stream_manager import StreamManager
            
            with patch.object(StreamManager, '__init__', lambda self, *args, **kwargs: None):
                manager = StreamManager.__new__(StreamManager)
                manager.url = "rtmp://test"
                manager.max_retries = 10
                manager.retry_delay = 0.01
                manager.running = False  # Already stopped

                # Act
                result = manager._connect_with_retry()

                # Assert
                assert result is None


# =============================================================================
# Tests for _reconnect
# =============================================================================

class TestReconnect:
    """Tests for reconnection handling."""

    def test_releases_old_capture(self):
        """Releases old capture before reconnecting."""
        # Arrange
        with patch("AI_APP.shared.src.stream_manager.cv2") as mock_cv2:
            old_cap = MagicMock()
            new_cap = MagicMock()
            new_cap.isOpened.return_value = True
            mock_cv2.VideoCapture.return_value = new_cap
            mock_cv2.CAP_FFMPEG = 1900
            mock_cv2.CAP_PROP_BUFFERSIZE = 38
            
            from AI_APP.shared.src.stream_manager import StreamManager
            
            with patch.object(StreamManager, '__init__', lambda self, *args, **kwargs: None):
                manager = StreamManager.__new__(StreamManager)
                manager.url = "rtmp://test"
                manager.max_retries = 1
                manager.retry_delay = 0.01
                manager.running = True
                manager.cap = old_cap
                manager.frame_queue = queue.Queue(maxsize=1)

                # Act
                manager._reconnect()

                # Assert
                old_cap.release.assert_called_once()

    def test_clears_current_frame(self):
        """Clears current frame during reconnection."""
        # Arrange
        with patch("AI_APP.shared.src.stream_manager.cv2") as mock_cv2:
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cv2.VideoCapture.return_value = mock_cap
            mock_cv2.CAP_FFMPEG = 1900
            mock_cv2.CAP_PROP_BUFFERSIZE = 38
            
            from AI_APP.shared.src.stream_manager import StreamManager
            
            with patch.object(StreamManager, '__init__', lambda self, *args, **kwargs: None):
                manager = StreamManager.__new__(StreamManager)
                manager.url = "rtmp://test"
                manager.max_retries = 1
                manager.retry_delay = 0.01
                manager.running = True
                manager.cap = MagicMock()
                manager.frame_queue = queue.Queue(maxsize=1)
                manager.frame_queue.put(np.zeros((480, 640, 3), dtype=np.uint8))

                # Act
                manager._reconnect()

                # Assert
                assert manager.frame_queue.empty()


# =============================================================================
# Tests for read
# =============================================================================

class TestRead:
    """Tests for frame reading."""

    def test_returns_frame_copy_when_available(self, sample_frame):
        """Returns a copy of the current frame."""
        # Arrange
        with patch("AI_APP.shared.src.stream_manager.cv2"):
            from AI_APP.shared.src.stream_manager import StreamManager
            
            with patch.object(StreamManager, '__init__', lambda self, *args, **kwargs: None):
                manager = StreamManager.__new__(StreamManager)
                manager.frame_queue = queue.Queue(maxsize=1)
                manager.frame_queue.put(sample_frame)

                # Act
                result = manager.read(timeout=1.0)

                # Assert
                assert result is not None
                assert np.array_equal(result, sample_frame)

    def test_returns_none_when_no_frame(self):
        """Returns None when no frame available."""
        # Arrange
        with patch("AI_APP.shared.src.stream_manager.cv2"):
            from AI_APP.shared.src.stream_manager import StreamManager
            
            with patch.object(StreamManager, '__init__', lambda self, *args, **kwargs: None):
                manager = StreamManager.__new__(StreamManager)
                manager.frame_queue = queue.Queue(maxsize=1)

                # Act
                result = manager.read(timeout=0.01)

                # Assert
                assert result is None


# =============================================================================
# Tests for release
# =============================================================================

class TestRelease:
    """Tests for resource cleanup."""

    def test_sets_running_false(self):
        """Sets running to False."""
        # Arrange
        with patch("AI_APP.shared.src.stream_manager.cv2"):
            from AI_APP.shared.src.stream_manager import StreamManager
            
            with patch.object(StreamManager, '__init__', lambda self, *args, **kwargs: None):
                manager = StreamManager.__new__(StreamManager)
                manager.url = "rtmp://test"
                manager.running = True
                manager.thread = MagicMock()
                manager.thread.join = MagicMock()
                manager.cap = MagicMock()
                manager.frame_queue = queue.Queue(maxsize=1)

                # Act
                manager.release()

                # Assert
                assert manager.running is False

    def test_joins_thread(self):
        """Waits for thread to complete."""
        # Arrange
        with patch("AI_APP.shared.src.stream_manager.cv2"):
            from AI_APP.shared.src.stream_manager import StreamManager

            with patch.object(StreamManager, '__init__', lambda self, *args, **kwargs: None):
                manager = StreamManager.__new__(StreamManager)
                manager.url = "rtmp://test"
                mock_thread = MagicMock()
                manager.thread = mock_thread
                manager.cap = MagicMock()
                manager.frame_queue = queue.Queue(maxsize=1)

                # Act
                manager.release()

                # Assert
                mock_thread.join.assert_called_once_with(timeout=1.0)

    def test_releases_capture(self):
        """Releases the video capture."""
        # Arrange
        with patch("AI_APP.shared.src.stream_manager.cv2"):
            from AI_APP.shared.src.stream_manager import StreamManager

            with patch.object(StreamManager, '__init__', lambda self, *args, **kwargs: None):
                manager = StreamManager.__new__(StreamManager)
                manager.url = "rtmp://test"
                manager.thread = MagicMock()
                mock_cap = MagicMock()
                manager.cap = mock_cap
                manager.frame_queue = queue.Queue(maxsize=1)

                # Act
                manager.release()

                # Assert
                mock_cap.release.assert_called_once()


# =============================================================================
# Tests for internal methods
# =============================================================================

class TestInternalMethods:
    """Tests for internal helper methods."""

    def test_ensure_connection_active_returns_true_when_connected(self):
        """_ensure_connection_active returns True when connected."""
        # Arrange
        with patch("AI_APP.shared.src.stream_manager.cv2"):
            from AI_APP.shared.src.stream_manager import StreamManager
            
            with patch.object(StreamManager, '__init__', lambda self, *args, **kwargs: None):
                manager = StreamManager.__new__(StreamManager)
                manager.cap = MagicMock()
                manager.cap.isOpened.return_value = True

                # Act
                result = manager._ensure_connection_active()

                # Assert
                assert result is True

    def test_ensure_connection_active_reconnects_when_disconnected(self):
        """_ensure_connection_active reconnects when disconnected."""
        # Arrange
        with patch("AI_APP.shared.src.stream_manager.cv2") as mock_cv2:
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cv2.VideoCapture.return_value = mock_cap
            mock_cv2.CAP_FFMPEG = 1900
            mock_cv2.CAP_PROP_BUFFERSIZE = 38
            
            from AI_APP.shared.src.stream_manager import StreamManager
            
            with patch.object(StreamManager, '__init__', lambda self, *args, **kwargs: None):
                manager = StreamManager.__new__(StreamManager)
                manager.url = "rtmp://test"
                manager.max_retries = 1
                manager.retry_delay = 0.01
                manager.running = True
                manager.cap = None  # Disconnected
                manager.frame_queue = queue.Queue(maxsize=1)

                # Act
                result = manager._ensure_connection_active()

                # Assert
                assert result is True
                assert manager.cap is mock_cap

    def test_handle_read_success_updates_frame(self, sample_frame):
        """_handle_read_success updates the frame."""
        # Arrange
        with patch("AI_APP.shared.src.stream_manager.cv2"):
            from AI_APP.shared.src.stream_manager import StreamManager
            
            with patch.object(StreamManager, '__init__', lambda self, *args, **kwargs: None):
                manager = StreamManager.__new__(StreamManager)
                manager.frame_queue = queue.Queue(maxsize=1)

                # Act
                manager._handle_read_success(sample_frame)

                # Assert
                result = manager.frame_queue.get_nowait()
                assert np.array_equal(result, sample_frame)

    def test_handle_read_failure_increments_count(self):
        """_handle_read_failure increments failure count."""
        # Arrange
        with patch("AI_APP.shared.src.stream_manager.cv2"):
            with patch("AI_APP.shared.src.stream_manager.time"):
                from AI_APP.shared.src.stream_manager import StreamManager
                
                with patch.object(StreamManager, '__init__', lambda self, *args, **kwargs: None):
                    manager = StreamManager.__new__(StreamManager)

                    # Act
                    result = manager._handle_read_failure(3, 10)

                    # Assert
                    assert result == 4

    def test_handle_read_failure_triggers_reconnect_at_max(self):
        """_handle_read_failure triggers reconnect at max failures."""
        # Arrange
        with patch("AI_APP.shared.src.stream_manager.cv2") as mock_cv2:
            with patch("AI_APP.shared.src.stream_manager.time"):
                mock_cap = MagicMock()
                mock_cap.isOpened.return_value = True
                mock_cv2.VideoCapture.return_value = mock_cap
                mock_cv2.CAP_FFMPEG = 1900
                mock_cv2.CAP_PROP_BUFFERSIZE = 38
                
                from AI_APP.shared.src.stream_manager import StreamManager
                
                with patch.object(StreamManager, '__init__', lambda self, *args, **kwargs: None):
                    manager = StreamManager.__new__(StreamManager)
                    manager.url = "rtmp://test"
                    manager.max_retries = 1
                    manager.retry_delay = 0.01
                    manager.running = True
                    manager.cap = MagicMock()
                    manager.frame_queue = queue.Queue(maxsize=1)

                    # Act - at max failures
                    result = manager._handle_read_failure(9, 10)

                    # Assert - counter reset after reconnect
                    assert result == 0
