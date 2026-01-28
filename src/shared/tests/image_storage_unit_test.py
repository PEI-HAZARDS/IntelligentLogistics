"""
Unit tests for shared/src/image_storage.py

Tests cover:
- ImageStorage initialization
- Bucket management (_ensure_bucket)
- Image upload (upload_memory_image)
- Presigned URL generation
- Error handling (S3Error, connection errors)

All MinIO client calls are mocked.
"""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock, PropertyMock
from io import BytesIO

# Mock dependencies before import
with patch("image_storage.Minio"):
    from image_storage import ImageStorage


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_minio_client():
    """Create a mock MinIO client."""
    with patch("image_storage.Minio") as MockMinio:
        mock_client = MagicMock()
        MockMinio.return_value = mock_client
        yield mock_client


@pytest.fixture
def storage_config():
    """Standard MinIO configuration for tests."""
    return {
        "endpoint": "localhost:9000",
        "access_key": "minioadmin",
        "secret_key": "minioadmin",
        "secure": False,
    }


@pytest.fixture
def sample_image():
    """Create a sample image as numpy array."""
    return np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)


# =============================================================================
# Tests for __init__
# =============================================================================

class TestImageStorageInit:
    """Tests for ImageStorage initialization."""

    def test_initialization_creates_minio_client(self, storage_config):
        """Initialization creates MinIO client with provided config."""
        # Arrange & Act
        with patch("image_storage.Minio") as MockMinio:
            storage = ImageStorage(storage_config, "test-bucket")

            # Assert
            MockMinio.assert_called_once_with(**storage_config)
            assert storage.bucket_name == "test-bucket"

    def test_stores_bucket_name(self, storage_config):
        """Bucket name is stored correctly."""
        # Arrange & Act
        with patch("image_storage.Minio"):
            storage = ImageStorage(storage_config, "my-bucket")

            # Assert
            assert storage.bucket_name == "my-bucket"


# =============================================================================
# Tests for _ensure_bucket
# =============================================================================

class TestEnsureBucket:
    """Tests for bucket creation and verification."""

    def test_bucket_exists_returns_true(self, storage_config):
        """Returns True when bucket already exists."""
        # Arrange
        with patch("image_storage.Minio") as MockMinio:
            mock_client = MagicMock()
            MockMinio.return_value = mock_client
            mock_client.bucket_exists.return_value = True
            
            storage = ImageStorage(storage_config, "existing-bucket")

            # Act
            result = storage._ensure_bucket()

            # Assert
            assert result is True
            mock_client.make_bucket.assert_not_called()

    def test_creates_bucket_if_not_exists(self, storage_config):
        """Creates bucket when it doesn't exist."""
        # Arrange
        with patch("image_storage.Minio") as MockMinio:
            mock_client = MagicMock()
            MockMinio.return_value = mock_client
            mock_client.bucket_exists.return_value = False
            
            storage = ImageStorage(storage_config, "new-bucket")

            # Act
            result = storage._ensure_bucket()

            # Assert
            assert result is True
            mock_client.make_bucket.assert_called_once_with("new-bucket")

    def test_returns_false_on_s3_error(self, storage_config):
        """Returns False when S3Error occurs."""
        # Arrange
        from minio.error import S3Error
        
        with patch("image_storage.Minio") as MockMinio:
            mock_client = MagicMock()
            MockMinio.return_value = mock_client
            mock_client.bucket_exists.side_effect = S3Error(
                "TestError", "test", "test", "test", "test", "test"
            )
            
            storage = ImageStorage(storage_config, "error-bucket")

            # Act
            result = storage._ensure_bucket()

            # Assert
            assert result is False


# =============================================================================
# Tests for upload_memory_image
# =============================================================================

