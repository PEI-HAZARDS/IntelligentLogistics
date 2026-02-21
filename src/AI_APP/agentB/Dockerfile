FROM python:3.11-slim

ENV PYTHONPATH=/app:/app/AI_APP \
    MODELS_PATH=/app/AI_APP/agentB/data \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# System dependencies
# chafa: terminal image viewing (debug)
# libgl1, libglib2.0-0: required by OpenCV
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    chafa \
    libgl1 \
    libglib2.0-0 && \
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
