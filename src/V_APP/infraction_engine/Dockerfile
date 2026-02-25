FROM python:3.11-slim

WORKDIR /infraction_engine

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install Python deps
COPY V_APP/infraction_engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
ENV PYTHONPATH=/infraction_engine
COPY V_APP/infraction_engine/src/ ./src/
COPY shared/ ./shared/
COPY V_APP/infraction_engine/init.py ./
COPY V_APP/infraction_engine/data ./data
COPY V_APP/shared ./V_APP/shared

CMD ["python", "init.py"]