class TestUploadMemoryImage:
    """Tests for uploading images from memory."""

    @patch("image_storage.cv2")
    def test_successful_upload(self, mock_cv2, storage_config, sample_image):
        """Successfully upload image and return presigned URL."""
        # Arrange
        with patch("image_storage.Minio") as MockMinio:
            mock_client = MagicMock()
            MockMinio.return_value = mock_client
            mock_client.bucket_exists.return_value = True
            mock_client.get_presigned_url.return_value = "http://example.com/image.jpg"
            
            # Mock cv2.imencode to return success
            mock_cv2.imencode.return_value = (True, np.array([1, 2, 3], dtype=np.uint8))
            
            storage = ImageStorage(storage_config, "test-bucket")

            # Act
            result = storage.upload_memory_image(sample_image, "test.jpg")

            # Assert
            assert result == "http://example.com/image.jpg"
            mock_client.put_object.assert_called_once()

    @patch("image_storage.cv2")
    def test_upload_with_none_image_returns_none(self, mock_cv2, storage_config):
        """Uploading None image returns None."""
        # Arrange
        with patch("image_storage.Minio") as MockMinio:
            mock_client = MagicMock()
            MockMinio.return_value = mock_client
            mock_client.bucket_exists.return_value = True
            
            storage = ImageStorage(storage_config, "test-bucket")

            # Act
            result = storage.upload_memory_image(None, "test.jpg")

            # Assert
            assert result is None
            mock_client.put_object.assert_not_called()

    @patch("image_storage.cv2")
    def test_upload_with_empty_image_returns_none(self, mock_cv2, storage_config):
        """Uploading empty image array returns None."""
        # Arrange
        with patch("image_storage.Minio") as MockMinio:
            mock_client = MagicMock()
            MockMinio.return_value = mock_client
            mock_client.bucket_exists.return_value = True
            
            storage = ImageStorage(storage_config, "test-bucket")
            empty_image = np.array([], dtype=np.uint8)

            # Act
            result = storage.upload_memory_image(empty_image, "test.jpg")

            # Assert
            assert result is None

    @patch("image_storage.cv2")
    def test_upload_fails_when_bucket_unavailable(self, mock_cv2, storage_config, sample_image):
        """Returns None when bucket is unavailable."""
        # Arrange
        from minio.error import S3Error
        
        with patch("image_storage.Minio") as MockMinio:
            mock_client = MagicMock()
            MockMinio.return_value = mock_client
            mock_client.bucket_exists.side_effect = S3Error(
                "TestError", "test", "test", "test", "test", "test"
            )
            
            storage = ImageStorage(storage_config, "test-bucket")

            # Act
            result = storage.upload_memory_image(sample_image, "test.jpg")

            # Assert
            assert result is None

    @patch("image_storage.cv2")
    def test_upload_fails_when_encoding_fails(self, mock_cv2, storage_config, sample_image):
        """Returns None when image encoding fails."""
        # Arrange
        with patch("image_storage.Minio") as MockMinio:
            mock_client = MagicMock()
            MockMinio.return_value = mock_client
            mock_client.bucket_exists.return_value = True
            
            # Mock encoding failure
            mock_cv2.imencode.return_value = (False, None)
            
            storage = ImageStorage(storage_config, "test-bucket")

            # Act
            result = storage.upload_memory_image(sample_image, "test.jpg")

            # Assert
            assert result is None
            mock_client.put_object.assert_not_called()

    @patch("image_storage.cv2")
    def test_upload_handles_s3_error(self, mock_cv2, storage_config, sample_image):
        """Handles S3Error during upload."""
        # Arrange
        from minio.error import S3Error
        
        with patch("image_storage.Minio") as MockMinio:
            mock_client = MagicMock()
            MockMinio.return_value = mock_client
            mock_client.bucket_exists.return_value = True
            mock_client.put_object.side_effect = S3Error(
                "UploadError", "test", "test", "test", "test", "test"
            )
            
            mock_cv2.imencode.return_value = (True, np.array([1, 2, 3], dtype=np.uint8))
            
            storage = ImageStorage(storage_config, "test-bucket")

            # Act
            result = storage.upload_memory_image(sample_image, "test.jpg")

            # Assert
            assert result is None

    @patch("image_storage.cv2")
    def test_upload_handles_connection_refused(self, mock_cv2, storage_config, sample_image):
        """Handles ConnectionRefusedError gracefully."""
        # Arrange
        with patch("image_storage.Minio") as MockMinio:
            mock_client = MagicMock()
            MockMinio.return_value = mock_client
            mock_client.bucket_exists.return_value = True
            mock_client.put_object.side_effect = ConnectionRefusedError("Connection refused")
            
            mock_cv2.imencode.return_value = (True, np.array([1, 2, 3], dtype=np.uint8))
            
            storage = ImageStorage(storage_config, "test-bucket")

            # Act
            result = storage.upload_memory_image(sample_image, "test.jpg")

            # Assert
            assert result is None

    @patch("image_storage.cv2")
    def test_upload_handles_os_error(self, mock_cv2, storage_config, sample_image):
        """Handles OSError gracefully."""
        # Arrange
        with patch("image_storage.Minio") as MockMinio:
            mock_client = MagicMock()
            MockMinio.return_value = mock_client
            mock_client.bucket_exists.return_value = True
            mock_client.put_object.side_effect = OSError("Network error")
            
            mock_cv2.imencode.return_value = (True, np.array([1, 2, 3], dtype=np.uint8))
            
            storage = ImageStorage(storage_config, "test-bucket")

            # Act
            result = storage.upload_memory_image(sample_image, "test.jpg")

            # Assert
            assert result is None

    @patch("image_storage.cv2")
    def test_upload_handles_max_retry_error(self, mock_cv2, storage_config, sample_image):
        """Handles MaxRetryError by name checking."""
        # Arrange
        with patch("image_storage.Minio") as MockMinio:
            mock_client = MagicMock()
            MockMinio.return_value = mock_client
            mock_client.bucket_exists.return_value = True
            
            # Create exception with __class__.__name__ = "MaxRetryError"
            class MaxRetryError(Exception):
                pass
            
            mock_client.put_object.side_effect = MaxRetryError("Max retries exceeded")
            mock_cv2.imencode.return_value = (True, np.array([1, 2, 3], dtype=np.uint8))
            
            storage = ImageStorage(storage_config, "test-bucket")

            # Act
            result = storage.upload_memory_image(sample_image, "test.jpg")

            # Assert
            assert result is None


