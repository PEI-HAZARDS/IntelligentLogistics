# --- 1. Base Stage (Common OS Deps & Python Packages) ---
FROM python:3.11-slim as base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install common system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    netcat-openbsd \
    postgresql-client \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install unified requirements
COPY V_APP/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- 2. Data Module Stage ---
FROM base as data_module
WORKDIR /app
ENV PYTHONPATH=/app
COPY V_APP/Data_Module/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh
COPY V_APP/Data_Module/ .
COPY shared/ ./shared/
ENTRYPOINT ["/app/entrypoint.sh"]
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# --- 3. API Gateway Stage ---
FROM base as api_gateway
WORKDIR /app
ENV PYTHONPATH=/app
COPY V_APP/api_gateway/src/ .
COPY shared/ ./shared/
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# --- 4. Decision Engine Stage ---
FROM base as decision_engine
WORKDIR /decision_engine
ENV PYTHONPATH=/decision_engine
# Copy source code relative to build context (src root)
COPY V_APP/decision_engine/src/ ./src/
COPY shared/ ./shared/
COPY V_APP/decision_engine/init.py ./
COPY V_APP/decision_engine/tests/ ./tests/
CMD ["python", "init.py"]

# --- 5. V_Gateway Stage ---
FROM base as v_gateway
WORKDIR /app
ENV PYTHONPATH=/app
COPY V_APP/gateway/ ./V_APP/gateway/
COPY shared/ ./shared/
CMD ["python", "-m", "V_APP.gateway"]
