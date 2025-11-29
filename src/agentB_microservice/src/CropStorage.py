from typing import Optional
from minio import Minio
from minio.error import S3Error
from datetime import timedelta
import logging
import cv2
import io

# --- Configuration ---
MINIO_CONF = {
    "endpoint": "10.255.32.132:9000",
    "access_key": "admin",
    "secret_key": "adminadmin",
    "secure": False  # Set to True if using HTTPS
}

BUCKET_NAME = "hz-crops"
FILE_PATH = "test.jpg"           # The file on your computer
OBJECT_NAME = "test.jpg"    # The name it will have in MinIO

logger = logging.getLogger("CropStorage")

class CropStorage:
    """
    Handles interactions with MinIO Object Storage.
    Uploads images directly from memory without writing to disk.
    """
    def __init__(self, configs, bucket_name):
        logger.info(f"[AgentB/MinIO] Connecting to MinIO...")
        
        self.client = Minio(**configs)
        self.bucket_name = bucket_name
        self._ensure_bucket()

    def _ensure_bucket(self):
        """Checks if bucket exists, creates it if not."""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"[AgentB/MinIO] Created bucket '{self.bucket_name}'")
        except S3Error as e:
            logger.error(f"[AgentB/MinIO] Bucket check failed: {e}")

    def upload_memory_image(self, img_array, object_name: str) -> Optional[str]:
        """
        Encodes a generic OpenCV image to JPEG and uploads to MinIO.
        Returns: Presigned URL or None on failure.
        """
        try:
            # 1. Encode image to memory buffer (no file system usage)
            success, encoded_img = cv2.imencode('.jpg', img_array)
            if not success:
                logger.error("[AgentB/MinIO] Failed to encode image to memory.")
                return None
            
            # 2. Convert to BytesIO stream
            data_stream = io.BytesIO(encoded_img.tobytes())
            stream_size = data_stream.getbuffer().nbytes

            # 3. Upload
            self.client.put_object(
                self.bucket_name,
                object_name,
                data_stream,
                stream_size,
                content_type="image/jpeg"
            )
            
            # 4. Generate Link
            return self._generate_presigned_url(object_name)

        except S3Error as e:
            logger.error(f"[AgentB/MinIO] Upload failed: {e}")
            return None
        except Exception as e:
            logger.exception(f"[AgentB/MinIO] Unexpected error during upload: {e}")
            return None

    def _generate_presigned_url(self, object_name: str, expires_days: int = 7) -> str:
        """Generates a temporary access URL."""
        return self.client.get_presigned_url(
            "GET",
            self.bucket_name,
            object_name,
            expires=timedelta(days=expires_days)
        )