# =============================================================================
# Tests for _generate_presigned_url
# =============================================================================

class TestGeneratePresignedUrl:
    """Tests for presigned URL generation."""

    def test_generates_presigned_url(self, storage_config):
        """Generates presigned URL with default expiry."""
        # Arrange
        with patch("image_storage.Minio") as MockMinio:
            mock_client = MagicMock()
            MockMinio.return_value = mock_client
            mock_client.get_presigned_url.return_value = "http://presigned-url.com/img.jpg"
            
            storage = ImageStorage(storage_config, "test-bucket")

            # Act
            result = storage._generate_presigned_url("test.jpg")

            # Assert
            assert result == "http://presigned-url.com/img.jpg"
            mock_client.get_presigned_url.assert_called_once()

    def test_uses_custom_expiry_days(self, storage_config):
        """Uses custom expiry days parameter."""
        # Arrange
        from datetime import timedelta
        
        with patch("image_storage.Minio") as MockMinio:
            mock_client = MagicMock()
            MockMinio.return_value = mock_client
            mock_client.get_presigned_url.return_value = "http://url.com/img.jpg"
            
            storage = ImageStorage(storage_config, "test-bucket")

            # Act
            result = storage._generate_presigned_url("test.jpg", expires_days=30)

            # Assert
            call_kwargs = mock_client.get_presigned_url.call_args[1]
            assert call_kwargs["expires"] == timedelta(days=30)
