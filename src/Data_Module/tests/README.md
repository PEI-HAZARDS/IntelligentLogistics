# Data Module Tests

## Structure

```
tests/
├── conftest.py           # Shared fixtures (mock_db, mock_driver, etc.)
├── test_integration.py   # Integration tests (require running services)
└── test_services.py      # Unit tests with mocks
```

## Running Tests

```bash
# Unit tests (no services required)
pytest tests/test_services.py -v

# Integration tests (require services running)
docker-compose up -d
pytest tests/test_integration.py -v
```

## Coverage

### Unit Tests (`test_services.py`)
- Driver authentication (not found, inactive, success)
- Appointment claims (invalid PIN)
- Arrival queries (empty, by ID)
- Worker authentication
- Alert queries and reference codes (ADR, Kemler)

### Integration Tests (`test_integration.py`)
- Health check
- Arrivals: list, stats, by ID, by PIN, by plate, status update
- Drivers: login, list, get, active, today, history, claim
- Workers: login, list, operators, managers, dashboard
- Alerts: list, active, stats, create, resolve
- Decisions: query, detection events, process, manual review
- Complete flows: driver, operator, decision

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TEST_BASE_URL` | `http://localhost:8080/api/v1` | Data Module API URL |
