FROM python:3.11-slim

ENV PYTHONPATH=/app:/app/AI_APP \
    MODELS_PATH=/app/AI_APP/agentA/data \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# System dependencies
# libgl1, libglib2.0-0: required by OpenCV
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY AI_APP/agentA/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Source code — only what agentA needs
COPY AI_APP/agentA/ ./AI_APP/agentA/
COPY AI_APP/shared/ ./AI_APP/shared/
COPY shared/ ./shared/

# Download model
RUN python AI_APP/agentA/setup.py

CMD ["python", "AI_APP/agentA/init.py"]
