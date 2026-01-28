# Use Python 3.11 slim image as base
FROM docker.io/python:3.11-slim@sha256:193fdd0bbcb3d2ae612bd6cc3548d2f7c78d65b549fcaa8af75624c47474444d

# Environment variables (runtime vars provided via docker-compose/.env)
ENV PYTHONPATH=/agentA \
    MODELS_PATH=/agentA/data

WORKDIR /agentA

# 1. System dependencies (OpenCV, etc.)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

# 2. Python dependencies
COPY agentA/requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 3. Copy source code
COPY agentA/src/ ./src/
COPY shared/ ./shared/
COPY agentA/init.py agentA/setup.py ./
COPY agentA/tests/ ./tests/

# 4. Download YOLO model
RUN python -c "from setup import setup; setup()" && \
    echo "Models ready in $MODELS_PATH"

# 5. Start the microservice
CMD ["python", "init.py"]