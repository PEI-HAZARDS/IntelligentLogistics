FROM tiangolo/nginx-rtmp:latest

# Instalar FFmpeg para ingest de streams RTSP + ferramentas de debug
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    vim \
    net-tools \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Copiar configuração customizada do Nginx
COPY nginx.conf /etc/nginx/nginx.conf

# Criar diretórios para HLS e DASH ANTES de testar nginx
RUN mkdir -p /tmp/hls/low /tmp/hls/high /tmp/dash/low /tmp/dash/high

# Testar configuração durante build (fail-fast)
RUN nginx -t || (echo "=== nginx.conf has errors ==="; cat /etc/nginx/nginx.conf; exit 1)

# Copiar scripts
COPY entrypoint.sh /entrypoint.sh
COPY ingest_streams.sh /usr/local/bin/ingest_streams.sh
COPY ingest_test_video.sh /usr/local/bin/ingest_test_video.sh

# Copiar HTML player para Nginx
COPY test_nginx_hls.html /usr/local/nginx/html/player.html

# Dar permissões
RUN chmod +x /entrypoint.sh /usr/local/bin/ingest_streams.sh /usr/local/bin/ingest_test_video.sh

# Expor portas
EXPOSE 1935 8080

# Health check (dar mais tempo para Nginx iniciar)
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Script de entrypoint customizado
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]