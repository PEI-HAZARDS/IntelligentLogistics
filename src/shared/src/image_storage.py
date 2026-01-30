from typing import Optional
from minio import Minio # type: ignore
from minio.error import S3Error # type: ignore
from minio.lifecycleconfig import LifecycleConfig, Rule, Expiration # type: ignore
from minio.commonconfig import Filter # type: ignore
from datetime import timedelta
import logging
import cv2
import io

logger = logging.getLogger("ImageStorage")

class ImageStorage:
    """
    Handles interactions with MinIO Object Storage.
    Uploads images directly from memory without writing to disk.
    Supports prefix-based lifecycle management for automatic cleanup.
    """
    def __init__(self, configs, bucket_name):
        logger.info("Connecting to MinIO...")
        self.client = Minio(**configs)
        self.bucket_name = bucket_name

    def _ensure_bucket(self) -> bool:
        """Checks if bucket exists, creates it if not. Returns True if bucket is ready."""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"Created bucket '{self.bucket_name}'")
                # Set lifecycle policies for automatic cleanup
                self._set_lifecycle_policies()
            return True
        except S3Error as e:
            logger.error(f"Bucket check/create failed: {e}")
            return False

    def _set_lifecycle_policies(self):
        """
        Configures automatic deletion policies for different image types:
        - debug/: 1 day (MinIO minimum, approximates 2 hours)
        - temp/: 1 day (24 hours)
        - delivery/: 7 days
        
        Note: MinIO evaluates lifecycle rules every 24 hours, so sub-daily 
        expiration is not precisely controllable. Debug images set to 1 day minimum.
        """
        try:
            config = LifecycleConfig(
                [
                    # Debug images: delete after 1 day (MinIO's minimum)
                    Rule(
                        rule_id="delete-debug-images",
                        rule_filter=Filter(prefix="debug/"),
                        status="Enabled",
                        expiration=Expiration(days=1)
                    ),
                    # Temporary processing images: delete after 1 day
                    Rule(
                        rule_id="delete-temp-images",
                        rule_filter=Filter(prefix="temp/"),
                        status="Enabled",
                        expiration=Expiration(days=1)
                    ),
                    # Delivery proof images: delete after 7 days
                    Rule(
                        rule_id="delete-delivery-images",
                        rule_filter=Filter(prefix="delivery/"),
                        status="Enabled",
                        expiration=Expiration(days=7)
                    )
                ]
            )
            self.client.set_bucket_lifecycle(self.bucket_name, config)
            logger.info("Lifecycle policies configured: debug/temp (1 day), delivery (7 days)")
        except S3Error as e:
            logger.warning(f"Failed to set lifecycle policies: {e}")

    def upload_memory_image(self, img_array, object_name: str, image_type: str = "temp") -> Optional[str]:
        """
        Encodes a generic OpenCV image to JPEG and uploads to MinIO with automatic cleanup.
        
        Args:
            img_array: OpenCV image array
            object_name: File name (e.g., 'detection_123.jpg')
            image_type: One of 'debug', 'temp', or 'delivery' (determines retention)
                - 'debug': ~1 day retention (for debugging/development)
                - 'temp': 1 day retention (for temporary processing)
                - 'delivery': 7 days retention (for delivery proofs)
        
        Returns: 
            Presigned URL or None on failure.
        """
        try:
            # Validate image_type
            valid_types = ['debug', 'temp', 'delivery']
            if image_type not in valid_types:
                logger.warning(f"Invalid image_type '{image_type}', defaulting to 'temp'")
                image_type = 'temp'
            
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

            # Add prefix based on image type
            prefixed_name = f"{image_type}/{object_name}"

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
                prefixed_name,
                data_stream,
                stream_size,
                content_type="image/jpeg"
            )
            logger.info(f"Uploaded {image_type} image as '{prefixed_name}' to bucket '{self.bucket_name}'")

            # 4. Generate Link
            return self._generate_presigned_url(prefixed_name)

        except S3Error as e:
            logger.error(f"Upload failed: {e}")
            return None
        except Exception as e:
            # Check for urllib3/requests connection errors by type name
            if e.__class__.__name__ in ("MaxRetryError", "NewConnectionError"):
                logger.warning(f"[MinIO] Connection error during upload: {e}. MinIO may be down. Skipping upload and continuing.")
                return None
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