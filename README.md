# Intelligent Logistics  

[![Figma](https://img.shields.io/badge/Figma-Design-orange?logo=figma)](https://www.figma.com/files/team/1309815608365821624/project/171687163/PEI?fuid=1309815603742744973)
[![Microsite](https://img.shields.io/badge/Microsite-PEI-blue?logo=github)](https://pei-hazards.github.io/Micro-site/)

## Introduction  
We live in an era where logistics is invisible but essential: our orders arrive the next day with just a click, but behind this process there are millions of containers and complex operations. In 2023 alone, it is estimated that **858 million containers** passed through seaports worldwide, moved by ships, trucks, and land infrastructure.  

This growing volume brings with it huge logistical challenges: delays, routing errors, and operational costs. In large ports — veritable mazes with dozens of warehouses — a single wrong instruction is enough for cargo to be sent to the wrong destination, generating **losses of time and money**.  

---

## Motivation  
To increase **efficiency** and reduce costs, port authorities are adopting **Information and Communication Technologies (ICT)** and **Industry 4.0** concepts. With the democratization of **Artificial Intelligence**, **cloud computing**, and the **digitization of processes**, innovative solutions are emerging to make logistics more **intelligent, automated, and sustainable**.  

The **Intelligent Logistics** project proposes exactly that:  
- Automate the **truck entry control** in a port.  
- Detect vehicles and cargo using cameras and computer vision algorithms.  
- Integrate the information with an **intelligent logistics system** that decides the correct entry and destination.  
- Clearly inform the driver, whether through **digital signage** at the port or **mobile applications**.  

---

## System Architecture

The system adopts a **containerized microservices architecture** organized into two main applications that communicate via gateways:

![System architecture](docs/sketch_arquitetura/arch_technological.png)

For a full deployment topology (VM layout, Kafka topics, and end-to-end flow), see
[docs/sketch_arquitetura/arch_flow.md](docs/sketch_arquitetura/arch_flow.md).

### AI_APP — Computer Vision Pipeline

The AI application implements a multi-agent detection pipeline using a **Blackboard Architecture**:

| Agent | Function | Model | Input |
|-------|----------|-------|-------|
| **AgentA** | Truck Detection | YOLOv11 | Low-res stream |
| **AgentB** | License Plate Detection + OCR | YOLOv11 + PaddleOCR | High-res stream |
| **AgentC** | Hazard Plate Detection + OCR | YOLOv11 + PaddleOCR | High-res stream |
| **AI Gateway** | Inter-app communication | — | Kafka events |

**Detection Flow:**
1. AgentA monitors the low-res stream and detects trucks → publishes `truck-detected-{GATE_ID}`
2. AgentB and AgentC subscribe to `truck-detected-{GATE_ID}`, switch to 4K stream for detailed analysis
3. AgentB extracts license plates → publishes `lp-results-{GATE_ID}`
4. AgentC extracts UN/Kemler codes from hazard placards → publishes `hz-results-{GATE_ID}`
5. AI Gateway forwards results to V_APP via HTTP
6. V-Brain sends a reset message to AgentA to re-arm the next detection cycle

**Notes:**
- AgentA is always-on on the low-res stream, but after publishing `truck-detected-{GATE_ID}` it waits for a V-Brain reset to re-arm (debounce ~35s as a safety net).
- AgentB and AgentC are event-driven, run consensus OCR across multiple frames, and upload crops to MinIO buckets.

### V_APP — Business Logic & Data Services

The vehicle application handles business logic, data persistence, and client communication:

| Component | Function | Technology |
|-----------|----------|------------|
| **API Gateway** | REST API, WebSocket notifications | FastAPI |
| **Decision Engine** | Access validation & routing decisions | Python |
| **Infraction Engine** | HighWay infraction decisions | Python |
| **V-Brain** | Cross-gate orchestration, scale up/down, AgentA reset | Python + Kafka |
| **V Gateway** | Inter-app communication | FastAPI + Kafka |
| **V Broker** | Internal event bus | Kafka (KRaft) |
| **Data Module** | Data persistence & caching | PostgreSQL, MongoDB, Redis |
| **Keycloak** | Identity provider | Keycloak |
| **MinIO** | Object storage for images/crops | S3-compatible |

**Key behaviors:**
- Decision Engine buffers results by `truck_id`, applies Levenshtein-based plate matching, and publishes `agent-decision-{GATE_ID}`.
- API Gateway proxies Data Module routes, emits WebSocket notifications, and enforces Keycloak roles.
- Data Module applies CQRS + Unit of Work + Inbox/Outbox with PostgreSQL (source of truth), MongoDB (events), and Redis (cache).

### Streaming Middleware

StreamV3 uses **MediaMTX** to ingest RTSP from IP cameras and re-serve streams to agents and UIs.
The legacy NGINX RTMP/HLS pipeline is documented in
[deprecated/streaming_middleware/README.md](deprecated/streaming_middleware/README.md).

| Stream Path | Resolution | Consumers | Protocol |
|-------------|------------|-----------|----------|
| `streams_low/gate{N}` | Low-res | AgentA (armed by reset) | RTSP/UDP |
| `streams_high/gate{N}` | 4K | AgentB, AgentC, operators | RTSP/UDP |
| `streams_*` | Low/4K | Frontend web players | WebRTC (WHEP) |

Key ports: RTSP `8554` (media on `8000/8001`), WebRTC `8889` (media on `8189`).
See [src/streamV3/README.md](src/streamV3/README.md) for full deployment and troubleshooting.

### Communication Patterns

- **Inter-Application**: HTTP via Gateways (AI Gateway ↔ V Gateway)
- **Intra-Application**: Apache Kafka (KRaft mode) for event-driven messaging
- **Client Communication**: REST API + WebSocket for real-time notifications
- **External Alerts**: MQTT over WSS for Mobitrust dangerous materials alerts

### Authentication & Authorization

Keycloak is the identity provider. The API Gateway exchanges credentials (ROPC), validates JWTs via
JWKS, and enforces RBAC for driver/operator/manager roles. See
[src/V_APP/keycloak/README.md](src/V_APP/keycloak/README.md).

---

## Technology Stack

| Category | Technologies |
|----------|--------------|
| **ML/CV** | YOLOv11 (Ultralytics), PaddleOCR, PyTorch |
| **Backend** | Python, FastAPI, Pydantic |
| **Messaging** | Apache Kafka (KRaft mode)|
| **Databases** | PostgreSQL, MongoDB, Redis |
| **Storage** | MinIO (S3-compatible) |
| **Streaming** | MediaMTX (RTSP/WebRTC), FFmpeg |
| **Identity** | Keycloak (JWT, RBAC) |
| **Containers** | Docker, Docker Compose |
| **Observability** | Prometheus, Grafana, Loki, Alertmanager, Tempo |

---

## Requirements  

### **Functional**  
- Real-time truck detection in 720p video streams with configurable confidence threshold
- License plate detection and OCR with Portuguese format validation (XX-XX-XX)
- Hazard placard detection with UN/Kemler code extraction
- Access decision generation: APPROVE, DENY, or MANUAL_REVIEW
- Integration with whitelist/blacklist for vehicle validation
- Time-based access rules (allowed hours, days, authorization expiry)
- Real-time WebSocket notifications to gate operators
- REST API for event queries, decision history, and manual review
- Image storage with presigned URL generation
- Audit logging of all actions

### **Non-Functional**  

- **Energy efficiency**: optimization of computational resource usage.  
- **Scalability**: Support multiple gates with independent agent instances
- **Flexibility**: active learning of new symbols/cargo types (?).  
- **Reliability**: Consensus algorithm for OCR accuracy
- **Security**: protection of logistics data and monitored vehicles.  
- **Performance**: Detection and notification must not exceed 2 seconds between capture and availability to the operator.  
- **Availability**: The system must maintain a minimum availability of 99% in the production environment.
- **Observability**: Full metrics, logging, and tracing pipeline

Detailed requirement specifications live in [docs/requisitos/RF.md](docs/requisitos/RF.md) and
[docs/requisitos/RNF.md](docs/requisitos/RNF.md).

---

## Project Structure

```
backend/
├── code_documentation/        # Deep-dive component docs
├── docs/                      # Requirements, architecture, benchmarks
├── env_manager/               # .env sync tooling (rclone)
└── src/
	├── AI_APP/                # Computer Vision Application
	│   ├── agentA/            # Truck detection agent
	│   ├── agentB/            # License plate agent
	│   ├── agentC/            # Hazard plate agent
	│   ├── broker/            # Kafka broker + dashboards
	│   ├── gateway/           # AI Gateway (inter-app bridge)
	│   ├── shared/            # Shared ML components
	│   └── tests/             # Integration and unit tests
	│
	├── V_APP/                 # Vehicle/Business Application
	│   ├── api_gateway/        # REST API & WebSocket
	│   ├── decision_engine/    # Access decision logic
	│   ├── gateway/            # V Gateway (inter-app bridge)
	│   ├── Data_Module/        # Data persistence services
	│   ├── infraction_engine/  # Infractions processing
	│   ├── keycloak/           # Keycloak realm + user sync
	│   ├── v_brain/            # V-Brain coordination logic
	│   ├── shared/             # Shared V_APP components
	│   └── test_scripts/       # Manual test helpers
	│
	├── devops/
	│   ├── observability/      # Prometheus, Grafana, Loki stack
	│   └── promtail-remote/    # Remote promtail shipping
	├── streamV3/               # MediaMTX stream router
	└── shared/                 # Cross-application utilities
```

## Operational Docs

- [env_manager/env_manager.md](env_manager/env_manager.md) — .env sync with Google Drive
- [docs/sketch_arquitetura/arch_flow.md](docs/sketch_arquitetura/arch_flow.md) — deployment topology and full flow
- [src/streamV3/README.md](src/streamV3/README.md) — MediaMTX stream router and ports
- [src/devops/observability/README.md](src/devops/observability/README.md) — observability stack quickstart
- [src/V_APP/keycloak/README.md](src/V_APP/keycloak/README.md) — Keycloak auth flow and roles
- [src/V_APP/Data_Module/README.md](src/V_APP/Data_Module/README.md) — CQRS/UoW/Outbox architecture
- [src/mobitrust/README.md](src/mobitrust/README.md) — MQTT alerts for dangerous materials
- [src/AI_APP/tests/TESTING.md](src/AI_APP/tests/TESTING.md) — AI_APP integration test suites

## Testing

AI_APP integration tests (from repository root):

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -r src/AI_APP/shared/tests/requirements.txt
PYTHONPATH=src uv run --active pytest -q src/AI_APP/tests
```
---

## Demonstration  
Integration with **real datacenters** and practical tests in port environments (such as the Port of Aveiro).  
- **Energy efficiency**: optimize the use of AI resources in datacenters and 6G-network, balancing performance and energy consumption.  

---

✨ This project combines **AI, computer vision, logistics, and energy efficiency**, being a proposal aligned with the challenges of Industry 4.0.  

---

## License

This repository's source code is licensed under the MIT License ([LICENSE](LICENSE)).

This project depends on third-party software with separate licenses, including:

- Ultralytics YOLOv11 (`ultralytics`) - AGPL-3.0 License

Use of this project together with AGPL-licensed dependencies may trigger additional
obligations under the AGPL-3.0, especially when distributing the software or making
it available as a network service.

Users are responsible for complying with the licenses of all dependencies.

---

## Future Work
- MLOps pipeline: allow the system to learn to identify new cargo types and symbols as they arise.  
- Secure intra-port routing
