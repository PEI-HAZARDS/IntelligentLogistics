#!/bin/bash

set -e

echo "[Entrypoint] Starting Nginx RTMP Server..."
echo "[Entrypoint] ===================================="

# Testar configuração do Nginx ANTES de iniciar
echo "[Entrypoint] Testing Nginx configuration..."
if ! nginx -t 2>&1 | tee /tmp/nginx-test.log; then
    echo "[Entrypoint] ===================================="
    echo "[Entrypoint] ERROR: Nginx configuration test FAILED!"
    echo "[Entrypoint] ===================================="
    cat /tmp/nginx-test.log
    echo "[Entrypoint] ===================================="
    echo "[Entrypoint] Showing nginx.conf:"
    cat /etc/nginx/nginx.conf
    exit 1
fi

echo "[Entrypoint] ✓ Nginx configuration is valid"
echo "[Entrypoint] ===================================="

# Criar diretórios necessários
echo "[Entrypoint] Creating directories..."
mkdir -p /tmp/hls/low /tmp/hls/high /tmp/dash/low /tmp/dash/high
chmod -R 777 /tmp/hls /tmp/dash
echo "[Entrypoint] ✓ Directories created"

# Escolher script de ingest baseado em STREAM_MODE
STREAM_MODE="${STREAM_MODE:-camera}"
echo "[Entrypoint] ===================================="
echo "[Entrypoint] STREAM MODE: ${STREAM_MODE}"
echo "[Entrypoint] ===================================="

if [[ "$STREAM_MODE" = "test" ]]; then
    echo "[Entrypoint] Starting TEST VIDEO ingestion..."
    /usr/local/bin/ingest_test_video.sh &
else
    echo "[Entrypoint] Starting CAMERA (RTSP) ingestion..."
    /usr/local/bin/ingest_streams.sh &
fi
INGEST_PID=$!
echo "[Entrypoint] ✓ Ingest started (PID: $INGEST_PID)"

# Aguardar 2 segundos para ingest começar
sleep 2

# Iniciar Nginx em FOREGROUND (não retorna)
echo "[Entrypoint] ===================================="
echo "[Entrypoint] Starting Nginx in foreground..."
echo "[Entrypoint] Nginx will handle all signals"
echo "[Entrypoint] ===================================="

# Cleanup handler
cleanup() {
    echo "[Entrypoint] Received signal, shutting down..."
    kill $INGEST_PID 2>/dev/null || true
    wait $INGEST_PID 2>/dev/null || true
    echo "[Entrypoint] Shutdown complete."
    exit 0
}

trap cleanup SIGTERM SIGINT

# Iniciar Nginx em foreground (bloqueia aqui)
exec nginx -g 'daemon off;'
