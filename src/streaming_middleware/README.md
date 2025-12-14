# Streaming Middleware - NGINX RTMP Server (10.255.32.35)

The **Streaming Middleware** is the video distribution infrastructure for the hazardous vehicle detection pipeline. It ingests RTSP streams from IP cameras, converts them to RTMP, and redistributes to multiple consumers (Agents and Frontend) without overloading the camera.

---

## Table of Contents

- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [Available Endpoints](#available-endpoints)
- [Running with Docker](#running-with-docker)
- [Environment Variables](#environment-variables)
- [Testing](#testing)
- [Debugging](#debugging)
- [Performance](#performance)

---

## How It Works

### Operation Cycle

1. **RTSP Ingestion**: FFmpeg processes inside the container connect to IP cameras via RTSP and pull video streams.

2. **Protocol Conversion**: RTSP streams are converted to RTMP format using FFmpeg with codec copy (no transcoding).

3. **RTMP Publishing**: Converted streams are published to the local NGINX RTMP server.

4. **Multi-Consumer Distribution**: NGINX redistributes streams to multiple consumers:
   - **RTMP**: For AgentA, AgentB, AgentC (low latency)
   - **HLS**: For Frontend web players (HTTP-based)

5. **Always-On Streams**: Both 720p (LOW) and 4K (HIGH) streams are continuously ingested and available.

### Stream Quality Levels

| Quality | Resolution | Use Case | Latency |
|---------|------------|----------|---------|
| LOW | 720p | AgentA continuous monitoring | ~500ms-1s |
| HIGH | 4K | AgentB/AgentC detailed analysis | ~500ms-1s |
| HLS LOW | 720p | Frontend web player | ~4-6s |
| HLS HIGH | 4K | Frontend web player | ~4-6s |

---

## Architecture

```
IP Camera (RTSP)
    │
    ├─ rtsp://10.255.35.86:554/stream2 (720p)
    └─ rtsp://10.255.35.86:554/stream1 (4K)
    │
    ▼
FFmpeg Ingest (inside container)
    │
    ├─ Converts RTSP → RTMP
    └─ Publishes to local NGINX
    │
    ▼
NGINX RTMP Server
    │
    ├─ rtmp://nginx-rtmp/streams_low/gate01  (for Agents)
    ├─ rtmp://nginx-rtmp/streams_high/gate01 (for Agents)
    ├─ http://nginx-rtmp:8080/hls/low/gate01.m3u8  (for Frontend)
    └─ http://nginx-rtmp:8080/hls/high/gate01.m3u8 (for Frontend)
```

---

## Available Endpoints

### RTMP (For Agents - Low Latency)

| Endpoint | Description |
|----------|-------------|
| `rtmp://nginx-rtmp:1935/streams_low/gate01` | 720p stream for AgentA |
| `rtmp://nginx-rtmp:1935/streams_high/gate01` | 4K stream for AgentB/AgentC |

### HTTP (For Frontend - Web Compatible)

| Endpoint | Description |
|----------|-------------|
| `http://nginx-rtmp:8080/hls/low/gate01.m3u8` | HLS 720p stream |
| `http://nginx-rtmp:8080/hls/high/gate01.m3u8` | HLS 4K stream |
| `http://nginx-rtmp:8080/dash/low/gate01.mpd` | DASH 720p (optional) |
| `http://nginx-rtmp:8080/stat` | RTMP statistics page |
| `http://nginx-rtmp:8080/health` | Health check endpoint |

---

## Running with Docker

### Building the Docker Image

1. Navigate to the streaming_middleware directory.
2. Build and run with Docker Compose:
   ```bash
   docker-compose build
   docker-compose up -d
   ```

### Running on Remote VM

```bash
# Create Docker context for remote deployment
docker context create NGINX --docker "host=ssh://pei_user@10.255.32.35"

# Build on remote
docker-compose build

# Start service
docker-compose up -d
```

### Firewall Configuration

Ensure the required ports are open:
```bash
sudo ufw allow 8080/tcp   # HTTP (HLS/DASH/Stats)
sudo ufw allow 1935/tcp   # RTMP
sudo ufw reload
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CAMERA_IP` | `10.255.35.86` | IP address of the RTSP camera |
| `RTSP_PORT` | `554` | RTSP port on the camera |
| `STREAM_LOW_PATH` | `stream2` | Path for 720p stream on camera |
| `STREAM_HIGH_PATH` | `stream1` | Path for 4K stream on camera |
| `GATE_ID` | `gate01` | Gate identifier (used in stream names) |

---

## Testing

### 1. Check if streams are active

```bash
curl http://10.255.32.35:8080/stat
```

### 2. Play HLS in browser

```
http://10.255.32.35:8080/hls/low/gate01.m3u8
```

### 3. Test RTMP with ffplay

```bash
ffplay rtmp://10.255.32.35:1935/streams_low/gate01
```

### 4. Health check

```bash
curl http://10.255.32.35:8080/health
# Expected: OK
```

### 5. Measure latency

```bash
# Direct RTSP latency
time ffmpeg -i rtsp://10.255.35.86:554/stream2 -frames:v 1 -f null - 2>&1 | grep "time="

# RTMP via NGINX latency
time ffmpeg -i rtmp://localhost:1935/streams_low/gate01 -frames:v 1 -f null - 2>&1 | grep "time="
```

---

## Debugging

### View container logs

```bash
docker logs -f nginx-rtmp
```

### View FFmpeg LOW logs

```bash
docker logs nginx-rtmp 2>&1 | grep "FFmpeg-LOW"
```

### View FFmpeg HIGH logs

```bash
docker logs nginx-rtmp 2>&1 | grep "FFmpeg-HIGH"
```

### Enter the container

```bash
docker exec -it nginx-rtmp bash
```

### Check running processes

```bash
docker exec nginx-rtmp ps aux | grep ffmpeg
```

---

## Performance

### Latency

| Stream Type | Latency |
|-------------|---------|
| RTMP (Agents) | ~500ms-1s |
| HLS (Frontend) | ~4-6s (2s fragments) |

### Bandwidth

| Stream | Bitrate |
|--------|---------|
| LOW (720p) | ~2-4 Mbps |
| HIGH (4K) | ~15-25 Mbps |

### CPU Usage

| Process | Usage |
|---------|-------|
| NGINX | ~5-10% (retransmission) |
| FFmpeg (2 processes) | ~15-30% (codec copy) |

---

## Integration with Microservices

### Agent Usage Examples

**AgentA (always connected to LOW):**
```python
from agentA_microservice.src.RTSPstream import RTSPStream

cap = RTSPStream("rtmp://nginx-rtmp/streams_low/gate01")
frame = cap.read()
```

**AgentB/AgentC (connects to HIGH on Kafka event):**
```python
# Wait for Kafka event
event = consumer.poll()

# Connect to 4K stream
cap = RTSPStream("rtmp://nginx-rtmp/streams_high/gate01")
frame = cap.read()

# Process and disconnect
cap.release()
```

**Frontend (consumes HLS):**
```javascript
import Hls from "hls.js";

const hls = new Hls();
hls.loadSource("http://nginx-rtmp:8080/hls/low/gate01.m3u8");
hls.attachMedia(videoElement);
```

---

## Additional Notes

- **Always-On**: Both 720p and 4K streams are continuously ingested.
- **Automatic Restart**: The `ingest_streams.sh` script monitors FFmpeg processes and restarts them if they fail.
- **Health Check**: Container has automatic health check every 30 seconds.
- **HLS Cleanup**: HLS fragments are automatically cleaned up (`hls_cleanup on`).
- **Security**: Only localhost (127.0.0.1) can publish streams; anyone can consume.
- **Multi-Gate**: Supports multiple gates by adding more `GATE_ID` configurations.