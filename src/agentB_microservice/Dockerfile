# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (needed for OpenCV, PaddleOCR, Tesseract, etc.)
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    ffmpeg \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Copy shared utilities
COPY src/shared_utils /app/shared_utils

# Copy agentB microservice
COPY src/agentB_microservice/src /app/agentB_microservice/src
COPY src/agentB_microservice/init.py /app/agentB_microservice/init.py
COPY src/agentB_microservice/requirements.txt /app/agentB_microservice/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/agentB_microservice/requirements.txt

# Set PYTHONPATH to include the app directory
ENV PYTHONPATH=/app

# Set environment variables for Kafka (can be overridden at runtime)
ENV KAFKA_BOOTSTRAP=10.255.32.64:9092

# Default command to run the service
CMD ["python", "/app/agentB_microservice/init.py"]
