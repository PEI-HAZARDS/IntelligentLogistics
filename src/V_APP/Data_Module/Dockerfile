FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# System deps: libpq for psycopg2, pg-client for entrypoint health checks,
# curl for Docker healthcheck, netcat for entrypoint wait loops
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    netcat-openbsd \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY V_APP/Data_Module/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
ENV PYTHONPATH=/app
COPY V_APP/Data_Module/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh
COPY V_APP/Data_Module/ .
COPY shared/ ./shared/

ENTRYPOINT ["/app/entrypoint.sh"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1
