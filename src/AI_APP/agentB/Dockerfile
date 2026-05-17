FROM nvidia/cuda:13.1.1-runtime-ubuntu22.04

ENV PYTHONPATH=/app:/app/AI_APP \
    MODELS_PATH=/app/AI_APP/agentB/data \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# System dependencies + Python 3.11
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    chafa \
    libgl1 \
    libglib2.0-0 \
    python3-pip \
    python3.11 python3.11-venv && \
    ln -sf /usr/bin/python3.11 /usr/bin/python && \
    ln -sf /usr/bin/python3.11 /usr/bin/python3 && \
    rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY AI_APP/agentB/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --ignore-installed blinker -r requirements.txt

# Source code — only what agentB needs
COPY AI_APP/agentB/ ./AI_APP/agentB/
COPY AI_APP/shared/ ./AI_APP/shared/
COPY shared/ ./shared/

# ML registry scripts (needed by setup.py to download the model)
COPY ml-registry/scripts/ ./ml-registry/scripts/

# MLflow / MinIO credentials — passed as build args so setup.py can reach the registry
ARG MLFLOW_TRACKING_URI
ARG MLFLOW_S3_ENDPOINT_URL
ARG AWS_ACCESS_KEY_ID
ARG AWS_SECRET_ACCESS_KEY
ARG MODEL_CACHE_DIR=/tmp/model_cache

ENV MLFLOW_TRACKING_URI=${MLFLOW_TRACKING_URI} \
    MLFLOW_S3_ENDPOINT_URL=${MLFLOW_S3_ENDPOINT_URL} \
    AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID} \
    AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY} \
    MODEL_CACHE_DIR=${MODEL_CACHE_DIR}

# Download model from local MLflow registry at build time
RUN python AI_APP/agentB/setup.py

CMD ["python", "AI_APP/agentB/init.py"]
