# `image_storage.py`

> In-memory image upload and lifecycle management for MinIO object storage.

---

## Overview

`ImageStorage` provides a high-level interface to MinIO for uploading OpenCV images directly from memory (no disk I/O). It handles bucket creation, prefix-based lifecycle policies for automatic object expiry, and presigned URL generation.

Within the IntelligentLogistics system, every AI agent that captures or processes images depends on this module. `AgentA` uses it to store annotated detection frames, `AgentB` stores failed OCR crops, and `BaseAgent` instantiates it for both annotated-frame and crop storage. Images are organized under prefixes (`annotated_frames/`, `crops/`, `other/`) that map to different retention periods managed by MinIO lifecycle rules.

The module does **not** perform any image processing itself — it receives ready-to-upload `numpy.ndarray` frames, encodes them to JPEG, and pushes them to MinIO.

---

## Location
```
src/shared/src/image_storage.py
```

## Dependencies

### Internal
> N/A

### External
| Package | Version | Why it's used |
|---------|---------|---------------|
| `minio` | — | MinIO client for bucket operations, object upload, lifecycle config, and presigned URLs |
| `opencv-python` | `4.x` | JPEG encoding of in-memory image arrays via `cv2.imencode` |
| `numpy` | — | Image array type (`np.ndarray`) |
| `urllib3` | — | Connection error types (`MaxRetryError`, `NewConnectionError`) for resilient error handling |

> Standard library modules used: `typing`, `datetime`, `logging`, `io`.

---

## Architecture & Flow

```
  AgentA / AgentB / BaseAgent
       │
       │  upload_memory_image(frame, name, type)
       ▼
 ┌──────────────┐
 │ ImageStorage  │
 │               │
 │ _ensure_bucket│──► MinIO: create bucket + lifecycle rules
 │ cv2.imencode  │──► JPEG in memory
 │ put_object    │──► MinIO: upload
 │ presigned_url │◄── MinIO: temporary access link
 └──────────────┘
       │
       ▼
   MinIO Server
   (S3-compatible)
```

**Flow:**
1. Consumer calls `upload_memory_image()` with an OpenCV frame, object name, and image type.
2. The method validates the image type and input array.
3. `_ensure_bucket()` lazily creates the bucket and applies lifecycle policies on first use.
4. The frame is JPEG-encoded in memory and uploaded via `put_object`.
5. A presigned URL is generated with a TTL matching the image type's retention period and returned to the caller.

---

## Classes

### `ImageStorage`

> Handles interactions with MinIO Object Storage. Uploads images directly from memory without writing to disk. Supports prefix-based lifecycle management for automatic cleanup.

**Inherits from:** `None`

**Constructor**
```python
ImageStorage(configs: dict[str, Any], bucket_name: str)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `configs` | `dict[str, Any]` | required | MinIO client configuration passed as kwargs to `Minio()` (keys: `endpoint`, `access_key`, `secret_key`, `secure`) |
| `bucket_name` | `str` | required | Target MinIO bucket name |

**Attributes**
| Attribute | Type | Description |
|-----------|------|-------------|
| `self.client` | `Minio` | Initialized MinIO client instance |
| `self.bucket_name` | `str` | Target bucket name |
| `self._bucket_verified` | `bool` | Lazy flag — `True` after the bucket has been verified/created and lifecycle policies applied |

**Class-level Constants**
| Constant | Type | Value | Description |
|----------|------|-------|-------------|
| `VALID_IMAGE_TYPES` | `set[str]` | `{'annotated_frames', 'crops', 'other'}` | Allowed image type prefixes |
| `_IMAGE_TYPE_TTL_DAYS` | `dict[str, int]` | `{'annotated_frames': 1, 'crops': 7, 'other': 7}` | Retention period in days per image type |

---

#### Methods

##### `upload_memory_image(img_array, object_name, image_type="other")`

> Encodes an OpenCV image to JPEG in memory and uploads it to MinIO under a type-based prefix with automatic lifecycle cleanup.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `img_array` | `Optional[np.ndarray]` | required | OpenCV image array (BGR) |
| `object_name` | `str` | required | File name for the object (e.g. `'detection_123.jpg'`) |
| `image_type` | `str` | `"other"` | One of `'annotated_frames'` (1-day retention), `'crops'` (7-day), or `'other'` (7-day) |

**Returns:** `Optional[str]` — Presigned URL for the uploaded object, or `None` on failure.

**Raises:**

> No exceptions are propagated. All errors are caught and logged internally; the method returns `None`.

**Example**
```python
from shared.src.image_storage import ImageStorage

config = {
    "endpoint": "10.255.32.82:9000",
    "access_key": "minioadmin",
    "secret_key": "minioadmin",
    "secure": False
}
storage = ImageStorage(config, "agenta-1")

