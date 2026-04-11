# MediaMTX Migration — All Changes

## Overview

Migrated the streaming infrastructure from NGINX-RTMP to **MediaMTX**, updating stream URLs across the entire stack and switching protocols for lower latency:

| Layer | Before | After |
|---|---|---|
| **AI Agents → MediaMTX** | RTMP (TCP, port 1935) | RTSP (UDP, port 8554) |
| **Browser → MediaMTX** | HLS with broken URLs | WebRTC iframe (port 8889) |
| **API Gateway** | Wrong URL pattern | Correct MediaMTX pattern + both HLS & WebRTC URLs |

---

## 1. Backend — API Gateway

### [stream.py](file:///home/tsh19/Universidade/3ºano/PEI/IntelligentLogistics/src/V_APP/api_gateway/src/routers/stream.py)

Fixed URL builder to match MediaMTX's path pattern and added WebRTC URL to the response:

```diff
-/hls/{quality}/{gate_id}/index.m3u8
+/streams_{quality}/{gate_id}/index.m3u8
```

Both endpoints now return [hls_url](file:///home/tsh19/Universidade/3%C2%BAano/PEI/IntelligentLogistics/src/V_APP/api_gateway/src/routers/stream.py#8-21) and [webrtc_url](file:///home/tsh19/Universidade/3%C2%BAano/PEI/IntelligentLogistics/src/V_APP/api_gateway/src/routers/stream.py#23-36).

### [api_gateway.py](file:///home/tsh19/Universidade/3ºano/PEI/IntelligentLogistics/src/V_APP/api_gateway/src/api_gateway.py)

Added [stream_webrtc_base_url](file:///home/tsh19/Universidade/3%C2%BAano/PEI/IntelligentLogistics/src/V_APP/api_gateway/src/dependencies.py#16-19) config field (default `http://mediamtx:8889`), stored on `app.state`.

### [dependencies.py](file:///home/tsh19/Universidade/3ºano/PEI/IntelligentLogistics/src/V_APP/api_gateway/src/dependencies.py)

Added [get_stream_webrtc_base_url()](file:///home/tsh19/Universidade/3%C2%BAano/PEI/IntelligentLogistics/src/V_APP/api_gateway/src/dependencies.py#16-19) FastAPI dependency.

### [docker-compose.yml](file:///home/tsh19/Universidade/3ºano/PEI/IntelligentLogistics/src/V_APP/docker-compose.yml)

Added `STREAM_WEBRTC_BASE_URL` env var passthrough to the api-gateway service.

### [.env](file:///home/tsh19/Universidade/3ºano/PEI/IntelligentLogistics/src/V_APP/.env) + [.env.example](file:///home/tsh19/Universidade/3ºano/PEI/IntelligentLogistics/src/V_APP/.env.example)

```diff
-STREAM_BASE_URL=http://10.255.32.56:8080
+STREAM_BASE_URL=http://10.255.32.56:8888
+STREAM_WEBRTC_BASE_URL=http://10.255.32.56:8889
```

---

## 2. Frontend

### [streams.ts](file:///home/tsh19/Universidade/3ºano/PEI/IntelligentLogistics_APP/intelligent-logistics-frontend/src/services/streams.ts)

- Added [webrtc_url](file:///home/tsh19/Universidade/3%C2%BAano/PEI/IntelligentLogistics/src/V_APP/api_gateway/src/routers/stream.py#23-36) to [StreamInfo](file:///home/tsh19/Universidade/3%C2%BAano/PEI/IntelligentLogistics_APP/intelligent-logistics-frontend/src/services/streams.ts#7-13) interface
- [getStreamUrl()](file:///home/tsh19/Universidade/3%C2%BAano/PEI/IntelligentLogistics_APP/intelligent-logistics-frontend/src/services/streams.ts#30-43) returns [webrtc_url](file:///home/tsh19/Universidade/3%C2%BAano/PEI/IntelligentLogistics/src/V_APP/api_gateway/src/routers/stream.py#23-36) for iframe playback

### [Dashboard.tsx](file:///home/tsh19/Universidade/3ºano/PEI/IntelligentLogistics_APP/intelligent-logistics-frontend/src/components/gate-operator/Dashboard.tsx)

Replaced `<HLSPlayer>` with `<iframe>` pointing to MediaMTX's WebRTC page.

### [WarningSign.tsx](file:///home/tsh19/Universidade/3ºano/PEI/IntelligentLogistics_APP/intelligent-logistics-frontend/src/pages/shared/WarningSign.tsx)

Same as Dashboard — `<HLSPlayer>` → `<iframe>`, removed HLS `<style>` block.

### [useStreamScale.ts](file:///home/tsh19/Universidade/3ºano/PEI/IntelligentLogistics_APP/intelligent-logistics-frontend/src/hooks/useStreamScale.ts)

Updated JSDoc to reflect WebRTC instead of HLS.

---

## 3. MediaMTX — WebRTC Docker NAT Fix

### Problem
MediaMTX inside Docker advertised container-internal IPs (`127.0.0.1`, `172.18.0.x`) as ICE candidates. Browsers couldn't reach those, causing `deadline exceeded while waiting connection`.

### Solution

#### [docker-compose.yml](file:///home/tsh19/Universidade/3ºano/PEI/IntelligentLogistics/src/streamV2/docker-compose.yml)

Added WebRTC NAT traversal env vars using MediaMTX's native `MTX_` prefix convention:

```yaml
# Disable auto-gathering Docker-internal IPs
- MTX_WEBRTCIPSFROMINTERFACES=false
# Advertise only the host VM's external IP
- MTX_WEBRTCADDITIONALHOSTS=${MTX_WEBRTC_HOST_IP}
# Single UDP+TCP port for WebRTC media transport
- MTX_WEBRTCLOCALUDPADDRESS=:8189
- MTX_WEBRTCLOCALTCPADDRESS=:8189
```

Exposed port `8189` (UDP + TCP) for WebRTC media transport.

#### [mediamtx.yml](file:///home/tsh19/Universidade/3ºano/PEI/IntelligentLogistics/src/streamV2/mediamtx.yml)

Added documentation comments referencing the env var overrides.

#### [.env](file:///home/tsh19/Universidade/3ºano/PEI/IntelligentLogistics/src/streamV2/.env) + [.env.example](file:///home/tsh19/Universidade/3ºano/PEI/IntelligentLogistics/src/streamV2/.env.example) (NEW)

Added `MTX_WEBRTC_HOST_IP=10.255.32.56` and created the missing [.env.example](file:///home/tsh19/Universidade/3%C2%BAano/PEI/IntelligentLogistics/src/V_APP/.env.example).

> [!IMPORTANT]
> The correct MediaMTX env var field names were found from the [official config](https://github.com/bluenviron/mediamtx/blob/main/mediamtx.yml). Earlier attempts using `webrtcICEHostNAT1To1` and `webrtcICEUDPMuxAddress` failed because those fields don't exist in the current version.

---

## 4. AI Agents — RTMP → RTSP

Switched all three agents from RTMP (TCP) to RTSP (UDP) for lower-latency frame delivery.

### [base_agent.py](file:///home/tsh19/Universidade/3ºano/PEI/IntelligentLogistics/src/AI_APP/shared/src/base_agent.py) (AgentB, AgentC)

```diff
-nginx_port: int = Field(default=1935)
+nginx_port: int = Field(default=8554)
 ...
-return f"rtmp://{self.nginx_host}:{self.nginx_port}/streams_high/gate{self.gate_id}"
+return f"rtsp://{self.nginx_host}:{self.nginx_port}/streams_high/gate{self.gate_id}"
```

### [agentA.py](file:///home/tsh19/Universidade/3ºano/PEI/IntelligentLogistics/src/AI_APP/agentA/src/agentA.py)

Same change for the low-quality stream URL (`streams_low/gate{id}`).

### [AI_APP/.env](file:///home/tsh19/Universidade/3ºano/PEI/IntelligentLogistics/src/AI_APP/.env) + [.env.example](file:///home/tsh19/Universidade/3ºano/PEI/IntelligentLogistics/src/AI_APP/.env.example)

```diff
-NGINX_PORT=1935
+NGINX_PORT=8554
```

### [base_agent_unit_test.py](file:///home/tsh19/Universidade/3ºano/PEI/IntelligentLogistics/src/AI_APP/shared/tests/base_agent_unit_test.py)

Updated assertion `rtmp://` → `rtsp://`.

---

## Deployment Checklist

```bash
# 1. Rebuild MediaMTX (WebRTC NAT fix + updated config)
cd src/streamV2 && docker-compose up -d --build

# 2. Rebuild API Gateway (new stream URLs + WebRTC env var)
cd src/V_APP && docker-compose up -d --build api-gateway

# 3. Rebuild AI Agents (RTMP → RTSP)
cd src/AI_APP && docker-compose up -d --build

# 4. Rebuild Frontend (WebRTC iframe)
# (standard frontend build process)
```
