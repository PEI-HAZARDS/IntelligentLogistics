# IP Camera → MediaMTX Stream Router

Ingests 4 RTSP streams from 2 IP cameras and re-serves them over WebRTC (browser UIs) and RTSP (AI agents, ffplay, OpenCV).

---

## Architecture

```
IP Cameras (10.16.9.x)         MediaMTX VM (10.255.32.56)        Consumers (172.16.10.x)
                                                                   
  cam1 rtsp://10.16.9.2:554 ─┐                                  ┌─ Browser UI   (WebRTC :8889)
    stream1  4K  15fps        │  pull via RTSP/TCP               ├─ AI Agents    (RTSP/UDP :8554)
    stream2  low-res          ├──────────────────► MediaMTX ─────┤
  cam2 rtsp://10.16.9.4:554 ─┘                                  └─ ffplay/VLC   (RTSP/UDP :8554)
    stream1  4K  15fps
    stream2  low-res
```

**Leg 1 — Cameras → MediaMTX uses TCP.**
Cameras are 4K (3840×2160) generating ~30–50 Mbps per stream. At that bitrate, each
video frame is split into hundreds of UDP packets fired across the router between
10.16.9.x and 10.255.32.x. When the router buffer fills it silently drops packets —
UDP has no retry mechanism, so MediaMTX times out after 3s. TCP retransmits dropped
packets automatically, keeping the stream stable at the cost of a few extra milliseconds
of latency, which is acceptable for a fixed camera feed.

**Leg 2 — MediaMTX → Consumers uses UDP.**
Consumers are on the same network as the VM — no routers in between, no packet loss.
UDP is used here for low latency. WebRTC is always UDP under the hood regardless.

---

## Stream Paths

| Path | Camera | Resolution | Source URL |
|------|--------|------------|------------|
| `streams_high/gate1` | Gate 1 | 4K (3840×2160) 15fps | `rtsp://10.16.9.2:554/stream1` |
| `streams_low/gate1`  | Gate 1 | Low-res              | `rtsp://10.16.9.2:554/stream2` |
| `streams_high/gate2` | Gate 2 | 4K (3840×2160) 15fps | `rtsp://10.16.9.4:554/stream1` |
| `streams_low/gate2`  | Gate 2 | Low-res              | `rtsp://10.16.9.4:554/stream2` |

---

## Ports

| Port | Protocol | Purpose |
|------|----------|---------|
| `8554` | TCP | RTSP server — AI agents, ffplay, OpenCV connect here |
| `8000` | UDP | RTP — media data channel for RTSP clients |
| `8001` | UDP | RTCP — control channel for RTSP clients |
| `8889` | TCP | WebRTC HTTP signalling (WHEP endpoint for browsers) |
| `8189` | UDP | WebRTC ICE/DTLS/SRTP — actual media for browser UIs |

There are only two protocols, but each one splits across two ports — a handshake port and a video data port:

```
RTSP (AI agents)
  8554 → "hello, I want cam1_low, let's use UDP"   (handshake, then idle)
  8000 → ████████████████████████████████████████  (actual video, constant stream)
  8001 → "still alive? timestamp ok?"              (heartbeat, tiny trickle)

WebRTC (browser)
  8889 → "hello, here's my SDP offer"              (handshake, one HTTP request)
  8189 → ████████████████████████████████████████  (actual video, encrypted UDP)
```

`8554` and `8889` are doorbells — the client knocks once to negotiate, then video never flows through them. All the actual video data flows through `8000` (RTSP) and `8189` (WebRTC). `8001` is minor — just a trickle of timing signals alongside the video stream.

---

## Deployment

### Prerequisites
- Docker with a remote context pointing to the VM, or Docker installed directly on the VM
- Files in the same directory: `Dockerfile`, `docker-compose.yml`, `mediamtx.yml`

### Build and start
```bash
# If using a remote Docker context
docker context use <your-vm-context>

# Build the image (bakes mediamtx.yml in — no scp needed) and start
docker compose up --build -d
```

### View logs
```bash
docker logs -f mediamtx
```

### Stop
```bash
docker compose down
```