url = storage.upload_memory_image(frame, "TRK1234_1700000000.jpg", image_type="annotated_frames")
# url → "http://10.255.32.82:9000/agenta-1/annotated_frames/TRK1234_1700000000.jpg?X-Amz-..."
```

> ⚠️ **Note:** Invalid `image_type` values are silently normalized to `"other"` with a warning log. `None` or empty image arrays are rejected early before any network call.

---

##### `_ensure_bucket()`

> Checks if the target bucket exists and creates it if not. Applies lifecycle policies on first successful verification. Uses a lazy flag (`_bucket_verified`) to skip redundant checks on subsequent calls.

**Parameters**

> N/A

**Returns:** `bool` — `True` if the bucket is ready for use, `False` on failure.

**Raises:**

> No exceptions are propagated. `S3Error` is caught and logged.

> ⚠️ **Note:** Handles the `BucketAlreadyOwnedByYou` race condition when multiple processes create the same bucket concurrently.

---

##### `_set_lifecycle_policies()`

> Configures MinIO lifecycle rules for automatic object expiration based on prefix.

**Parameters**

> N/A

**Returns:** `None`

**Raises:**

> No exceptions are propagated. `S3Error` is caught and logged as a warning.

**Lifecycle rules applied:**
| Prefix | Rule ID | Retention |
|--------|---------|-----------|
| `annotated_frames/` | `delete-frame-images` | 1 day |
| `crops/` | `delete-crop-images` | 7 days |
| `other/` | `delete-other-images` | 7 days |

---

##### `_generate_presigned_url(object_name, expires_days=7)`

> Generates a temporary presigned GET URL for a stored object.

**Parameters**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `object_name` | `str` | required | Full object path including prefix (e.g. `'crops/img.jpg'`) |
| `expires_days` | `int` | `7` | URL validity period in days |

**Returns:** `str` — Presigned URL for the object.

**Raises:**

- `S3Error` — Propagated to the caller (caught in `upload_memory_image`).

---

## Standalone Functions

> N/A

---

## Configuration & Environment Variables

> N/A

> `ImageStorage` itself does not read environment variables. The MinIO connection configuration and bucket name are passed in by the caller. Consuming modules resolve environment variables (`MINIO_HOST`, `MINIO_PORT`, `ACCESS_KEY`, `SECRET_KEY`, `GATE_ID`) to construct the config dict before instantiation.

---

## Usage Example

End-to-end usage as seen in `AgentA`:
```python
import os
from shared.src.image_storage import ImageStorage

# MinIO configuration from environment
MINIO_CONFIG = {
    "endpoint": f"{os.getenv('MINIO_HOST', '10.255.32.82')}:{os.getenv('MINIO_PORT', '9000')}",
    "access_key": os.getenv("ACCESS_KEY"),
    "secret_key": os.getenv("SECRET_KEY"),
    "secure": False
}
BUCKET_NAME = f"agenta-{os.getenv('GATE_ID', '1')}"

storage = ImageStorage(MINIO_CONFIG, BUCKET_NAME)

# Upload an annotated detection frame (1-day retention)
import time
url = storage.upload_memory_image(
    annotated_frame,
    f"TRK1234_{int(time.time())}.jpg",
    image_type="annotated_frames"
)

if url:
    print(f"Uploaded: {url}")
else:
    print("Upload failed or MinIO unavailable")
```

---

## Error Handling

All exceptions in `upload_memory_image()` are caught internally — the method never propagates exceptions to the caller:

- **Input validation** — `None` or empty image arrays are rejected early with an `ERROR` log, returning `None`.
- **Invalid image type** — Unrecognized `image_type` values fall back to `"other"` with a `WARNING` log.
- **Bucket operations** — `S3Error` during bucket creation or lifecycle configuration is caught in `_ensure_bucket()`, returning `False` and causing the upload to abort.
- **Upload failures** — `S3Error` during `put_object` is caught and logged at `ERROR`, returning `None`.
- **Connection failures** — `MaxRetryError`, `NewConnectionError`, and `ConnectionError` are caught separately with a `WARNING` log indicating MinIO may be down, allowing the calling agent to continue operating without storage.
- **Unexpected errors** — All other exceptions are caught via a broad `except Exception` with `logger.exception()`.

Logging uses a named logger (`ImageStorage`) at `INFO`, `WARNING`, and `ERROR` levels.

---

## Testing

| Test file | Type | What it covers |
|-----------|------|----------------|
| `image_storage_unit_test.py` | Unit | Initialization, bucket creation/verification, lifecycle policies, image upload (success, None input, empty input, encoding failure, S3 errors, connection errors), presigned URL generation |

To run:
```bash
pytest src/shared/tests/image_storage_unit_test.py
```

---

## Known Issues / TODOs

> N/A

---

## Changelog

> N/A

---

## Related Docs

- [`stream_manager.md`](./stream_manager.md) — Another shared module used by the same agents
- [`base_agent.md`](./base_agent.md) — Base class that instantiates `ImageStorage` for agents
- [`template.md`](../template.md) — Documentation template
