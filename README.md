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

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            INTELLIGENT LOGISTICS                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────┐                      ┌──────────────────────┐    │
│  │       AI_APP         │     HTTP/Gateway     │        V_APP         │    │
│  │  (Computer Vision)   │◄────────────────────►│   (Business Logic)   │    │
│  │                      │                      │                      │    │
│  │  ┌────────────────┐  │                      │  ┌────────────────┐  │    │
│  │  │    AgentA      │  │                      │  │  API Gateway   │  │    │
│  │  │ Truck Detection│  │                      │  │   (FastAPI)    │  │    │
│  │  └───────┬────────┘  │                      │  └───────┬────────┘  │    │
│  │          │ Kafka     │                      │          │           │    │
│  │  ┌───────▼────────┐  │                      │  ┌───────▼────────┐  │    │
│  │  │    AgentB      │  │                      │  │ Decision Engine│  │    │
│  │  │ License Plate  │  │                      │  │  (Validation)  │  │    │
│  │  └───────┬────────┘  │                      │  └───────┬────────┘  │    │
│  │          │ Kafka     │                      │          │           │    │
│  │  ┌───────▼────────┐  │                      │  ┌───────▼────────┐  │    │
│  │  │    AgentC      │  │                      │  │  Data Module   │  │    │
│  │  │ Hazard Plates  │  │                      │  │  (PostgreSQL,  │  │    │
│  │  └───────┬────────┘  │                      │  │  MongoDB, Redis│  │    │
│  │          │           │                      │  │  MinIO)        │  │    │
│  │  ┌───────▼────────┐  │                      │  └────────────────┘  │    │
│  │  │   AI Gateway   │◄─┼──────────────────────┼►│    V Gateway    │  │    │
│  │  └────────────────┘  │                      │  └────────────────┘  │    │
│  └──────────────────────┘                      └──────────────────────┘    │
│                                                                             │
│  ┌──────────────────────┐          ┌──────────────────────────────────┐    │
│  │ Streaming Middleware │          │       Observability Stack        │    │
│  │   (NGINX RTMP)       │          │  (Prometheus, Grafana, Loki)     │    │
│  │  RTSP → RTMP/HLS     │          └──────────────────────────────────┘    │
│  └──────────────────────┘                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### AI_APP — Computer Vision Pipeline

The AI application implements a multi-agent detection pipeline using a **Blackboard Architecture**:

| Agent | Function | Model | Input |
|-------|----------|-------|-------|
| **AgentA** | Truck Detection | YOLOv8 | 720p RTMP stream |
| **AgentB** | License Plate Detection + OCR | YOLOv8 + PaddleOCR | 4K RTMP stream |
| **AgentC** | Hazard Plate Detection + OCR | YOLOv8 + PaddleOCR | 4K RTMP stream |
| **AI Gateway** | Inter-app communication | — | Kafka events |

**Detection Flow:**
1. AgentA monitors the 720p stream and detects trucks → publishes `truck_detected` event
2. AgentB and AgentC subscribe to `truck_detected`, switch to 4K stream for detailed analysis
3. AgentB extracts license plates → publishes `license_plate_results`
4. AgentC extracts UN/Kemler codes from hazard placards → publishes `hazard_plate_results`
5. AI Gateway forwards results to V_APP via HTTP

### V_APP — Business Logic & Data Services

The vehicle application handles business logic, data persistence, and client communication:

| Component | Function | Technology |
|-----------|----------|------------|
| **API Gateway** | REST API, WebSocket notifications | FastAPI |
| **Decision Engine** | Access validation & routing decisions | Python |
| **Data Module** | Data persistence & caching | PostgreSQL, MongoDB, Redis |
| **V Gateway** | Inter-app communication | FastAPI + Kafka |
| **MinIO** | Object storage for images/crops | S3-compatible |

### Streaming Middleware

NGINX RTMP server that ingests camera streams and redistributes to consumers:

| Stream | Resolution | Consumers | Latency |
|--------|------------|-----------|---------|
| RTMP LOW | 720p | AgentA (continuous) | ~500ms |
| RTMP HIGH | 4K | AgentB, AgentC (on-demand) | ~500ms |
| HLS | 720p/4K | Frontend web players | ~4-6s |

### Communication Patterns

- **Inter-Application**: HTTP via Gateways (AI Gateway ↔ V Gateway)
- **Intra-Application**: Apache Kafka (KRaft mode) for event-driven messaging
- **Client Communication**: REST API + WebSocket for real-time notifications

---

## Technology Stack

| Category | Technologies |
|----------|--------------|
| **ML/CV** | YOLOv8 (Ultralytics), PaddleOCR, PyTorch |
| **Backend** | Python, FastAPI, Pydantic |
| **Messaging** | Apache Kafka (KRaft mode) |
| **Databases** | PostgreSQL, MongoDB, Redis |
| **Storage** | MinIO (S3-compatible) |
| **Streaming** | NGINX RTMP, FFmpeg |
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


---

## Project Structure

```
src/
├── AI_APP/                    # Computer Vision Application
│   ├── agentA/                # Truck detection agent
│   ├── agentB/                # License plate agent
│   ├── agentC/                # Hazard plate agent
│   ├── gateway/               # AI Gateway (inter-app bridge)
│   ├── shared/                # Shared ML components
│   └── docker-compose.yml
│
├── V_APP/                     # Vehicle/Business Application
│   ├── api_gateway/           # REST API & WebSocket
│   ├── decision_engine/       # Access decision logic
│   ├── gateway/               # V Gateway (inter-app bridge)
│   ├── Data_Module/           # Data persistence services
│   └── docker-compose.yml
│
├── streaming_middleware/      # NGINX RTMP server
├── devops/
│   ├── observability/         # Prometheus, Grafana, Loki stack
│   └── jenkins/               # CI/CD pipelines
└── shared/                    # Cross-application utilities
```

---

## Future Evolutions (Phase II)  
- **Active learning**: allow the system to learn to identify new cargo types and symbols as they arise.  
- **Energy efficiency**: optimize the use of AI resources in datacenters, balancing performance and energy consumption.  

---

## Demonstration  
Integration with **real datacenters** and practical tests in port environments (such as the Port of Aveiro).  

---

✨ This project combines **AI, computer vision, logistics, and energy efficiency**, being a proposal aligned with the challenges of Industry 4.0.  


## Future Work

- (...)