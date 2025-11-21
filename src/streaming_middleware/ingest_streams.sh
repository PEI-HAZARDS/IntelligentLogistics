#!/bin/bash

set -e

echo "[Ingest] Starting stream ingestion..."

# ============================================
# Configuração de Streams
# ============================================
CAMERA_IP="${CAMERA_IP:-10.255.35.86}"
RTSP_PORT="${RTSP_PORT:-554}"
STREAM_LOW_PATH="${STREAM_LOW_PATH:-stream2}"    # 720p
STREAM_HIGH_PATH="${STREAM_HIGH_PATH:-stream1}"  # 4K
GATE_ID="${GATE_ID:-gate01}"

# URLs RTSP das câmaras
RTSP_URL_LOW="rtsp://${CAMERA_IP}:${RTSP_PORT}/${STREAM_LOW_PATH}"
RTSP_URL_HIGH="rtsp://${CAMERA_IP}:${RTSP_PORT}/${STREAM_HIGH_PATH}"

# URLs RTMP de destino (Nginx local)
RTMP_URL_LOW="rtmp://localhost/live_low/${GATE_ID}"
RTMP_URL_HIGH="rtmp://localhost/live_high/${GATE_ID}"

echo "[Ingest] Configuration:"
echo "  Camera IP: ${CAMERA_IP}"
echo "  Gate ID: ${GATE_ID}"
echo "  RTSP LOW: ${RTSP_URL_LOW}"
echo "  RTSP HIGH: ${RTSP_URL_HIGH}"

# ============================================
# Stream LOW (720p) - Always-on
# Codec: H.264 (copy direto, sem transcoding)
# ============================================
echo "[Ingest] Starting LOW stream (720p)..."
ffmpeg -rtsp_transport tcp \
       -i "${RTSP_URL_LOW}" \
       -c:v copy \
       -c:a aac -b:a 128k \
       -f flv "${RTMP_URL_LOW}" \
       2>&1 | sed 's/^/[FFmpeg-LOW] /' &

LOW_PID=$!
echo "[Ingest] LOW stream started (PID: $LOW_PID)"

# Aguardar 2s para garantir que LOW está estável
sleep 2

# ============================================
# Stream HIGH (4K) - Always-on
# Codec: HEVC → H.264 (TRANSCODE obrigatório!)
# Nota: FLV/RTMP não suporta HEVC, precisa converter
# ============================================
echo "[Ingest] Starting HIGH stream (4K - HEVC→H.264 transcoding)..."
ffmpeg -rtsp_transport tcp \
       -i "${RTSP_URL_HIGH}" \
       -c:v libx264 \
       -preset ultrafast \
       -tune zerolatency \
       -crf 23 \
       -maxrate 20M \
       -bufsize 40M \
       -pix_fmt yuv420p \
       -c:a aac -b:a 192k \
       -f flv "${RTMP_URL_HIGH}" \
       2>&1 | sed 's/^/[FFmpeg-HIGH] /' &

HIGH_PID=$!
echo "[Ingest] HIGH stream started (PID: $HIGH_PID)"

# ============================================
# Trap para limpar processos ao sair
# ============================================
cleanup() {
    echo "[Ingest] Received signal, stopping streams..."
    kill $LOW_PID $HIGH_PID 2>/dev/null || true
    sleep 1
    echo "[Ingest] Streams stopped."
    exit 0
}

trap cleanup SIGTERM SIGINT

# ============================================
# Monitor de processos (restart automático)
# ============================================
echo "[Ingest] All streams running. Monitoring processes..."

while true; do
    # Verificar se LOW está rodando
    if ! kill -0 $LOW_PID 2>/dev/null; then
        echo "[Ingest] LOW stream died, restarting..."
        ffmpeg -rtsp_transport tcp \
               -i "${RTSP_URL_LOW}" \
               -c:v copy \
               -c:a aac -b:a 128k \
               -f flv "${RTMP_URL_LOW}" \
               2>&1 | sed 's/^/[FFmpeg-LOW] /' &
        LOW_PID=$!
        echo "[Ingest] LOW stream restarted (PID: $LOW_PID)"
    fi
    
    # Verificar se HIGH está rodando
    if ! kill -0 $HIGH_PID 2>/dev/null; then
        echo "[Ingest] HIGH stream died, restarting..."
        ffmpeg -rtsp_transport tcp \
               -i "${RTSP_URL_HIGH}" \
               -c:v libx264 \
               -preset ultrafast \
               -tune zerolatency \
               -crf 23 \
               -maxrate 20M \
               -bufsize 40M \
               -pix_fmt yuv420p \
               -c:a aac -b:a 192k \
               -f flv "${RTMP_URL_HIGH}" \
               2>&1 | sed 's/^/[FFmpeg-HIGH] /' &
        HIGH_PID=$!
        echo "[Ingest] HIGH stream restarted (PID: $HIGH_PID)"
    fi
    
    sleep 10  # Verificar a cada 10 segundos
done