### Rebuild after config changes
Any change to `mediamtx.yml` requires a rebuild since it is baked into the image:
```bash
docker compose up --build -d
```

---

## Connecting: Browser UI

Open `camera-dashboard.html` directly in any browser on the same network.
It connects to all 4 streams simultaneously via WebRTC (WHEP protocol).

You can also open any single stream in a browser directly:
```
http://10.255.32.56:8889/streams_high/gate1
http://10.255.32.56:8889/streams_low/gate1
http://10.255.32.56:8889/streams_high/gate2
http://10.255.32.56:8889/streams_low/gate2
```

---

## Connecting: ffplay

Basic playback (UDP transport, low latency):
```bash
ffplay -rtsp_transport udp rtsp://10.255.32.56:8554/streams_high/gate1
```

With reduced buffering for near-realtime display:
```bash
ffplay -rtsp_transport udp -fflags nobuffer -flags low_delay -framedrop rtsp://10.255.32.56:8554/streams_high/gate1
```

All 4 streams (run each in a separate terminal):
```bash
ffplay -rtsp_transport udp rtsp://10.255.32.56:8554/streams_high/gate1
ffplay -rtsp_transport udp rtsp://10.255.32.56:8554/streams_low/gate1
ffplay -rtsp_transport udp rtsp://10.255.32.56:8554/streams_high/gate2
ffplay -rtsp_transport udp rtsp://10.255.32.56:8554/streams_low/gate2
```

If you see dropped frames on the 4K streams in ffplay, add `-buffer_size 1024000`:
```bash
ffplay -rtsp_transport udp -buffer_size 1024000 rtsp://10.255.32.56:8554/streams_high/gate1
```

---

## Connecting: AI Agents (Python / OpenCV)

```python
import cv2

# Recommended: use low-res streams for inference (faster, less memory)
# Use high-res only if your model requires it

cap = cv2.VideoCapture("rtsp://10.255.32.56:8554/streams_low/gate1", cv2.CAP_FFMPEG)

# Force UDP transport and reduce buffer for low latency
cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

while True:
    ret, frame = cap.read()
    if not ret:
        break
    # run your YOLO / OCR inference on frame
```

Stream URLs for agents:

| Stream | RTSP URL |
|--------|----------|
| streams_high/gate1 | `rtsp://10.255.32.56:8554/streams_high/gate1` |
| streams_low/gate1  | `rtsp://10.255.32.56:8554/streams_low/gate1`  |
| streams_high/gate2 | `rtsp://10.255.32.56:8554/streams_high/gate2` |
| streams_low/gate2  | `rtsp://10.255.32.56:8554/streams_low/gate2`  |

> **Tip:** Point YOLO/OCR agents at the `streams_low/` streams. They reconnect faster, use
> less CPU to decode, and inference accuracy rarely benefits from 4K input.
> Reserve `streams_high/` streams for recording or human review.

---

## Connecting: GStreamer

```bash
gst-launch-1.0 rtspsrc location=rtsp://10.255.32.56:8554/streams_low/gate1 protocols=udp ! \
  decodebin ! videoconvert ! autovideosink
```

---

## Troubleshooting

**`UDP timeout` on camera sources**
The camera → MediaMTX leg uses TCP (`rtspTransport: tcp` in `pathDefaults`).
If you see this, the config was not rebuilt into the image. Run `docker compose up --build -d`.

**`no stream is available on path`**
MediaMTX lost the camera connection and is reconnecting. Usually resolves in a few
seconds. Check camera is powered and reachable: `ping 10.16.9.2`

**WebRTC sessions connect then immediately close**
The `webrtcAdditionalHosts` IP must match the IP your browser can reach the VM on.
Currently set to `10.255.32.56`. If accessing from a different network, update this
value in `mediamtx.yml` and rebuild.

**ffplay shows frames but with high latency**
Add `-fflags nobuffer -flags low_delay -framedrop` to your ffplay command.

**`sourceAnyPortEnable` deprecation warning**
Harmless — this field was renamed to `rtspAnyPort` in v1.16. It is not present in
the current config; if you see the warning, an old config was loaded. Rebuild the image.