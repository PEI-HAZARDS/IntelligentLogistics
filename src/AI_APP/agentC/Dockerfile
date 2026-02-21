FROM python:3.11-slim

ENV PYTHONPATH=/app:/app/AI_APP \
    MODELS_PATH=/app/AI_APP/agentC/data \
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
COPY AI_APP/agentC/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Source code — only what agentC needs
COPY AI_APP/agentC/ ./AI_APP/agentC/
COPY shared/ ./shared/

# Download model
RUN python AI_APP/agentC/setup.py

CMD ["python", "AI_APP/agentC/init.py"]
