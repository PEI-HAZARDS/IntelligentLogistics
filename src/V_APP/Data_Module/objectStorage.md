# Object Storage - MinIO S3-Compatible Storage (10.255.32.82)

**MinIO** provides S3-compatible object storage for the hazardous vehicle detection pipeline. It stores license plate and hazard plate crop images uploaded by AgentB and AgentC, making them accessible via HTTP URLs for the API Gateway and Frontend.

---

## Table of Contents

- [How It Works](#how-it-works)
- [Buckets](#buckets)
- [Running with Docker](#running-with-docker)
- [Environment Variables](#environment-variables)
- [Using the MinIO Client (mc)](#using-the-minio-client-mc)
- [Integration with Python (boto3)](#integration-with-python-boto3)
- [Troubleshooting](#troubleshooting)

---

## How It Works

### Operation Flow

1. **Image Upload**: AgentB and AgentC detect plates, extract crops, and upload them to MinIO.

2. **URL Generation**: MinIO returns public URLs for the uploaded images.

3. **URL Publishing**: Agents include the crop URLs in their Kafka messages.

4. **Image Access**: The API Gateway and Frontend can access images via the stored URLs.

### Storage Structure

```
MinIO Server
    │
    ├─ lp-crops/                    (License Plate crops)
    │   ├─ lp_TRK123_ABC1234.jpg
    │   └─ lp_TRK456_XYZ9876.jpg
    │
    └─ hz-crops/                    (Hazard Plate crops)
        ├─ hz_TRK123_33_1203.jpg
        └─ hz_TRK456_X423_1830.jpg
```

---

## Buckets

| Bucket | Purpose | Created By |
|--------|---------|------------|
| `lp-crops` | License plate crop images | AgentB |
| `hz-crops` | Hazard plate crop images | AgentC |
| `failed-crops` | Failed classification crops (debug) | AgentB |

---

## Running with Docker

### Using Docker Compose (Recommended)

```bash
cd src/object_storage
docker-compose up -d
```


### Accessing MinIO

| Interface | URL | Description |
|-----------|-----|-------------|
| S3 API | `http://10.255.32.82:9000` | S3-compatible API endpoint |
| Web Console | `http://10.255.32.82:9090` | Web-based management UI |

---

## Environment Variables

### MinIO Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MINIO_ROOT_USER` | `minioadmin` | Root username (change for production) |
| `MINIO_ROOT_PASSWORD` | `minioadmin` | Root password (change for production) |

### Application Configuration (Used by Agents)

| Variable | Default | Description |
|----------|---------|-------------|
| `MINIO_HOST` | `10.255.32.82` | MinIO server hostname/IP |
| `MINIO_PORT` | `9000` | MinIO S3 API port |
| `ACCESS_KEY` | (required) | MinIO access key |
| `SECRET_KEY` | (required) | MinIO secret key |
| `BUCKET_NAME` | `lp-crops` / `hz-crops` | Target bucket for uploads |

### Local Testing

```bash
export MINIO_HOST=127.0.0.1
export MINIO_PORT=9000
export ACCESS_KEY=minioadmin
export SECRET_KEY=minioadmin
export BUCKET_NAME=lp-crops
```

---

## Using the MinIO Client (mc)

### Installation

See: https://min.io/docs/minio/linux/reference/minio-mc.html

### Configure Alias

```bash
mc alias set local http://127.0.0.1:9000 minioadmin minioadmin
```

### Create Buckets

```bash
# Create license plate bucket
mc mb local/lp-crops

# Create hazard plate bucket
mc mb local/hz-crops

# List all buckets
mc ls local
```

### Upload/Download Files

```bash
# Upload an image
mc cp /path/to/image.jpg local/lp-crops/lp_sample.jpg

# Download an image
mc cp local/lp-crops/lp_sample.jpg /path/to/download/

# List bucket contents
mc ls local/lp-crops
```

---

## Integration with Python (boto3)

MinIO is S3-compatible, so you can use the AWS SDK for Python:


### Using CropStorage (Project Utility)

The project provides a `CropStorage` class that wraps MinIO operations:

```python
from agentB_microservice.src.CropStorage import CropStorage

MINIO_CONF = {
    "endpoint": "10.255.32.82:9000",
    "access_key": "minioadmin",
    "secret_key": "minioadmin",
    "secure": False
}

storage = CropStorage(MINIO_CONF, "lp-crops")

# Upload image from memory (numpy array)
url = storage.upload_memory_image(crop_array, "lp_TRK123_ABC1234.jpg")
print(f"Uploaded: {url}")
```

---


