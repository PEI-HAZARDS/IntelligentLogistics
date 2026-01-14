# Use Python 3.11 slim image as base
FROM docker.io/python:3.11-slim@sha256:193fdd0bbcb3d2ae612bd6cc3548d2f7c78d65b549fcaa8af75624c47474444d

# Environment variables (runtime vars provided via docker-compose/.env)
ENV PYTHONPATH=/app

WORKDIR /app

# 1. System dependencies (OpenCV, etc.)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

# 2. Python dependencies
COPY requirements.txt ./decision_engine_microservice/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r decision_engine_microservice/requirements.txt

# 3. Copy source code
COPY src/ ./decision_engine_microservice/src/
COPY init.py ./decision_engine_microservice/
COPY tests/ ./decision_engine_microservice/tests/

# 5. Start the microservice
CMD ["python", "decision_engine_microservice/init.py"]