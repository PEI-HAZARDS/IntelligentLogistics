# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (openCV, ffmpeg, etc.)
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy shared utils
COPY src/shared_utils /app/shared_utils

# Copy agentA microservice
COPY src/agentA_microservice/src /app/agentA_microservice/src
COPY src/agentA_microservice/init.py /app/agentA_microservice/init.py
COPY src/agentA_microservice/requirements.txt /app/agentA_microservice/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/agentA_microservice/requirements.txt

# Set PYTHONPATH to include the app directory
ENV PYTHONPATH=/app

# Set environment variables for Kafka (can be overridden at runtime)
ENV KAFKA_BOOTSTRAP=10.255.32.64:9092

# Run the agent
CMD ["python", "/app/agentA_microservice/init.py"]