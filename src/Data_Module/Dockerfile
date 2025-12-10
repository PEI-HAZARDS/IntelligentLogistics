FROM python:3.11-slim

WORKDIR /app

# Instalar dependências OS (PostgreSQL, netcat para aguardar serviços)
RUN apt-get update && apt-get install -y \
    gcc libpq-dev netcat-openbsd curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Tornar entrypoint executável
RUN chmod +x /app/entrypoint.sh

# Usar entrypoint para executar data_init antes do servidor
ENTRYPOINT ["/app/entrypoint.sh"]

# Adiciona healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
