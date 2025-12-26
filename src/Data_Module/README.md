# Data Module - Intelligent Logistics

The **Data Module** is the source of truth microservice for the Intelligent Logistics system. It serves as the central data layer, managing all persistent storage (PostgreSQL, MongoDB, Redis) and providing RESTful APIs for other microservices.

---

## Architecture Overview

```mermaid
flowchart TB
    subgraph DataModule["Data Module (Port 8080)"]
        API["FastAPI Server"]
        
        subgraph Databases
            PG[(PostgreSQL)]
            MONGO[(MongoDB)]
            REDIS[(Redis)]
        end
        
        API --> PG
        API --> MONGO
        API --> REDIS
    end
    
    DE["Decision Engine"] <--> API
    GW["API Gateway"] <--> API
    FE["Frontend Apps"] --> GW
```

---

## Project Structure

```
Data_Module/
├── main.py                 # FastAPI application entrypoint
├── config.py               # Environment configuration (Pydantic Settings)
├── Dockerfile              # Container image definition
├── docker-compose.yml      # Local development stack
├── entrypoint.sh           # Container startup script
├── requirements.txt        # Python dependencies
│
├── db/                     # Database connections
│   ├── postgres.py         # SQLAlchemy engine + session (simulation of port terminal data)
│   ├── mongo.py            # PyMongo client + collections (persistency of events)
│   └── redis.py            # Redis client (caching of decisions)
│
├── models/
│   ├── sql_models.py       # SQLAlchemy ORM models
│   └── pydantic_models.py  # Request/Response schemas (data validation)
│
├── routes/                 # API endpoints (FastAPI routers)
│   ├── arrivals.py         # Appointment/arrival management
│   ├── decisions.py        # Decision Engine integration
│   ├── driver.py           # Driver authentication & operations
│   ├── alerts.py           # Alert management
│   ├── worker.py           # Operator/Manager authentication
│   └── events.py           # Legacy events endpoint
│
├── services/               # Business logic layer
│   ├── arrival_service.py  # Appointment CRUD + queries
│   ├── decision_service.py # Decision processing logic
│   ├── driver_service.py   # Driver authentication
│   ├── alert_service.py    # Alert creation + hazmat handling
│   ├── worker_service.py   # Worker/Operator authentication
│   ├── cache_service.py    # Redis cache utilities
│   └── event_service.py    # MongoDB event logging
│
├── scripts/
│   ├── data_init.py        # Database seeding (populate with sample data, simulation of port terminal data)
│   ├── data_init_sample.py # Sample data for development (mvp)
│   ├── triggers.sql        # PostgreSQL triggers (for events)
│   └── indexes.sql         # PostgreSQL indexes (for performance)
│
└── tests/
    └── test_integration.py # Integration tests (for development)
```

---

## Driver Authentication

### Current Flow (Simplified)

The driver authentication uses a simple flow:

1. **Login**: Driver validates credentials (license + password)
2. **Access via PIN**: Driver uses the appointment PIN (arrival_id) to access delivery details

```mermaid
sequenceDiagram
    participant App as Driver App
    participant GW as API Gateway
    participant DM as Data Module

    Note over App,DM: 1. Login (validate credentials)
    App->>GW: POST /drivers/login {license, password}
    GW->>DM: Forward request
    DM-->>GW: {driver_info}
    GW-->>App: Store driver info locally

    Note over App,DM: 2. View today's deliveries
    App->>GW: GET /drivers/me/today?drivers_license=XX
    DM-->>App: List of today's appointments

    Note over App,DM: 3. Access delivery via PIN
    App->>GW: POST /drivers/claim {arrival_id: "PRT-001"}
    GW->>DM: Validate PIN + sequential order
    DM-->>App: Delivery details + navigation
```

### Sequential Delivery Control

Drivers must complete deliveries in order. The `/claim` endpoint validates:
- PIN is valid and belongs to the driver
- This is the next delivery in queue (unless debug mode is enabled)

