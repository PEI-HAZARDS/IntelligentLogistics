#!/bin/sh

set -e

echo "[Entrypoint] Starting MediaMTX StreamV2..."
echo "[Entrypoint] ===================================="

# ============================================
# 1. Start MediaMTX in background
# ============================================
echo "[Entrypoint] Starting MediaMTX..."
/mediamtx &
MTX_PID=$!

# Wait for MediaMTX API to be ready
echo "[Entrypoint] Waiting for MediaMTX to be ready..."
MAX_WAIT=15
WAITED=0
while ! wget -q -O /dev/null http://localhost:9997/v3/config/global/get 2>/dev/null; do
    sleep 1
    WAITED=$((WAITED + 1))
    if [ "$WAITED" -ge "$MAX_WAIT" ]; then
        echo "[Entrypoint] ERROR: MediaMTX did not start within ${MAX_WAIT}s"
        exit 1
    fi
done
echo "[Entrypoint] MediaMTX is ready (took ${WAITED}s)"

# ============================================
# 2. Start ingest AFTER MediaMTX is listening
# ============================================
STREAM_MODE="${STREAM_MODE:-camera}"
echo "[Entrypoint] ===================================="
echo "[Entrypoint] STREAM MODE: ${STREAM_MODE}"
echo "[Entrypoint] ===================================="

if [ "$STREAM_MODE" = "test" ]; then
    echo "[Entrypoint] Starting TEST VIDEO ingestion..."
    /usr/local/bin/ingest_test_video.sh &
else
    echo "[Entrypoint] Starting CAMERA (RTSP) ingestion..."
    /usr/local/bin/ingest_streams.sh &
fi
INGEST_PID=$!
echo "[Entrypoint] Ingest started (PID: $INGEST_PID)"

# ============================================
# 3. Cleanup handler + wait on MediaMTX
# ============================================
cleanup() {
    echo "[Entrypoint] Received signal, shutting down..."
    kill $INGEST_PID 2>/dev/null || true
    kill $MTX_PID 2>/dev/null || true
    wait $INGEST_PID 2>/dev/null || true
    wait $MTX_PID 2>/dev/null || true
    echo "[Entrypoint] Shutdown complete."
    exit 0
}

trap cleanup TERM INT

echo "[Entrypoint] ===================================="
echo "[Entrypoint] MediaMTX running (PID: $MTX_PID)"
echo "[Entrypoint]   RTMP:   rtmp://localhost:1935"
echo "[Entrypoint]   HLS:    http://localhost:8888"
echo "[Entrypoint]   WebRTC: http://localhost:8889"
echo "[Entrypoint]   API:    http://localhost:9997"
echo "[Entrypoint] ===================================="
wait $MTX_PID
