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

# Configurar player.html com os Gate IDs atuais
echo "[Entrypoint] Configuring player.html..."
PLAYER_HTML="/usr/local/nginx/html/player.html"
if [[ -f "$PLAYER_HTML" ]]; then
    # Ensure 'gate' prefix
    [[ ! $CAMERA1_GATE_ID =~ ^gate ]] && CAMERA1_GATE_ID="gate${CAMERA1_GATE_ID:-1}"
    [[ ! $CAMERA2_GATE_ID =~ ^gate ]] && CAMERA2_GATE_ID="gate${CAMERA2_GATE_ID:-2}"
    
    sed -i "s/{{CAMERA1_GATE_ID}}/${CAMERA1_GATE_ID}/g" "$PLAYER_HTML"
    sed -i "s/{{CAMERA2_GATE_ID}}/${CAMERA2_GATE_ID}/g" "$PLAYER_HTML"
    echo "[Entrypoint] ✓ player.html updated (Gate 1: $CAMERA1_GATE_ID, Gate 2: $CAMERA2_GATE_ID)"
else
    echo "[Entrypoint] ⚠ player.html not found at $PLAYER_HTML"
fi

# ============================================
# 1. Start Nginx FIRST (background) so RTMP port 1935 is available
# ============================================
echo "[Entrypoint] ===================================="
echo "[Entrypoint] Starting Nginx in background..."
echo "[Entrypoint] ===================================="
nginx -g 'daemon off;' &
NGINX_PID=$!

# Wait for Nginx RTMP to be ready (port 1935)
echo "[Entrypoint] Waiting for Nginx RTMP to be ready..."
MAX_WAIT=15
WAITED=0
while ! curl -sf http://localhost:8080/health > /dev/null 2>&1; do
    sleep 1
    WAITED=$((WAITED + 1))
    if [[ $WAITED -ge $MAX_WAIT ]]; then
        echo "[Entrypoint] ERROR: Nginx did not start within ${MAX_WAIT}s"
        exit 1
    fi
done
echo "[Entrypoint] ✓ Nginx is ready (took ${WAITED}s)"

# ============================================
# 2. Start ingest AFTER Nginx is listening
# ============================================
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

# ============================================
# 3. Cleanup handler + wait on Nginx
# ============================================
cleanup() {
    echo "[Entrypoint] Received signal, shutting down..."
    kill $INGEST_PID 2>/dev/null || true
    kill $NGINX_PID 2>/dev/null || true
    wait $INGEST_PID 2>/dev/null || true
    wait $NGINX_PID 2>/dev/null || true
    echo "[Entrypoint] Shutdown complete."
    exit 0
}

trap cleanup SIGTERM SIGINT

# Block on Nginx (replaces 'exec nginx')
echo "[Entrypoint] ===================================="
echo "[Entrypoint] Nginx running (PID: $NGINX_PID), waiting..."
echo "[Entrypoint] ===================================="
wait $NGINX_PID
