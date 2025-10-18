# Intelligent Logistics – Arquitetura Global do Sistema

O sistema adota uma **Macro-Arquitetura baseada em Microserviços**, onde cada componente é autónomo, escalável e especializado, implementando internamente uma **Arquitetura em Camadas**, e comunicando entre si através de um modelo **Event-Driven** (baseado em MQTT).

---

[React Native App] ---\
                        --> [API Gateway (FastAPI)] ---> [DB: PostgreSQL/MongoDB]
[React Web App] -------/

[API Gateway] <--> [Broker MQTT] <--> [Agente Edge (deteção YOLO)]
                                   \--> [Serviço ML na Cloud]
                                   \--> [Serviço de Decisão / Roteamento]

### Benefícios da Arquitetura
- **Escalável** → Adiciona câmeras/sensores sem impacto global.  
- **Flexível** → Diferentes front-ends (motorista / operador) partilham backend unificado.  
- **Tempo real** → MQTT assegura baixa latência na comunicação de eventos críticos.  
- **Integrável** → API REST/GraphQL facilmente consumida por sistemas portuários externos.

---

## Persistência Poliglota (Polyglot Persistence)

| Base de Dados | Tipo | Função | Exemplos |
|----------------|-------|---------|-----------|
| **PostgreSQL** | Relacional | Dados core e estruturados | Identificação de camiões, entradas/saídas, cais, relatórios |
| **MongoDB** | Não relacional | Dados flexíveis e não estruturados | Logs YOLO, eventos IoT/MQTT, histórico de métricas IA |

> Combinação ideal de **confiabilidade** (PostgreSQL) e **flexibilidade** (MongoDB).

[Motorista App (React Native)] --> [API FastAPI] --> PostgreSQL (dados estruturados)
                                              \
                                               --> MongoDB (logs, eventos IoT)

[Operador Cancela Dashboard] --> [API FastAPI] --> PostgreSQL (consultas, relatórios)
                                              \
                                               --> MongoDB (monitorização em tempo real)

[Agente ML / YOLO] --> [Broker MQTT] --> [API FastAPI] --> MongoDB (deteções)

---

### Vantagens
- **Confiabilidade** → PostgreSQL garante integridade administrativa.  
- **Flexibilidade** → MongoDB absorve dados variáveis.  
- **Escalabilidade** → MongoDB suporta milhões de mensagens IoT.  
- **Complementaridade** → API combina dados de ambas (relatórios + eventos ML).

---

## Exemplo de Cenário Real

1. **Camião chega** → YOLO deteta veículo → evento guardado no MongoDB.  
2. **Validação de matrícula** → Backend cria registo no PostgreSQL.  
3. **Operador confirma** → Atualização no PostgreSQL.  
4. **Relatório diário** → Combina PostgreSQL (dados operacionais) + MongoDB (análises ML).

---

##  Macro Arquitetura (Microservices)

```
┌────────────────────────────────────────────┐
│           VIRTUAL MACHINE (Datacenter)     │
│────────────────────────────────────────────│
│  Camera HTTP Stream                        │
│   - 720p: "http://cam-ip/720p"             │
│   - 4K:   "http://cam-ip/4k"               │
│                                            │
│  ┌──────────────────────────────────────┐  │
│  │ AI Detection Service (Python + YOLOv11) │
│  │ - lê feed HTTP/RTSP                     │
│  │ - 1ª deteção/class de camião (720p)     │
│  │ - publica no broker MQTT                │
│  │ - 2ª deteção/class matrícula (4k)       │
│  │ - OCR de matrícula e placa              │
│  │ - publica resultados no MQTT            │
│  └──────────────────────────────────────┘  │
│               │                            │
│               ▼                            │
│  MQTT Broker (Mosquitto - local)           │
│               │                            │
│               ▼                            │
│  Backend API (FastAPI + Paho MQTT)         │
│  - recebe deteções                         │
│  - grava PostgreSQL                        │
│  - envia logs para MongoDB                 │
│  - expõe API REST (/vehicles, /status)     │
│               │                            │
│               ▼                            │
│  Databases:                                │
│  - PostgreSQL (dados operacionais)         │
│  - MongoDB (logs / deteções)               │
│               │                            │
│               ▼                            │
│  Frontend Web (React)                      │
│  - Operador da cancela                     │
│  - Consome API FastAPI                     │
│                                            │
│  App Motorista (React Native)              │
│  - Consome API remota                      │
└────────────────────────────────────────────┘
```

---

## Arquitetura Interna (Layered)

```
┌────────────────────────────┐
│  Presentation Layer (API)  │ → Controladores / Endpoints REST
├────────────────────────────┤
│  Service Layer (Business)  │ → Regras de negócio / validações
├────────────────────────────┤
│  Data Access Layer (DAO)   │ → PostgreSQL / MongoDB
├────────────────────────────┤
│  Integration Layer         │ → MQTT Client / APIs externas
└────────────────────────────┘
```

---

## Roadmap de Implementação

| Etapa | Descrição | Tecnologias | Objetivo |
|-------|------------|-------------|-----------|
| **1. MVP (Atual)** | Sistema completo dentro de VM | YOLO + MQTT + FastAPI + React | Prova de conceito |
| **2. Containerização** | Separar módulos em Docker | Docker + Docker Compose | Deploy modular |
| **3. Escalabilidade** | Separar IA e Backend | Compose multi-host | Distribuição de carga |
| **4. Edge Computing** | Deploy em portos e datacenters | 5G + K3s (Kubernetes Edge) | Descentralização |
