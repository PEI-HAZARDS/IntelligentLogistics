#!/bin/bash

# NOTE: Do NOT use 'set -e' here — this is a long-running monitoring script
# and individual FFmpeg failures must NOT kill the entire process.

echo "[Ingest] Starting stream ingestion..."

# ============================================
# Stream Configuration
# ============================================
# Camera 1
CAMERA1_IP="${CAMERA1_IP:-10.255.35.86}"
CAMERA1_PORT="${CAMERA1_PORT:-554}"
CAMERA1_LOW_PATH="${CAMERA1_LOW_PATH:-stream2}"
CAMERA1_HIGH_PATH="${CAMERA1_HIGH_PATH:-stream1}"
CAMERA1_GATE_ID="${CAMERA1_GATE_ID:-gate1}"

# Camera 2
CAMERA2_IP="${CAMERA2_IP:-10.255.35.97}"
CAMERA2_PORT="${CAMERA2_PORT:-554}"
CAMERA2_LOW_PATH="${CAMERA2_LOW_PATH:-stream2}"
CAMERA2_HIGH_PATH="${CAMERA2_HIGH_PATH:-stream1}"
CAMERA2_GATE_ID="${CAMERA2_GATE_ID:-gate2}"

# RTSP source URLs
RTSP1_LOW="rtsp://${CAMERA1_IP}:${CAMERA1_PORT}/${CAMERA1_LOW_PATH}"
RTSP1_HIGH="rtsp://${CAMERA1_IP}:${CAMERA1_PORT}/${CAMERA1_HIGH_PATH}"
RTSP2_LOW="rtsp://${CAMERA2_IP}:${CAMERA2_PORT}/${CAMERA2_LOW_PATH}"
RTSP2_HIGH="rtsp://${CAMERA2_IP}:${CAMERA2_PORT}/${CAMERA2_HIGH_PATH}"

# Fix Gate IDs to ensure 'gate' prefix
[[ ! $CAMERA1_GATE_ID =~ ^gate ]] && CAMERA1_GATE_ID="gate${CAMERA1_GATE_ID}"
[[ ! $CAMERA2_GATE_ID =~ ^gate ]] && CAMERA2_GATE_ID="gate${CAMERA2_GATE_ID}"

# RTMP destination URLs (local Nginx)
RTMP1_LOW="rtmp://localhost/streams_low/${CAMERA1_GATE_ID}"
RTMP1_HIGH="rtmp://localhost/streams_high/${CAMERA1_GATE_ID}"
RTMP2_LOW="rtmp://localhost/streams_low/${CAMERA2_GATE_ID}"
RTMP2_HIGH="rtmp://localhost/streams_high/${CAMERA2_GATE_ID}"

echo "[Ingest] Configuration:"
echo "  Camera 1: ${CAMERA1_IP} -> Gate: ${CAMERA1_GATE_ID}"
echo "  Camera 2: ${CAMERA2_IP} -> Gate: ${CAMERA2_GATE_ID}"

# ============================================
# Log directory
# ============================================
LOG_DIR="/tmp/ffmpeg-logs"
mkdir -p "${LOG_DIR}"

# ============================================
# Common RTSP input flags for IP cameras:
#   - tcp transport (more reliable than udp)
#   - stimeout: connection timeout in microseconds (10s)
#   - rtsp_flags prefer_tcp: prefer TCP for RTP
#   - fflags +genpts: generate timestamps if missing
# ============================================
RTSP_INPUT_FLAGS="-rtsp_transport tcp -timeout 10000000"

# ============================================
# Ingest Functions
# ============================================
start_low() {
    local rtsp_url=$1
    local rtmp_url=$2
    local label=$3
    local log_file="${LOG_DIR}/ffmpeg-low-${label}.log"
    # Transcode to H.264 — needed because some cameras output HEVC
    # which is not compatible with FLV/RTMP containers
    ffmpeg ${RTSP_INPUT_FLAGS} \
           -i "${rtsp_url}" \
           -an \
           -c:v libx264 \
           -preset ultrafast \
           -tune zerolatency \
           -crf 28 \
           -pix_fmt yuv420p \
           -f flv "${rtmp_url}" \
           > "${log_file}" 2>&1 &
    echo $!
}

