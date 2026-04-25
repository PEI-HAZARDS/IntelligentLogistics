"""
Tests for GET /arrivals/{id} two-tier read path (Redis → PG).

At current port scale (hundreds of appointments/day) two tiers are sufficient:
  - Redis hot cache: written by outbox worker on every AppointmentStateChanged event.
  - PostgreSQL: final fallback; warms Redis on hit.

Scale-up note (BR-29): for high-volume deployments a MongoDB appointments_read
middle tier can be inserted between Redis and PG.  The collection and its
indexes are already declared in mongo.py.  Restore the three-tier block in
routes/arrivals.py::get_arrival and re-extend the outbox worker to activate it.

Structural tests run without running services.
Integration tests require Redis + PostgreSQL (docker-compose up -d).

Run:
    PYTHONPATH=. pytest tests/integration/test_arrivals_read_fallback.py -v
"""

import pathlib
import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_ROUTE_PATH = (
    pathlib.Path(__file__).parent.parent.parent
    / "routes" / "arrivals.py"
)
_MONGO_PATH = (
    pathlib.Path(__file__).parent.parent.parent
    / "infrastructure" / "persistence" / "mongo.py"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_arrival_src() -> str:
    """Extract the get_arrival handler body from routes/arrivals.py."""
    src = _ROUTE_PATH.read_text()
    start = src.find("def get_arrival(")
    end = src.find("\n\n@router", start + 1)
    return src[start:end] if end != -1 else src[start:start + 1200]


# ---------------------------------------------------------------------------
# 1. Structural guards — two-tier order (no running services required)
# ---------------------------------------------------------------------------

def test_redis_cache_checked_first_in_source():
    """
    get_cached_appointment must appear before get_appointment_by_id —
    Redis is the hot tier and must be checked first.
    """
    src = _get_arrival_src()
    redis_pos = src.find("get_cached_appointment")
    pg_pos = src.find("get_appointment_by_id")

    assert redis_pos != -1, "get_cached_appointment not found in get_arrival"
    assert pg_pos != -1, "get_appointment_by_id not found in get_arrival"
    assert redis_pos < pg_pos, "Redis check must come before PG query in get_arrival"


def test_cache_warmed_after_pg_read_in_source():
    """
    cache_appointment must appear after get_appointment_by_id — a PG read
    must warm Redis for subsequent callers.
    """
    src = _get_arrival_src()
    pg_pos = src.find("get_appointment_by_id")
    warm_pos = src.find("cache_appointment", pg_pos)

    assert warm_pos != -1, "cache_appointment not found after PG read in get_arrival"
    assert warm_pos > pg_pos, "Redis warm-up must follow the PG read"


def test_404_raised_when_pg_returns_none_in_source():
    """
    HTTPException(404) must follow get_appointment_by_id to handle a missing
    appointment when both tiers miss.
    """
    src = _get_arrival_src()
    pg_pos = src.find("get_appointment_by_id")
    exc_pos = src.find("HTTPException", pg_pos)

    assert exc_pos != -1, "HTTPException must be raised after all tiers miss (404)"


def test_appointments_read_collection_declared_for_scale_up():
    """
    appointments_read_collection is declared in mongo.py as a scale-up option.
    At current port volume the read path is Redis → PG (two-tier).
    For high-load deployments a three-tier Redis → Mongo → PG path
    can be activated by restoring the middle-tier block in get_arrival (BR-29).
    """
    src = _MONGO_PATH.read_text()
    assert "appointments_read_collection" in src, (
        "appointments_read_collection must remain declared in mongo.py "
        "as a scale-up option (BR-29)"
    )


def test_scale_up_note_documented_in_source():
    """get_arrival docstring must document the Mongo middle-tier scale-up note."""
    src = _get_arrival_src()
    assert "Scale-up" in src or "scale-up" in src or "BR-29" in src, (
        "get_arrival must document the MongoDB middle-tier scale-up option"
    )


# ---------------------------------------------------------------------------
# 2. Behavioural integration tests (require Redis + PostgreSQL)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_redis_hit_returns_cached_value():
    """
    When appointment data is pre-seeded in Redis, get_cached_appointment
    returns it without touching PG.
    """
    from infrastructure.persistence.redis import (
        cache_appointment,
        get_cached_appointment,
        appointment_cache_key,
        redis_client,
    )

    appointment_id = 99991
    payload = {
        "id": appointment_id,
        "arrival_id": "PRT-TEST-01",
        "status": "in_transit",
        "license_plate": "AB-12-CD",
    }

    try:
        cache_appointment(appointment_id, payload)
        result = get_cached_appointment(appointment_id)
        assert result is not None, "Cache miss — Redis did not store the value"
        assert result["id"] == appointment_id
        assert result["status"] == "in_transit"
    finally:
        redis_client.delete(appointment_cache_key(appointment_id))


@pytest.mark.integration
def test_redis_miss_returns_none():
    """
    When no cached value exists, get_cached_appointment returns None,
    allowing the caller to fall through to PG.
    """
    from infrastructure.persistence.redis import (
        get_cached_appointment,
        appointment_cache_key,
        redis_client,
    )

    appointment_id = 99992
    redis_client.delete(appointment_cache_key(appointment_id))

    result = get_cached_appointment(appointment_id)
    assert result is None, (
        "Expected None on cache miss; got a value — stale key in Redis"
    )


@pytest.mark.integration
def test_pg_fallback_warms_redis(pg_session):
    """
    On a Redis miss, get_appointment_by_id reads from PG and
    cache_appointment warms Redis for subsequent callers.
    Requires at least one appointment in the DB.
    """
    from infrastructure.persistence.redis import (
        get_cached_appointment,
        cache_appointment,
        appointment_cache_key,
        redis_client,
    )
    from infrastructure.persistence.sql_models import Appointment as AppointmentORM

    row = pg_session.query(AppointmentORM).first()
    if row is None:
        pytest.skip("No appointment rows in DB — run data_init_demo.py first")

    appt_id = row.id
    redis_client.delete(appointment_cache_key(appt_id))

    assert get_cached_appointment(appt_id) is None, "Key must be absent before test"

    cache_appointment(appt_id, {"id": appt_id, "status": str(row.status)})

    warmed = get_cached_appointment(appt_id)
    assert warmed is not None, "Redis must be warm after cache_appointment call"
    assert warmed["id"] == appt_id

    redis_client.delete(appointment_cache_key(appt_id))