### Debug Mode

For testing, sequential validation can be disabled:

```bash
export DEBUG_MODE=true
# Then use: POST /drivers/claim?debug=true
```

### Future: OAuth 2.0 + JWT

> [!NOTE]
> **Planned Enhancement**: Full token-based authentication with OAuth 2.0 + JWT.
> 
> When implemented:
> - Login will return JWT access token
> - All `/me/*` endpoints will require `Authorization: Bearer <token>`
> - Proper session management with refresh tokens
> - Session fields in Driver model are reserved for this purpose

---

## Database Schema

We designed the database searching for the most common use cases and the most important data for the system to function.

### PostgreSQL (Relational Data)

| Entity       | Description                              |
|--------------|------------------------------------------|
| `Terminal`   | Port terminal with coordinates           |
| `Gate`       | Entry/exit gates                         |
| `Dock`       | Loading/unloading bays                   |
| `Company`    | Transport companies (by NIF)             |
| `Driver`     | Truck drivers with authentication        |
| `Truck`      | Vehicles by license plate                |
| `Worker`     | Staff (base for Manager/Operator)        |
| `Manager`    | Logistics managers                       |
| `Operator`   | Gate operators                           |
| `Shift`      | Work shifts per gate                     |
| `Booking`    | Cargo bookings with reference            |
| `Cargo`      | Individual cargo items (hazmat flags)    |
| `Appointment`| Scheduled arrivals (core entity)         |
| `Visit`      | Actual gate visits                       |
| `Alert`      | System alerts (safety/operational)       |

### MongoDB (Event Logs)

| Collection      | Purpose                               |
|-----------------|---------------------------------------|
| `detections`    | License/hazardous plate detection events        |
| `events`        | General system events                 |
| `system_logs`   | Application logs                      |
| `ocr_failures`  | Failed OCR recognition attempts       |

### Redis (Cache)

Used for caching decision results and preventing duplicate processing, important to improve performance a critical point of the system.

---

## Running Locally with Docker
Here we provide a docker-compose file to run the application locally. (you would have a independent data module to experiment with the system or to use it as a standalone service)
### Pre-requisites

- Docker & Docker Compose installed
- Ports available: `8080`, `5432`, `27017`, `6379`

### Quick Start

```bash
cd src/Data_Module

# Start all services (PostgreSQL, MongoDB, Redis, API)
docker-compose up -d

# Check logs
docker-compose logs -f data-module

# Verify health
curl http://localhost:8080/api/v1/health
```

### Expected Health Response

```json
{
  "status": "ok",
  "components": {
    "postgres": true,
    "mongo": true,
    "redis": true
  },
  "decision_engine_url": "http://decision-engine:8001"
}
```

### Stop Services

```bash
docker-compose down

# Remove volumes (reset databases)
docker-compose down -v
```

---

## Environment Variables

| Variable               | Default                                    | Description                    |
|------------------------|--------------------------------------------|--------------------------------|
| `POSTGRES_HOST`        | `postgres`                                 | PostgreSQL hostname            |
| `POSTGRES_PORT`        | `5432`                                     | PostgreSQL port                |
| `POSTGRES_USER`        | `porto`                                    | Database user                  |
| `POSTGRES_PASSWORD`    | `porto_password`                           | Database password              |
| `POSTGRES_DB`          | `porto_logistica`                          | Database name                  |
| `MONGO_URL`            | `mongodb://admin:admin123@mongo:27017`     | MongoDB connection string      |
| `REDIS_HOST`           | `redis`                                    | Redis hostname                 |
| `REDIS_PORT`           | `6379`                                     | Redis port                     |
| `DECISION_ENGINE_URL`  | `http://decision-engine:8001`              | Decision Engine endpoint       |
| `DEBUG_MODE`           | `false`                                    | Enable debug mode (bypass sequential delivery validation) |
| `TOKEN_EXPIRY_HOURS`   | `24`                                       | Driver session token expiry (hours) |

