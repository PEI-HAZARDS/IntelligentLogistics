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
    pip install --no-cache-dir -r requirements.txt

# Source code — only what agentB needs
COPY AI_APP/agentB/ ./AI_APP/agentB/
COPY AI_APP/shared/ ./AI_APP/shared/
COPY shared/ ./shared/

# Download model
RUN python AI_APP/agentB/setup.py

CMD ["python", "AI_APP/agentB/init.py"]
