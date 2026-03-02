FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install Python deps
COPY V_APP/infraction_engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (consistent with V_Brain)
ENV PYTHONPATH=/app
COPY V_APP/infraction_engine/ ./V_APP/infraction_engine/
COPY shared/ ./shared/
COPY V_APP/shared/ ./V_APP/shared/

# Use module-style execution for consistent imports
CMD ["python", "-m", "V_APP.infraction_engine.init"]
