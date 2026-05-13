FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# curl for potential healthcheck use
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY V_APP/v_brain/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
ENV PYTHONPATH=/app
COPY V_APP/v_brain/ ./V_APP/v_brain/
COPY shared/ ./shared/
COPY V_APP/shared/ ./V_APP/shared/

RUN useradd -m appuser && chown -R appuser /app
USER appuser

CMD ["python", "-m", "V_APP.v_brain"]
