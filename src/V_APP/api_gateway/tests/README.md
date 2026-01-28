# API Gateway Tests

## Structure

```
tests/
├── __init__.py
├── test_gateway.py   # Integration tests
└── README.md
```

## Running Tests

```bash
# Require API Gateway and Data Module running
docker-compose up -d
pytest tests/test_gateway.py -v
```

## Coverage

### Endpoints Tested
- **Health**: `GET /health`
- **Drivers**: login, list, get, /me/active, /me/today, /me/history, claim
- **Arrivals**: list, by ID, stats
- **Workers**: login, list
- **Alerts**: list, active

### Integration Flow
- Driver: login → view today → view active

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TEST_BASE_URL` | `http://localhost:8000/api` | API Gateway URL |
