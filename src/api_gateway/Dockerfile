# Imagem base leve com Python 3.11
FROM python:3.11-slim

# Evitar criação de ficheiros .pyc e forçar logs a sair diretamente
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Diretório de trabalho dentro do container
WORKDIR /app

# Instalar dependências do sistema (se precisares de mais no futuro, adiciona aqui)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements do API Gateway
COPY requirements.txt .

# Instalar dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar o código do API Gateway para dentro do container
COPY . .

# Porta exposta pelo API Gateway
EXPOSE 8000

# NÃO definimos DATA_MODULE_URL/STREAM_BASE_URL aqui para não forçar localhost.
# Esses valores vêm:
#   - dos defaults no config.py (data-module / nginx-rtmp)
#   - ou de variáveis de ambiente passadas pelo docker compose / orquestrador.

# Comando para arrancar o FastAPI com Uvicorn
# Nota: "api_gateway.main:app" corresponde ao módulo/pacote + objeto FastAPI
CMD ["uvicorn", "api_gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
