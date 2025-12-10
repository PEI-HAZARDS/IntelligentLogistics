# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY src/decision_engine_microservice/requirements.txt /app/decision_engine_microservice/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/decision_engine_microservice/requirements.txt

    # Install system dependencies (openCV, ffmpeg, etc.)
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0

# Copy shared utils
COPY src/shared_utils /app/shared_utils

# Copy decision engine microservice
COPY src/decision_engine_microservice/src /app/decision_engine_microservice/src
COPY src/decision_engine_microservice/init.py /app/decision_engine_microservice/init.py


# Set PYTHONPATH to include the app directory
ENV PYTHONPATH=/app

# Set environment variables for Kafka (can be overridden at runtime)
ENV KAFKA_BOOTSTRAP=10.255.32.64:9092

# Run the agent
CMD ["python", "/app/decision_engine_microservice/init.py"]