---

## API Endpoints

Base URL: `http://localhost:8080/api/v1`
Swagger UI: `http://localhost:8080/docs`

### Health

| Method | Endpoint   | Description         |
|--------|------------|---------------------|
| GET    | `/health`  | Service health check|

### Arrivals

| Method | Endpoint                                  | Description                        |
|--------|-------------------------------------------|------------------------------------|
| GET    | `/arrivals`                               | List appointments (paginated)      |
| GET    | `/arrivals/{id}`                          | Get appointment by ID              |
| GET    | `/arrivals/pin/{pin}`                     | Get appointment by access PIN      |
| GET    | `/arrivals/stats`                         | Appointment statistics             |
| GET    | `/arrivals/next/{gate_id}`                | Next arrivals for gate             |
| GET    | `/arrivals/query/license-plate/{plate}`   | Query by license plate             |
| POST   | `/arrivals/{id}/decision`                 | Process decision for appointment   |

### Decisions

| Method | Endpoint                   | Description                              |
|--------|----------------------------|------------------------------------------|
| POST   | `/decisions/process`       | Receive decision from Decision Engine    |
| POST   | `/decisions/query-appointments` | Query candidate appointments        |
| POST   | `/decisions/detection-event`    | Register detection event            |

### Drivers

Simple flow: Login validates credentials, then use `drivers_license` as query parameter for subsequent calls.

| Method | Endpoint                      | Description                           |
|--------|-------------------------------|---------------------------------------|
| POST   | `/drivers/login`              | Validate credentials, get driver info |
| POST   | `/drivers/claim`              | Claim delivery via PIN (arrival_id)   |
| GET    | `/drivers/me/active`          | Get driver's active appointment       |
| GET    | `/drivers/me/today`           | Get driver's today appointments       |
| GET    | `/drivers/me/history`         | Get driver's delivery history         |
| GET    | `/drivers`                    | List all drivers (backoffice)         |
| GET    | `/drivers/{license}`          | Get driver details (backoffice)       |
| GET    | `/drivers/{license}/arrivals` | Get driver history (backoffice)       |

> **Note**: `/claim` validates sequential order. Use `?debug=true` with `DEBUG_MODE=true` to bypass.
> 
> **Future**: OAuth 2.0 + JWT will add `Authorization: Bearer <token>` to all `/me/*` endpoints.

### Workers

| Method | Endpoint                | Description              |
|--------|-------------------------|--------------------------|
| POST   | `/workers/login`        | Worker authentication    |
| GET    | `/workers/me`           | Get current worker info  |
| GET    | `/workers/shifts`       | List shifts              |

### Alerts

| Method | Endpoint                     | Description                 |
|--------|------------------------------|-----------------------------|
| GET    | `/alerts`                    | List alerts                 |
| GET    | `/alerts/active`             | Get active alerts           |
| POST   | `/alerts`                    | Create alert                |
| POST   | `/alerts/hazmat`             | Create hazmat-specific alert|
| GET    | `/alerts/reference/adr-codes`| ADR code reference          |

---

## Communication with Other Microservices

### Decision Engine → Data Module

The **Decision Engine** consumes these endpoints:

| Endpoint                              | Purpose                                    |
|---------------------------------------|--------------------------------------------|
| `POST /decisions/query-appointments`  | Query candidate appointments by gate/time  |
| `POST /decisions/process`             | Send final decision (approved/rejected)    |
| `POST /alerts/hazmat`                 | Create hazmat alerts (UN/Kemler codes)     |
| `GET /arrivals/query/license-plate/*` | Lookup appointments by detected plate      |

### API Gateway → Data Module

The **API Gateway** proxies frontend requests to:

| Endpoint                    | Consumer                    |
|-----------------------------|-----------------------------|
| `/arrivals/*`               | Operator Dashboard          |
| `/drivers/*`                | Driver Mobile App           |
| `/workers/*`                | Operator/Manager Login      |
| `/alerts/*`                 | Operator Dashboard          |

