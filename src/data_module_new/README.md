# Port Logistics Backend

FastAPI backend for Port Logistics Management System.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your PostgreSQL credentials

# Run migrations
alembic upgrade head

# Start development server
uvicorn app.main:app --reload
```

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI application
│   ├── core/                # Config, database, security
│   ├── models/              # SQLAlchemy models
│   ├── schemas/             # Pydantic schemas
│   ├── repositories/        # Data access layer
│   ├── services/            # Business logic
│   └── api/v1/              # REST endpoints
├── alembic/                 # Database migrations
├── requirements.txt
└── .env.example
```

## Alembic Commands

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1

# Show current revision
alembic current
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `SECRET_KEY` | JWT signing key | Required |
| `ALGORITHM` | JWT algorithm | HS256 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token validity | 30 |
| `AI_CONFIDENCE_THRESHOLD` | Auto-correction threshold | 0.85 |

## API Endpoints

### Authentication
- `POST /api/v1/auth/login` - Worker login
- `GET /api/v1/auth/me` - Current user info

### Trucks & Drivers
- `GET/POST /api/v1/trucks`
- `GET /api/v1/trucks/{id}`
- `GET /api/v1/trucks/plate/{plate}`
- `GET/POST /api/v1/drivers`

### Appointments
- `POST /api/v1/appointments`
- `GET /api/v1/appointments/{id}`
- `PUT /api/v1/appointments/{id}/confirm`
- `GET /api/v1/appointments/{id}/window`

### Gates & Visits
- `POST /api/v1/gates/{id}/check-in`
- `POST /api/v1/visits/{id}/check-out`
- `GET /api/v1/visits/{id}`
- `POST /api/v1/visits/{id}/events`

### AI Recognition
- `POST /api/v1/ai/recognitions`
- `GET /api/v1/ai/recognitions/{id}`
- `POST /api/v1/ai/corrections`

### Telemetry
- `POST /api/v1/telemetry/metrics`

# Run PostgreSQL with PostGIS (needed for geo_polygon field)
docker run -d \
  --name port_logistics_db \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=port_logistics \
  -p 5432:5432 \
  postgis/postgis:16-3.4