#!/bin/bash

set -e

echo "[Ingest] Starting stream ingestion..."

# ============================================
# Configuração de Streams
# ============================================
# Camera 1 Defaults
CAMERA1_IP="${CAMERA1_IP:-10.255.35.86}"
CAMERA1_PORT="${CAMERA1_PORT:-554}"
CAMERA1_LOW_PATH="${CAMERA1_LOW_PATH:-stream2}"
CAMERA1_HIGH_PATH="${CAMERA1_HIGH_PATH:-stream1}"
CAMERA1_GATE_ID="${CAMERA1_GATE_ID:-gate1}"

# Camera 2 Defaults
CAMERA2_IP="${CAMERA2_IP:-10.255.35.87}"
CAMERA2_PORT="${CAMERA2_PORT:-554}"
CAMERA2_LOW_PATH="${CAMERA2_LOW_PATH:-stream2}"
CAMERA2_HIGH_PATH="${CAMERA2_HIGH_PATH:-stream1}"
CAMERA2_GATE_ID="${CAMERA2_GATE_ID:-gate2}"

# URLs RTSP
RTSP1_LOW="rtsp://${CAMERA1_IP}:${CAMERA1_PORT}/${CAMERA1_LOW_PATH}"
RTSP1_HIGH="rtsp://${CAMERA1_IP}:${CAMERA1_PORT}/${CAMERA1_HIGH_PATH}"
RTSP2_LOW="rtsp://${CAMERA2_IP}:${CAMERA2_PORT}/${CAMERA2_LOW_PATH}"
RTSP2_HIGH="rtsp://${CAMERA2_IP}:${CAMERA2_PORT}/${CAMERA2_HIGH_PATH}"

# Fix Gate IDs to ensure 'gate' prefix
[[ ! $CAMERA1_GATE_ID =~ ^gate ]] && CAMERA1_GATE_ID="gate${CAMERA1_GATE_ID}"
[[ ! $CAMERA2_GATE_ID =~ ^gate ]] && CAMERA2_GATE_ID="gate${CAMERA2_GATE_ID}"

# URLs RTMP de destino (Nginx local)
RTMP1_LOW="rtmp://localhost/live_low/${CAMERA1_GATE_ID}"
RTMP1_HIGH="rtmp://localhost/live_high/${CAMERA1_GATE_ID}"
RTMP2_LOW="rtmp://localhost/live_low/${CAMERA2_GATE_ID}"
RTMP2_HIGH="rtmp://localhost/live_high/${CAMERA2_GATE_ID}"

echo "[Ingest] Configuration:"
echo "  Camera 1: ${CAMERA1_IP} -> Gate: ${CAMERA1_GATE_ID}"
echo "  Camera 2: ${CAMERA2_IP} -> Gate: ${CAMERA2_GATE_ID}"

# ============================================
# Funções de Ingest
# ============================================
start_low() {
    local rtsp_url=$1
    local rtmp_url=$2
    local label=$3
    ffmpeg -rtsp_transport tcp \
           -i "${rtsp_url}" \
           -an \
           -c:v copy \
           -f flv "${rtmp_url}" \
           2>&1 | sed "s/^/[FFmpeg-LOW-${label}] /" &
    echo $!
}

start_high() {
    local rtsp_url=$1
    local rtmp_url=$2
    local label=$3
    # HEVC → H.264 transcoding, sem áudio
    ffmpeg -rtsp_transport tcp \
           -i "${rtsp_url}" \
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
           -f flv "${rtmp_url}" \
           2>&1 | sed "s/^/[FFmpeg-HIGH-${label}] /" &
    echo $!
}

# Iniciar Streams Cam 1
PID1_LOW=$(start_low "${RTSP1_LOW}" "${RTMP1_LOW}" "CAM1")
PID1_HIGH=$(start_high "${RTSP1_HIGH}" "${RTMP1_HIGH}" "CAM1")

# Iniciar Streams Cam 2
PID2_LOW=$(start_low "${RTSP2_LOW}" "${RTMP2_LOW}" "CAM2")
PID2_HIGH=$(start_high "${RTSP2_HIGH}" "${RTMP2_HIGH}" "CAM2")

# ============================================
# Trap para limpar processos ao sair
# ============================================
cleanup() {
    echo "[Ingest] Received signal, stopping streams..."
    kill $PID1_LOW $PID1_HIGH $PID2_LOW $PID2_HIGH 2>/dev/null || true
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
    # Monitor Cam 1
    if ! kill -0 $PID1_LOW 2>/dev/null; then
        echo "[Ingest] CAM1 LOW stream died, restarting..."
        PID1_LOW=$(start_low "${RTSP1_LOW}" "${RTMP1_LOW}" "CAM1")
    fi
    if ! kill -0 $PID1_HIGH 2>/dev/null; then
        echo "[Ingest] CAM1 HIGH stream died, restarting..."
        PID1_HIGH=$(start_high "${RTSP1_HIGH}" "${RTMP1_HIGH}" "CAM1")
    fi

    # Monitor Cam 2
    if ! kill -0 $PID2_LOW 2>/dev/null; then
        echo "[Ingest] CAM2 LOW stream died, restarting..."
        PID2_LOW=$(start_low "${RTSP2_LOW}" "${RTMP2_LOW}" "CAM2")
    fi
    if ! kill -0 $PID2_HIGH 2>/dev/null; then
        echo "[Ingest] CAM2 HIGH stream died, restarting..."
        PID2_HIGH=$(start_high "${RTSP2_HIGH}" "${RTMP2_HIGH}" "CAM2")
    fi
    
    sleep 10
done