### Data Flow Diagram

```mermaid
sequenceDiagram
    participant Camera
    participant DE as Decision Engine
    participant DM as Data Module
    participant GW as API Gateway
    participant FE as Frontend

    Camera->>DE: License Plate Detection
    DE->>DM: POST /decisions/query-appointments
    DM-->>DE: Candidate Appointments
    DE->>DE: Evaluate (ML Agents)
    DE->>DM: POST /decisions/process
    DM->>DM: Update Appointment + Create Alerts
    DM-->>DE: Confirmation
    DE->>GW: Kafka Event (decision-results)
    GW->>FE: WebSocket Broadcast
```

### Arrival Verification Flow

Detailed flow when a truck arrives at the port gate:

```mermaid
sequenceDiagram
    participant CAM as Camera/Sensor
    participant AB as Agent B (LP Detection)
    participant AC as Agent C (Hazmat Detection)
    participant DE as Decision Engine
    participant DM as Data Module
    participant REDIS as Redis Cache
    participant PG as PostgreSQL
    participant MONGO as MongoDB

    Note over CAM,MONGO: 1. Detection Phase
    CAM->>AB: Video Stream Frame
    AB->>AB: OCR License Plate
    AB->>DE: Detection Event (plate, confidence)
    
    CAM->>AC: Video Stream Frame
    AC->>AC: Detect Hazmat Placards
    AC->>DE: Hazmat Event (UN code, Kemler)

    Note over CAM,MONGO: 2. Query Phase
    DE->>DM: POST /decisions/query-appointments
    DM->>REDIS: Check cache
    REDIS-->>DM: Cache miss
    DM->>PG: Query appointments (gate, time window, status)
    PG-->>DM: Candidate appointments list
    DM->>REDIS: Cache result
    DM-->>DE: Appointments with cargo details

    Note over CAM,MONGO: 3. Decision Phase
    DE->>DE: Match plate to appointment
    DE->>DE: Validate hazmat vs booking
    DE->>DE: Compute final decision

    Note over CAM,MONGO: 4. Persist Phase
    DE->>DM: POST /decisions/process
    DM->>REDIS: Check duplicate (idempotency)
    DM->>PG: UPDATE appointment status
    DM->>PG: INSERT alert (if hazmat)
    DM->>MONGO: INSERT detection event
    DM-->>DE: Decision confirmed

    Note over CAM,MONGO: 5. Notification Phase
    DE->>DE: Publish to Kafka
```

### Operator Dashboard Flow

How the gate operator dashboard receives real-time updates:

```mermaid
sequenceDiagram
    participant OP as Operator Browser
    participant FE as Frontend App
    participant GW as API Gateway
    participant WS as WebSocket Server
    participant DM as Data Module
    participant KF as Kafka

    Note over OP,KF: 1. Initial Load
    OP->>FE: Open Dashboard
    FE->>GW: GET /arrivals/next/{gate_id}
    GW->>DM: Proxy request
    DM-->>GW: Upcoming arrivals list
    GW-->>FE: JSON response
    FE->>OP: Render arrivals table

    Note over OP,KF: 2. WebSocket Connection
    FE->>GW: WS Connect /ws/gate/{gate_id}
    GW->>WS: Upgrade connection
    WS-->>FE: Connected

    Note over OP,KF: 3. Real-time Updates
    KF->>GW: Kafka message (decision-results-{gate_id})
    GW->>GW: Parse decision payload
    GW->>WS: Broadcast to gate channel
    WS->>FE: Push decision event
    FE->>OP: Update UI (new arrival, alert badge)

    Note over OP,KF: 4. Manual Actions
    OP->>FE: Click "Approve Entry"
    FE->>GW: POST /arrivals/{id}/decision
    GW->>DM: Proxy request
    DM->>DM: Update appointment status
    DM-->>GW: Updated appointment
    GW-->>FE: Success response
    FE->>OP: Show confirmation
```

