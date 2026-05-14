FROM python:3.11-slim

ENV PYTHONPATH=/app \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Python dependencies
COPY AI_APP/gateway/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Source code — only what the gateway needs
COPY AI_APP/gateway/ ./AI_APP/gateway/
COPY shared/ ./shared/

CMD ["python", "-m", "AI_APP.gateway"]
