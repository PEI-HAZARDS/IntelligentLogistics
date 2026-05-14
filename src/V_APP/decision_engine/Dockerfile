FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install Python deps
COPY V_APP/decision_engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (consistent with V_Brain)
ENV PYTHONPATH=/app
COPY V_APP/decision_engine/ ./V_APP/decision_engine/
COPY shared/ ./shared/
COPY V_APP/shared/ ./V_APP/shared/

RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Use module-style execution for consistent imports
CMD ["python", "-m", "V_APP.decision_engine.init"]
