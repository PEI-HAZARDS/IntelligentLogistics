# Use Python 3.11 slim image as base
FROM docker.io/python:3.11-slim@sha256:193fdd0bbcb3d2ae612bd6cc3548d2f7c78d65b549fcaa8af75624c47474444d

# Environment variables (TODO: store sensitive data securely)
ENV PYTHONPATH=/app \
    KAFKA_BOOTSTRAP=10.255.32.143:9092 \
    MODELS_PATH=/app/agentC_microservice/data \
    GATE_ID=1 \
    NGINX_RTMP_HOST=10.255.32.35 \
    MINIO_HOST=10.255.32.132 \
    MINIO_PORT=9000 \
    ACCESS_KEY=admin \    
    SECRET_KEY=adminadmin \
    BUCKET_NAME=hz-crops \
    NGINX_RTMP_PORT=1935

WORKDIR /app

# 1. System dependencies (OpenCV, etc.)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    chafa  \
    libgl1 \
    libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

# 2. Python dependencies
COPY requirements.txt ./agentC_microservice/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r agentC_microservice/requirements.txt

# 3. Copy source code
COPY src/ ./agentC_microservice/src/
COPY init.py setup.py ./agentC_microservice/
COPY tests/ ./agentC_microservice/tests/

# 4. Download YOLO model
RUN python -c "from agentC_microservice.setup import setup; setup()" && \
    echo "Models ready in $MODELS_PATH"

# 5. Start the microservice
CMD ["python", "agentC_microservice/init.py"]