### Driver Mobile App Flow

Complete driver journey from login to unloading assignment (with token authentication):

```mermaid
sequenceDiagram
    participant DR as Driver Mobile App
    participant GW as API Gateway
    participant DM as Data Module
    participant DB as PostgreSQL
    participant DE as Decision Engine
    participant CAM as Gate Camera

    Note over DR,CAM: 1. Authentication & Route
    DR->>GW: POST /drivers/login (license, password)
    GW->>DM: Forward request
    DM->>DB: Validate credentials
    DM->>DB: Generate & store session_token
    DM->>DB: Set current_appointment_id (next in queue)
    DM-->>GW: {token, driver_info}
    GW-->>DR: Store token locally
    
    DR->>GW: GET /drivers/me/today
    Note over DR: Header: Authorization: Bearer <token>
    GW->>DM: Forward with auth header
    DM->>DB: Validate token + Get appointments
    DM-->>GW: Appointments list
    GW-->>DR: Show scheduled arrivals
    
    DR->>DR: Navigate to port (GPS route)

    Note over DR,CAM: 2. Arrival at Gate
    DR->>DR: Approaching gate
    CAM->>DE: Detect license plate
    DE->>DM: POST /decisions/query-appointments
    DM-->>DE: Match appointment found
    
    Note over DR,CAM: 3. Automatic Access Decision
    DE->>DE: Validate booking + hazmat check
    DE->>DM: POST /decisions/process (approved)
    DM->>DM: UPDATE appointment status = in_process
    DM-->>DE: Confirmation

    Note over DR,CAM: 4. Real-time Status Update
    DE->>GW: Kafka (decision-results)
    GW->>DR: Push notification (WebSocket/FCM)
    DR->>DR: Show "Access Granted"
    
    DR->>GW: GET /drivers/me/active (with Bearer token)
    GW->>DM: Forward with auth header
    DM->>DB: Validate token + Get active appointment
    DM-->>GW: Appointment + Terminal + Dock info
    GW-->>DR: Display assignment

    Note over DR,CAM: 5. Claim (if manual entry)
    DR->>GW: POST /drivers/claim {arrival_id: "PRT-0001"}
    Note over DR: Header: Authorization: Bearer <token>
    GW->>DM: Forward with auth header
    DM->>DB: Validate token
    DM->>DB: Check sequential order (is this the next delivery?)
    alt Next in queue
        DM->>DB: UPDATE driver.current_appointment_id
        DM-->>GW: Appointment claimed
        GW-->>DR: Show navigation to dock
    else Not next in queue
        DM-->>GW: Error: Complete previous delivery first
        GW-->>DR: Show error message
    end

    Note over DR,CAM: 6. Unloading & Completion
    DR->>DR: Show dock location on map
    DR->>DR: Navigate to assigned dock
    DR->>DR: Unload cargo
    DR->>GW: Complete delivery
    GW->>DM: UPDATE status = completed
    DM->>DB: Advance to next appointment in queue
    DM-->>GW: Confirmation + next appointment
    GW-->>DR: Show "Delivery Complete" + next delivery info
```

---

## Development

### Run Without Docker

```bash
cd src/Data_Module

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables (or create .env file)
export POSTGRES_HOST=localhost
export MONGO_URL=mongodb://admin:admin123@localhost:27017
export REDIS_HOST=localhost

# Start server
uvicorn main:app --reload --port 8000
```

### Run Tests

```bash
# Using the test script
./test_api.sh all

# Using pytest
pytest tests/test_integration.py -v
```

---

## Key Features

- **Background Scheduler**: Automatically updates `in_transit` to `delayed` status for overdue appointments (15-minute tolerance (standard in industry), runs every 5 minutes)
- **Hazmat Detection**: Full ADR/UN and Kemler code reference for dangerous goods alerts
- **Health Checks**: Comprehensive readiness probes for all database connections
- **CORS Enabled**: Accepts requests from any origin (configure for production)
