#!/bin/bash

set -e

echo "[Ingest Test] Starting TEST VIDEO stream ingestion..."
echo "[Ingest Test] =========================================="

# ============================================
# Configuração para Vídeo de Teste
# ============================================
CAMERA1_GATE_ID="${CAMERA1_GATE_ID:-gate1}"
CAMERA2_GATE_ID="${CAMERA2_GATE_ID:-gate2}"
TEST_VIDEO1_PATH="${TEST_VIDEO1_PATH:-/videos/test_video1.mp4}"
TEST_VIDEO2_PATH="${TEST_VIDEO2_PATH:-/videos/test_video2.mp4}"

# Fix Gate IDs to ensure 'gate' prefix
[[ ! $CAMERA1_GATE_ID =~ ^gate ]] && CAMERA1_GATE_ID="gate${CAMERA1_GATE_ID}"
[[ ! $CAMERA2_GATE_ID =~ ^gate ]] && CAMERA2_GATE_ID="gate${CAMERA2_GATE_ID}"

# URLs RTMP de destino (Nginx local)
RTMP1_LOW="rtmp://localhost/streams_low/${CAMERA1_GATE_ID}"
RTMP1_HIGH="rtmp://localhost/streams_high/${CAMERA1_GATE_ID}"
RTMP2_LOW="rtmp://localhost/streams_low/${CAMERA2_GATE_ID}"
RTMP2_HIGH="rtmp://localhost/streams_high/${CAMERA2_GATE_ID}"

echo "[Ingest Test] Configuration:"
echo "  Video 1: ${TEST_VIDEO1_PATH} -> Gate: ${CAMERA1_GATE_ID}"
echo "  Video 2: ${TEST_VIDEO2_PATH} -> Gate: ${CAMERA2_GATE_ID}"

# Verificar se os vídeos existem, caso contrário usar fallback para test_video.mp4
if [[ ! -f "${TEST_VIDEO1_PATH}" ]]; then
    echo "[Ingest Test] WARNING: Test video 1 not found at ${TEST_VIDEO1_PATH}. Checking for fallback..."
    if [[ -f "/videos/test_video.mp4" ]]; then
        TEST_VIDEO1_PATH="/videos/test_video.mp4"
        echo "[Ingest Test] ✓ Falling back to /videos/test_video.mp4 for CAM1"
    else
        echo "[Ingest Test] ERROR: No test video found for CAM1"
        exit 1
    fi
fi

if [[ ! -f "${TEST_VIDEO2_PATH}" ]]; then
    echo "[Ingest Test] WARNING: Test video 2 not found at ${TEST_VIDEO2_PATH}. Checking for fallback..."
    if [[ -f "/videos/test_video.mp4" ]]; then
        TEST_VIDEO2_PATH="/videos/test_video.mp4"
        echo "[Ingest Test] ✓ Falling back to /videos/test_video.mp4 for CAM2"
    else
        echo "[Ingest Test] ERROR: No test video found for CAM2"
        exit 1
    fi
fi

# ============================================
# Log directory for FFmpeg output
# ============================================
LOG_DIR="/tmp/ffmpeg-logs"
mkdir -p "${LOG_DIR}"

# ============================================
# Ingest functions — redirect to log files so $! tracks FFmpeg directly
# ============================================
start_test_low() {
    local video_path=$1
    local rtmp_url=$2
    local label=$3
    local log_file="${LOG_DIR}/ffmpeg-low-${label}.log"
    ffmpeg -stream_loop -1 -re \
           -i "${video_path}" \
           -an \
           -vf "scale=1280:720" \
           -c:v libx264 \
           -preset ultrafast \
           -tune zerolatency \
           -f flv "${rtmp_url}" \
           > "${log_file}" 2>&1 &
    echo $!
}

start_test_high() {
    local video_path=$1
    local rtmp_url=$2
    local label=$3
    local log_file="${LOG_DIR}/ffmpeg-high-${label}.log"
    ffmpeg -stream_loop -1 -re \
           -i "${video_path}" \
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
           > "${log_file}" 2>&1 &
    echo $!
}

# ============================================
# Start streams with staggered delays to avoid
# overwhelming NGINX with simultaneous publishes
# ============================================
echo "[Ingest Test] Starting CAM1 LOW..."
PID1_LOW=$(start_test_low "${TEST_VIDEO1_PATH}" "${RTMP1_LOW}" "CAM1")
sleep 2

echo "[Ingest Test] Starting CAM1 HIGH..."
PID1_HIGH=$(start_test_high "${TEST_VIDEO1_PATH}" "${RTMP1_HIGH}" "CAM1")
sleep 2

echo "[Ingest Test] Starting CAM2 LOW..."
PID2_LOW=$(start_test_low "${TEST_VIDEO2_PATH}" "${RTMP2_LOW}" "CAM2")
sleep 2

echo "[Ingest Test] Starting CAM2 HIGH..."
PID2_HIGH=$(start_test_high "${TEST_VIDEO2_PATH}" "${RTMP2_HIGH}" "CAM2")
sleep 2

# ============================================
# Trap for cleanup
# ============================================
cleanup() {
    echo "[Ingest Test] Received signal, stopping streams..."
    kill $PID1_LOW $PID1_HIGH $PID2_LOW $PID2_HIGH 2>/dev/null || true
    sleep 1
    echo "[Ingest Test] Streams stopped."
    exit 0
}

trap cleanup SIGTERM SIGINT

# ============================================
# Monitor processes (auto-restart with logging)
# ============================================
echo "[Ingest Test] All test streams started. PIDs: LOW1=$PID1_LOW HIGH1=$PID1_HIGH LOW2=$PID2_LOW HIGH2=$PID2_HIGH"
echo "[Ingest Test] Monitoring processes..."

while true; do
    # Monitor Cam 1
    if ! kill -0 $PID1_LOW 2>/dev/null; then
        echo "[Ingest Test] CAM1 LOW stream died (was PID $PID1_LOW), restarting..."
        PID1_LOW=$(start_test_low "${TEST_VIDEO1_PATH}" "${RTMP1_LOW}" "CAM1")
        echo "[Ingest Test] CAM1 LOW restarted (new PID $PID1_LOW)"
        sleep 1
    fi
    if ! kill -0 $PID1_HIGH 2>/dev/null; then
        echo "[Ingest Test] CAM1 HIGH stream died (was PID $PID1_HIGH), restarting..."
        PID1_HIGH=$(start_test_high "${TEST_VIDEO1_PATH}" "${RTMP1_HIGH}" "CAM1")
        echo "[Ingest Test] CAM1 HIGH restarted (new PID $PID1_HIGH)"
        sleep 1
    fi

    # Monitor Cam 2
    if ! kill -0 $PID2_LOW 2>/dev/null; then
        echo "[Ingest Test] CAM2 LOW stream died (was PID $PID2_LOW), restarting..."
        PID2_LOW=$(start_test_low "${TEST_VIDEO2_PATH}" "${RTMP2_LOW}" "CAM2")
        echo "[Ingest Test] CAM2 LOW restarted (new PID $PID2_LOW)"
        sleep 1
    fi
    if ! kill -0 $PID2_HIGH 2>/dev/null; then
        echo "[Ingest Test] CAM2 HIGH stream died (was PID $PID2_HIGH), restarting..."
        PID2_HIGH=$(start_test_high "${TEST_VIDEO2_PATH}" "${RTMP2_HIGH}" "CAM2")
        echo "[Ingest Test] CAM2 HIGH restarted (new PID $PID2_HIGH)"
        sleep 1
    fi
    
    sleep 10
done