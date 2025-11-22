# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Variáveis de ambiente (podem ser sobrescritas no docker run/compose)
ENV PYTHONPATH=/app \
    KAFKA_BOOTSTRAP=10.255.32.143:9092 \
    MODELS_PATH=/app/agentB_microservice/data

WORKDIR /app

# 1. System dependencies (OpenCV, etc.) – cache quase eterno
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

# 2. Python dependencies – muda só quando requirements.txt mudar
COPY src/agentB_microservice/requirements.txt ./agentB_microservice/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r agentB_microservice/requirements.txt

# 3. Copiar TODO o código ANTES de qualquer RUN pesado
COPY src/shared_utils ./shared_utils/
COPY src/agentB_microservice ./agentB_microservice/

# 4. Download do modelo (só acontece na primeira build de sempre)
#     Depois desta linha, toda a gente reutiliza o cache para sempre
RUN python -c "from agentB_microservice.setup import setup; setup()" && \
    echo "Modelos prontos em $MODELS_PATH"

# 5. Comando de arranque
CMD ["python", "agentB_microservice/init.py"]