start_high() {
    local rtsp_url=$1
    local rtmp_url=$2
    local label=$3
    local log_file="${LOG_DIR}/ffmpeg-high-${label}.log"
    # HEVC → H.264 transcoding, no audio
    ffmpeg ${RTSP_INPUT_FLAGS} \
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
           > "${log_file}" 2>&1 &
    echo $!
}

# ============================================
# Start streams with staggered delays to avoid
# overwhelming cameras with simultaneous RTSP connections
# ============================================
echo "[Ingest] Starting CAM1 LOW..."
PID1_LOW=$(start_low "${RTSP1_LOW}" "${RTMP1_LOW}" "CAM1")
echo "[Ingest] ✓ CAM1 LOW started (PID: $PID1_LOW)"
sleep 3

echo "[Ingest] Starting CAM1 HIGH..."
PID1_HIGH=$(start_high "${RTSP1_HIGH}" "${RTMP1_HIGH}" "CAM1")
echo "[Ingest] ✓ CAM1 HIGH started (PID: $PID1_HIGH)"
sleep 3

echo "[Ingest] Starting CAM2 LOW..."
PID2_LOW=$(start_low "${RTSP2_LOW}" "${RTMP2_LOW}" "CAM2")
echo "[Ingest] ✓ CAM2 LOW started (PID: $PID2_LOW)"
sleep 3

echo "[Ingest] Starting CAM2 HIGH..."
PID2_HIGH=$(start_high "${RTSP2_HIGH}" "${RTMP2_HIGH}" "CAM2")
echo "[Ingest] ✓ CAM2 HIGH started (PID: $PID2_HIGH)"
sleep 3

# ============================================
# Cleanup handler
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
# Monitoring loop with restart cooldown
# ============================================
RESTART_DELAY=5  # seconds to wait before restarting a dead stream

echo "[Ingest] All streams started. Monitoring processes..."
echo "[Ingest] PIDs: LOW1=$PID1_LOW HIGH1=$PID1_HIGH LOW2=$PID2_LOW HIGH2=$PID2_HIGH"

while true; do
    # --- Monitor Cam 1 ---
    if ! kill -0 $PID1_LOW 2>/dev/null; then
        echo "[Ingest] $(date '+%H:%M:%S') CAM1 LOW died (was PID $PID1_LOW), restarting in ${RESTART_DELAY}s..."
        sleep $RESTART_DELAY
        PID1_LOW=$(start_low "${RTSP1_LOW}" "${RTMP1_LOW}" "CAM1")
        echo "[Ingest] ✓ CAM1 LOW restarted (new PID $PID1_LOW)"
        sleep 2
    fi

    if ! kill -0 $PID1_HIGH 2>/dev/null; then
        echo "[Ingest] $(date '+%H:%M:%S') CAM1 HIGH died (was PID $PID1_HIGH), restarting in ${RESTART_DELAY}s..."
        sleep $RESTART_DELAY
        PID1_HIGH=$(start_high "${RTSP1_HIGH}" "${RTMP1_HIGH}" "CAM1")
        echo "[Ingest] ✓ CAM1 HIGH restarted (new PID $PID1_HIGH)"
        sleep 2
    fi

    # --- Monitor Cam 2 ---
    if ! kill -0 $PID2_LOW 2>/dev/null; then
        echo "[Ingest] $(date '+%H:%M:%S') CAM2 LOW died (was PID $PID2_LOW), restarting in ${RESTART_DELAY}s..."
        sleep $RESTART_DELAY
        PID2_LOW=$(start_low "${RTSP2_LOW}" "${RTMP2_LOW}" "CAM2")
        echo "[Ingest] ✓ CAM2 LOW restarted (new PID $PID2_LOW)"
        sleep 2
    fi

    if ! kill -0 $PID2_HIGH 2>/dev/null; then
        echo "[Ingest] $(date '+%H:%M:%S') CAM2 HIGH died (was PID $PID2_HIGH), restarting in ${RESTART_DELAY}s..."
        sleep $RESTART_DELAY
        PID2_HIGH=$(start_high "${RTSP2_HIGH}" "${RTMP2_HIGH}" "CAM2")
        echo "[Ingest] ✓ CAM2 HIGH restarted (new PID $PID2_HIGH)"
        sleep 2
    fi

    sleep 10
done