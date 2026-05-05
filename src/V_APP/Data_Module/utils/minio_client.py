"""
MinIO client helper for the Data Module.

Used exclusively by the RGPD erasure handler to delete alert images
when a driver exercises the right to erasure (Art. 17 RGPD).

URL format stored in alert.image_url:
  http://<host>:<port>/<bucket>/<object-path>
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error

from config import settings

logger = logging.getLogger(__name__)


def _get_client() -> Minio:
    return Minio(
        f"{settings.minio_host}:{settings.minio_port}",
        access_key=settings.minio_root_user,
        secret_key=settings.minio_root_password,
        secure=False,
    )


def delete_object_by_url(image_url: str) -> bool:
    """
    Delete a MinIO object given its full HTTP URL.
    Returns True on success, False if the object was not found or deletion failed.
    """
    try:
        parsed = urlparse(image_url)
        # Path is /<bucket>/<object-key...>
        parts = parsed.path.lstrip("/").split("/", 1)
        if len(parts) != 2:
            logger.warning("Cannot parse MinIO URL (expected /bucket/key): %s", image_url)
            return False
        bucket, object_key = parts
        client = _get_client()
        client.remove_object(bucket, object_key)
        logger.info("Deleted MinIO object: %s/%s", bucket, object_key)
        return True
    except S3Error as exc:
        if exc.code == "NoSuchKey":
            logger.debug("MinIO object already absent: %s", image_url)
            return True
        logger.error("MinIO deletion failed for %s: %s", image_url, exc)
        return False
    except Exception as exc:
        logger.error("Unexpected error deleting MinIO object %s: %s", image_url, exc)
        return False


def delete_objects_by_urls(urls: list[str]) -> dict[str, bool]:
    """Delete multiple objects, returning a map of url → success."""
    return {url: delete_object_by_url(url) for url in urls if url}
