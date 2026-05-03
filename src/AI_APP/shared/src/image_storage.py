import time
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
from AI_APP.shared.src.object_detector import ObjectDetector


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

    def __init__(self, configs: dict[str, Any], bucket_name: str, models_path: str, privacy_mode : bool = True, object_detector: Optional[ObjectDetector] = None):
        logger.info("Initializing MinIO client...")
        self.client = Minio(**configs)
        self.bucket_name = bucket_name
        self.privacy_mode = privacy_mode
        
        try:
            self.yolo_person = object_detector or ObjectDetector(models_path + "/truck_model.pt", 0)
            self.yolo_truck = object_detector or ObjectDetector(models_path + "/truck_model.pt", 7)
        except FileNotFoundError as e:
            logger.critical(f"Model file not found — cannot start MinIO client: {e}")
            raise SystemExit(1) from e
        except RuntimeError as e:
            logger.critical(f"Failed to load YOLO model — cannot MinIO client: {e}")
            raise SystemExit(1) from e
    
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
            
            # 0. Apply privacy filters if enabled
            if self.privacy_mode:
                start = time.time()
                blurred_img = self._people_blur(img_array)
                if blurred_img is not None:
                    img_array = blurred_img
                else:
                    logger.warning("People blur skipped due to error, continuing with original image")
                
                blurred_img = self._cabine_blur(img_array)
                if blurred_img is not None:
                    img_array = blurred_img
                else:
                    logger.warning("Cabin blur skipped due to error, continuing with current image")
                
                elapsed = time.time() - start
                logger.info(f"Privacy filters applied in {elapsed:.2f} seconds")
            
            # 1. Ensure bucket exists (retry if initial creation failed)
            if not self._ensure_bucket():
                logger.error("Cannot upload: bucket unavailable")
                return None

            # Add prefix based on image type
            prefixed_name = f"{image_type}/{object_name}"

            # 2. Encode image to memory buffer (no file system usage)
            success, encoded_img = cv2.imencode('.jpg', img_array)
            if not success:
                logger.error("Failed to encode image to memory.")
                return None

            # 3. Convert to BytesIO stream
            data_stream = io.BytesIO(encoded_img.tobytes())
            stream_size = data_stream.getbuffer().nbytes

            # 4. Upload
            self.client.put_object(
                self.bucket_name,
                prefixed_name,
                data_stream,
                stream_size,
                content_type="image/jpeg"
            )
            logger.info(f"Uploaded '{prefixed_name}' to bucket '{self.bucket_name}'")

            # 5. Generate Link
            expires = self._IMAGE_TYPE_TTL_DAYS.get(image_type, 7)
            return self._generate_presigned_url(prefixed_name, expires_days=expires)

        except S3Error as e:
            logger.error(f"Upload failed: {e}")
            return None
        
        except (MaxRetryError, NewConnectionError, ConnectionError) as e:
            logger.warning(f"[MinIO] Connection error during upload: {e}. MinIO may be down. Skipping upload and continuing.")
            return None
        
        except Exception as e:
            logger.exception(f"Unexpected error during upload: {e}")
            return None

    def _people_blur(self, img_array: np.ndarray) -> np.ndarray:
        """Detects and blurs people in the image using YOLO."""
        try:
            detections = self.yolo_person.detect(img_array)
            boxes = self.yolo_person.get_boxes(detections)
            for box in boxes:
                x1, y1, x2, y2 = map(int, box[:4])
                # Extract body region
                body_region = img_array[y1:y2, x1:x2]
                # Apply Gaussian blur to the body region
                blurred_body = cv2.GaussianBlur(body_region, (99, 99), 30)
                # Replace original body with blurred version
                img_array[y1:y2, x1:x2] = blurred_body
            return img_array
        
        except Exception as e:
            logger.warning(f"Body blurring failed: {e}.")
            return None
    
    def _cabine_blur(self, img_array: np.ndarray) -> np.ndarray:
        """Detects and blurs the truck cabin area using YOLO."""
        try:
            detections = self.yolo_truck.detect(img_array)
            boxes = self.yolo_truck.get_boxes(detections)
            if boxes:
                logger.info(f"{len(boxes)} cabin(s) detected. Blurring...")
            for box in boxes:
                x1, y1, x2, y2 = map(int, box[:4])
                # Extract cabin region
                cab_bottom = y1 + int((y2 - y1) * 0.35)
                cabin_region = img_array[y1:cab_bottom, x1:x2]
                # Apply Gaussian blur to the cabin region
                blurred_cabin = cv2.GaussianBlur(cabin_region, (99, 99), 30)
                # Replace original cabin with blurred version
                img_array[y1:y2, x1:x2] = blurred_cabin
            return img_array
        
        except Exception as e:
            logger.warning(f"Cabin blurring failed: {e}.")
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
            logger.error(f"Bucket check/create failed: {e}")
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
            logger.warning(f"Failed to set lifecycle policies: {e}")

    def _generate_presigned_url(self, object_name: str, expires_days: int = 7) -> str:
        """Generates a temporary access URL."""
        return self.client.get_presigned_url(
            "GET",
            self.bucket_name,
            object_name,
            expires=timedelta(days=expires_days)
        )