FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py .
COPY templates/ templates/
COPY static/ static/

# Environment variables
ENV KAFKA_BOOTSTRAP=kafka:29092 \
    GATE_ID=1

EXPOSE 8091

CMD ["python", "app.py"]
