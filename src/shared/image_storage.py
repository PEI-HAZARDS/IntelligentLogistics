from typing import Optional
from minio import Minio # type: ignore
from minio.error import S3Error # type: ignore
from datetime import timedelta
import logging
import cv2
import io

logger = logging.getLogger("ImageStorage")

class ImageStorage:
    """
    Handles interactions with MinIO Object Storage.
    Uploads images directly from memory without writing to disk.
    """
    def __init__(self, configs, bucket_name):
        logger.info("Connecting to MinIO...")
        
        self.client = Minio(**configs)
        self.bucket_name = bucket_name
        self._ensure_bucket()

    def _ensure_bucket(self) -> bool:
        """Checks if bucket exists, creates it if not. Returns True if bucket is ready."""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"Created bucket '{self.bucket_name}'")
            return True
        except S3Error as e:
            logger.error(f"Bucket check/create failed: {e}")
            return False

    def upload_memory_image(self, img_array, object_name: str) -> Optional[str]:
        """
        Encodes a generic OpenCV image to JPEG and uploads to MinIO.
        Returns: Presigned URL or None on failure.
        """
        try:
            # 0. Ensure bucket exists (retry if initial creation failed)
            if not self._ensure_bucket():
                logger.error("Cannot upload: bucket unavailable")
                return None

            # Guard: ensure image is not empty/None before encoding
            if img_array is None:
                logger.error("Cannot upload: image is None")
                return None
            if hasattr(img_array, 'size') and img_array.size == 0:
                logger.error("Cannot upload: image array is empty")
                return None

            # 1. Encode image to memory buffer (no file system usage)
            success, encoded_img = cv2.imencode('.jpg', img_array)
            if not success:
                logger.error("Failed to encode image to memory.")
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

            logger.info(f"Uploaded image as '{object_name}' to bucket '{self.bucket_name}'")
            
            # 4. Generate Link
            return self._generate_presigned_url(object_name)

        except S3Error as e:
            logger.error(f"Upload failed: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error during upload: {e}")
            return None

    def _generate_presigned_url(self, object_name: str, expires_days: int = 7) -> str:
        """Generates a temporary access URL."""
        return self.client.get_presigned_url(
            "GET",
            self.bucket_name,
            object_name,
            expires=timedelta(days=expires_days)
        )