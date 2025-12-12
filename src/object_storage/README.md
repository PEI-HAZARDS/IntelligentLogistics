**MinIO (Object Storage) - Local Docker setup**

This folder contains a simple Dockerfile and a `docker-compose.yml` to run a local MinIO instance (S3-compatible object storage) used by the project.

Files included:
- `Dockerfile` - lightweight wrapper using the official `minio/minio` image.
- `docker-compose.yml` - docker-compose example with ports and a persistent `./data/minio` volume.

Quick summary
- MinIO API (S3) is exposed on port `9000`.
- MinIO Console (web UI) is exposed on port `9001`.
- Default credentials in `docker-compose.yml`: `MINIO_ROOT_USER=minioadmin`, `MINIO_ROOT_PASSWORD=minioadmin` (change for production).

Run with Docker Compose (recommended for local dev)

```bash
cd src/object_storage
docker-compose up -d
```

Run with plain Docker

```bash
docker build -t local-minio .
docker run -d --name minio -p 9000:9000 -p 9001:9001 -v "$PWD/data/minio:/data" \
	-e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin local-minio
```

Create a bucket (using `mc` - MinIO client)

Install `mc` (https://min.io/docs/minio/linux/reference/minio-mc.html)

```bash
# configure alias
mc alias set local http://127.0.0.1:9000 minioadmin minioadmin

# create a bucket called `lp-crops`
mc mb local/lp-crops

# list buckets
mc ls local
```

Upload an object (example using `mc`)

```bash
mc cp /path/to/image.jpg local/lp-crops/lp_sample.jpg
```

Using AWS S3 SDKs / `boto3`

MinIO is S3-compatible. Example Python snippet using `boto3`:

```python
import boto3
from botocore.client import Config

s3 = boto3.client('s3',
									endpoint_url='http://127.0.0.1:9000',
									aws_access_key_id='minioadmin',
									aws_secret_access_key='minioadmin',
									config=Config(signature_version='s3v4'),
									region_name='us-east-1')

# upload
s3.upload_file('/path/to/image.jpg', 'lp-crops', 'lp_image.jpg')

# generate presigned URL (valid 7 days)
url = s3.generate_presigned_url('get_object', Params={'Bucket':'lp-crops','Key':'lp_image.jpg'}, ExpiresIn=604800)
print(url)
```

Environment variables in the project

The project uses environment variables to find MinIO. By default in code the bucket and host may be configured via:

- `MINIO_HOST` (example: `10.255.32.132`)
- `MINIO_PORT` (example: `9000`)
- `ACCESS_KEY` and `SECRET_KEY` for credentials
- `BUCKET_NAME` (example: `lp-crops`)

For local testing you can export these to match the docker-compose defaults:

```bash
export MINIO_HOST=127.0.0.1
export MINIO_PORT=9000
export ACCESS_KEY=minioadmin
export SECRET_KEY=minioadmin
export BUCKET_NAME=lp-crops
```

Notes & Recommendations
- For production, do NOT use `minioadmin/minioadmin`. Set strong credentials and secure access (TLS).
- Persist the `./data/minio` directory or mount a managed volume to avoid data loss.
- If running MinIO behind a reverse proxy, configure the console and API ports accordingly.

Troubleshooting
- If the console is inaccessible, check container logs: `docker logs minio`.
- If uploads fail from the app, verify `ACCESS_KEY` / `SECRET_KEY` and endpoint/port.

If you want, I can also add a small script that pre-creates the `lp-crops` bucket at container startup.

