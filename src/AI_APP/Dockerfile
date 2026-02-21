# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Environment variables
ENV PYTHONPATH=/app:/app/AI_APP \
    MODELS_PATH=/app/data \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# 1. System dependencies
# chafa: for terminal image viewing (AgentB/C might use it for debug)
# libgl1, libglib2.0-0: for OpenCV
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    chafa \
    libgl1 \
    libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

# 2. Python dependencies
COPY AI_APP/requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 3. Copy source code
# We copy the entire AI_APP and shared directories to preserve structure
COPY AI_APP/ ./AI_APP/
COPY shared/ ./shared/

# 4. Download Models
# We run the setup scripts for each agent to download their respective models into their data directories.
# Note: The setup scripts use relative paths, so we need to be careful about CWD.
# Current WORKDIR is /app.
# Agent A
RUN python AI_APP/agentA/setup.py
# Agent B
RUN python AI_APP/agentB/setup.py
# Agent C
RUN python AI_APP/agentC/setup.py

# 5. Default command (overridden by docker-compose)
CMD ["python", "AI_APP/agentA/init.py"]
