#!/bin/bash

set -e

echo "[Ingest Test] Starting TEST VIDEO stream ingestion..."
echo "[Ingest Test] =========================================="

# ============================================
# Configuração para Vídeo de Teste
# ============================================
GATE_ID="${GATE_ID:-gate1}"
TEST_VIDEO_PATH="${TEST_VIDEO_PATH:-/videos/test_video.mp4}"

# URLs RTMP de destino (Nginx local)
RTMP_URL_LOW="rtmp://localhost/live_low/${GATE_ID}"
RTMP_URL_HIGH="rtmp://localhost/live_high/${GATE_ID}"

echo "[Ingest Test] Configuration:"
echo "  Gate ID: ${GATE_ID}"
echo "  Test Video: ${TEST_VIDEO_PATH}"
echo "  RTMP LOW: ${RTMP_URL_LOW}"
echo "  RTMP HIGH: ${RTMP_URL_HIGH}"

# Verificar se o vídeo existe
if [ ! -f "${TEST_VIDEO_PATH}" ]; then
    echo "[Ingest Test] ERROR: Test video not found at ${TEST_VIDEO_PATH}"
    echo "[Ingest Test] Make sure to mount the video file in the container."
    exit 1
fi

echo "[Ingest Test] ✓ Test video found: ${TEST_VIDEO_PATH}"

# ============================================
# Stream LOW (720p) - Loop do vídeo de teste
# ============================================
echo "[Ingest Test] Starting LOW stream from test video..."
ffmpeg -stream_loop -1 -re \
       -i "${TEST_VIDEO_PATH}" \
       -an \
       -vf "scale=1280:720" \
       -c:v libx264 \
       -preset ultrafast \
       -tune zerolatency \
       -f flv "${RTMP_URL_LOW}" \
       2>&1 | sed 's/^/[FFmpeg-LOW] /' &

LOW_PID=$!
echo "[Ingest Test] LOW stream started (PID: $LOW_PID)"

# Aguardar 2s para garantir que LOW está estável
sleep 2

# ============================================
# Stream HIGH (1080p) - Loop do vídeo de teste
# ============================================
echo "[Ingest Test] Starting HIGH stream from test video..."
ffmpeg -stream_loop -1 -re \
       -i "${TEST_VIDEO_PATH}" \
       -an \
       -c:v libx264 \
       -preset ultrafast \
       -tune zerolatency \
       -crf 23 \
       -maxrate 20M \
       -bufsize 40M \
       -pix_fmt yuv420p \
       -g 30 \
       -keyint_min 30 \
       -f flv "${RTMP_URL_HIGH}" \
       2>&1 | sed 's/^/[FFmpeg-HIGH] /' &

HIGH_PID=$!
echo "[Ingest Test] HIGH stream started (PID: $HIGH_PID)"

# ============================================
# Trap para limpar processos ao sair
# ============================================
cleanup() {
    echo "[Ingest Test] Received signal, stopping streams..."
    kill $LOW_PID $HIGH_PID 2>/dev/null || true
    sleep 1
    echo "[Ingest Test] Streams stopped."
    exit 0
}

trap cleanup SIGTERM SIGINT

# ============================================
# Monitor de processos (restart automático)
# ============================================
echo "[Ingest Test] All test streams running. Monitoring processes..."

while true; do
    # Verificar se LOW está rodando
    if ! kill -0 $LOW_PID 2>/dev/null; then
        echo "[Ingest Test] LOW stream died, restarting..."
        ffmpeg -stream_loop -1 -re \
               -i "${TEST_VIDEO_PATH}" \
               -an \
               -vf "scale=1280:720" \
               -c:v libx264 \
               -preset ultrafast \
               -tune zerolatency \
               -f flv "${RTMP_URL_LOW}" \
               2>&1 | sed 's/^/[FFmpeg-LOW] /' &
        LOW_PID=$!
        echo "[Ingest Test] LOW stream restarted (PID: $LOW_PID)"
    fi
    
    # Verificar se HIGH está rodando
    if ! kill -0 $HIGH_PID 2>/dev/null; then
        echo "[Ingest Test] HIGH stream died, restarting..."
        ffmpeg -stream_loop -1 -re \
               -i "${TEST_VIDEO_PATH}" \
               -an \
               -c:v libx264 \
               -preset ultrafast \
               -tune zerolatency \
               -crf 23 \
               -maxrate 20M \
               -bufsize 40M \
               -pix_fmt yuv420p \
               -g 30 \
               -keyint_min 30 \
               -f flv "${RTMP_URL_HIGH}" \
               2>&1 | sed 's/^/[FFmpeg-HIGH] /' &
        HIGH_PID=$!
        echo "[Ingest Test] HIGH stream restarted (PID: $HIGH_PID)"
    fi
    
    sleep 10  # Verificar a cada 10 segundos
done
