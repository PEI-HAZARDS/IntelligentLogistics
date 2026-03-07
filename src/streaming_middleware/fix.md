# Streaming Middleware — IP Camera Migration Fix

## Problem

After switching from test videos (inside the VM) to real IP cameras via RTSP, only **Gate 1 LOW** was working. The remaining three streams (Gate 1 HIGH, Gate 2 LOW, Gate 2 HIGH) were either failing silently or crashing intermittently.

## Root Causes

### 1. Broken PID Tracking (affected all streams)

The [start_low()](file:///home/tsh19/Universidade/3%C2%BAano/PEI/IntelligentLogistics/src/streaming_middleware/ingest_streams.sh#63-82) and [start_high()](file:///home/tsh19/Universidade/3%C2%BAano/PEI/IntelligentLogistics/src/streaming_middleware/ingest_streams.sh#83-105) functions piped FFmpeg output through `sed` for labeling:

```bash
ffmpeg ... 2>&1 | sed "s/^/[FFmpeg-LOW-${label}] /" &
echo $!
```

**`$!` captures the PID of `sed`, not FFmpeg.** The monitoring loop was checking if `sed` was alive — not the actual FFmpeg process — so dead streams were never detected or restarted.

**Fix:** Redirect FFmpeg output to log files instead of piping through `sed`:

```diff
-ffmpeg ... 2>&1 | sed "s/^/[FFmpeg-LOW-${label}] /" &
+ffmpeg ... > "${log_file}" 2>&1 &
```

---

### 2. HEVC Codec Incompatibility (Gate 2 LOW)

Camera 2's low stream outputs **HEVC (H.265)**, but the [start_low()](file:///home/tsh19/Universidade/3%C2%BAano/PEI/IntelligentLogistics/src/streaming_middleware/ingest_streams.sh#63-82) function used `-c:v copy` (passthrough). The FLV/RTMP container **does not support HEVC** — only H.264.

FFmpeg error:
```
[flv] Video codec hevc not compatible with flv
Could not write header for output file #0
```

**Fix:** Transcode to H.264 in [start_low()](file:///home/tsh19/Universidade/3%C2%BAano/PEI/IntelligentLogistics/src/streaming_middleware/ingest_streams.sh#63-82), matching the approach already used in [start_high()](file:///home/tsh19/Universidade/3%C2%BAano/PEI/IntelligentLogistics/src/streaming_middleware/ingest_streams.sh#83-105):

```diff
-ffmpeg ... -c:v copy -f flv ...
+ffmpeg ... -c:v libx264 -preset ultrafast -tune zerolatency -crf 28 -f flv ...
```

---

### 3. `set -e` Killing the Monitoring Loop (Gate 2 HIGH crash)

The script had `set -e` at the top. When any FFmpeg process crashed (e.g., RTSP connection drop), the monitoring/restart logic could exit the entire script, preventing auto-recovery.

**Fix:** Removed `set -e` — a long-running monitoring script must tolerate individual process failures.

---

### 4. No RTSP Resilience Flags (all camera streams)

Unlike test videos (local files), IP cameras can drop RTSP connections due to network issues, camera reboots, or connection limits. The original script had no timeout or reconnection handling.

**Fix:** Added RTSP-specific FFmpeg input flags:

```bash
-rtsp_transport tcp -stimeout 10000000 -rtsp_flags prefer_tcp
```

- `-stimeout 10000000` → 10-second connection timeout (prevents indefinite hangs)
- `-rtsp_flags prefer_tcp` → prefer TCP for RTP transport (more reliable)

---

### 5. No Startup Stagger (race condition)

All 4 FFmpeg processes were launched simultaneously. IP cameras often can't handle multiple concurrent RTSP session setups, causing connection failures.

**Fix:** Added 3-second delays between starting each stream, plus a 5-second cooldown before restarting dead streams in the monitoring loop.

## Changed File

- [ingest_streams.sh](file:///home/tsh19/Universidade/3ºano/PEI/IntelligentLogistics/src/streaming_middleware/ingest_streams.sh)

render_diffs(file:///home/tsh19/Universidade/3ºano/PEI/IntelligentLogistics/src/streaming_middleware/ingest_streams.sh)
