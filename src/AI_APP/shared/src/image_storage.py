from typing import Any, Optional
from minio import Minio # type: ignore
from minio.error import S3Error # type: ignore
from minio.lifecycleconfig import LifecycleConfig, Rule, Expiration # type: ignore
from minio.commonconfig import Filter # type: ignore
from urllib3.exceptions import MaxRetryError, NewConnectionError # type: ignore
from datetime import timedelta
import logging
import cv2 # type: ignore
import numpy as np # type: ignore
import io

logger = logging.getLogger("ImageStorage")

class ImageStorage:
    """
    Handles interactions with MinIO Object Storage.
    Uploads images directly from memory without writing to disk.
    Supports prefix-based lifecycle management for automatic cleanup.
    """

    # Outside of __init__: class-level constants and variables
    VALID_IMAGE_TYPES = {'annotated_frames', 'crops', 'other'}
    _IMAGE_TYPE_TTL_DAYS = {
        'annotated_frames': 1,
        'crops': 7,
        'other': 7,
    }

    def __init__(self, configs: dict[str, Any], bucket_name: str):
        logger.info("Initializing MinIO client...")
        self.client = Minio(**configs)
        self.bucket_name = bucket_name
    
    def upload_memory_image(self, img_array: Optional[np.ndarray], object_name: str, image_type: str = "other") -> Optional[str]:
        """
        Encodes a generic OpenCV image to JPEG and uploads to MinIO with automatic cleanup.
        
        Args:
            img_array: OpenCV image array
            object_name: File name (e.g., 'detection_123.jpg')
            image_type: One of 'annotated_frames', 'other', or 'crops' (determines retention)
                - 'annotated_frames': 1 day retention (for temporary processing)
                - 'other': 7 days retention (for temporary storage)
                - 'crops': 7 days retention (for delivery proofs)
        
        Returns: 
            Presigned URL or None on failure.
        """
        try:
            # Validate image_type
            if image_type not in self.VALID_IMAGE_TYPES:
                logger.warning(f"Invalid image_type '{image_type}', defaulting to 'other'")
                image_type = 'other'

            # Guard: ensure image is not empty/None before encoding (fail fast)
            if img_array is None:
                logger.error("Cannot upload: image is None")
                return None
            
            if hasattr(img_array, 'size') and img_array.size == 0:
                logger.error("Cannot upload: image array is empty")
                return None
            
            # 0. Ensure bucket exists (retry if initial creation failed)
            if not self._ensure_bucket():
                logger.error("Cannot upload: bucket unavailable")
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
            logger.info(f"Uploaded '{prefixed_name}' to bucket '{self.bucket_name}'")

            # 4. Generate Link
            expires = self._IMAGE_TYPE_TTL_DAYS.get(image_type, 7)
            return self._generate_presigned_url(prefixed_name, expires_days=expires)

        except S3Error as e:
            logger.exception("Upload failed")
            return None
        
        except (MaxRetryError, NewConnectionError, ConnectionError) as e:
            logger.exception("[MinIO] Connection error during upload. MinIO may be down. Skipping upload and continuing.")
            return None
        
        except Exception as e:
            logger.exception("Unexpected error during upload")
            return None

    def _ensure_bucket(self) -> bool:
        """Checks if bucket exists, creates it if not. Returns True if bucket is ready."""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                try:
                    self.client.make_bucket(self.bucket_name)
                    logger.info(f"Created bucket '{self.bucket_name}'")
                    
                except S3Error as e:
                    # Another process may have created it concurrently
                    if "BucketAlreadyOwnedByYou" not in str(e):
                        raise
                    
            # Always ensure lifecycle policies are up to date
            self._set_lifecycle_policies()
            
            return True
        
        except S3Error as e:
            logger.exception("Bucket check/create failed")
            return False

    def _set_lifecycle_policies(self):
        """
        Configures automatic deletion policies for different image types:
        - annotated_frames/: 1 day (24 hours)
        - crops/: 7 days
        """
        try:
            config = LifecycleConfig(
                [
                    # Debug images: delete after 1 day (MinIO's minimum)
                    Rule(
                        rule_id="delete-frame-images",
                        rule_filter=Filter(prefix="annotated_frames/"),
                        status="Enabled",
                        expiration=Expiration(days=1)
                    ),
                    # Delivery proof images: delete after 7 days
                    Rule(
                        rule_id="delete-crop-images",
                        rule_filter=Filter(prefix="crops/"),
                        status="Enabled",
                        expiration=Expiration(days=7)
                    ),
                    Rule(
                        rule_id="delete-other-images",
                        rule_filter=Filter(prefix="other/"),
                        status="Enabled",
                        expiration=Expiration(days=7)
                    )
                ]
            )
            
            self.client.set_bucket_lifecycle(self.bucket_name, config)
            logger.info("Lifecycle policies configured: annotated_frames (1 day), crops (7 days)")
        
        except S3Error as e:
            logger.exception("Failed to set lifecycle policies")

    def _generate_presigned_url(self, object_name: str, expires_days: int = 7) -> str:
        """Generates a temporary access URL."""
        return self.client.get_presigned_url(
            "GET",
            self.bucket_name,
            object_name,
            expires=timedelta(days=expires_days)
        )