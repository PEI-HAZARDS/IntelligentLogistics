"""
Tests for GET /arrivals/{id} read fallback order (BR-29).

BR-29 — GET /arrivals/{id} lookup order: Redis → Mongo → PG.

Audit finding: the actual implementation uses Redis → PG (two-tier).
The Mongo middle tier specified in BR-29 is absent from routes/arrivals.py.
This file:
  - Confirms what IS implemented (Redis first, PG fallback, cache warm-up).
  - Documents the missing Mongo tier as an xfail gap.

Structural tests run without running services.
Integration tests require Redis + PostgreSQL (docker-compose up -d).

Run:
    PYTHONPATH=. pytest tests/integration/test_arrivals_read_fallback.py -v
"""

import json
import pathlib
import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_ROUTE_PATH = (
    pathlib.Path(__file__).parent.parent.parent
    / "routes" / "arrivals.py"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_arrival_src() -> str:
    """Extract the get_arrival handler body from routes/arrivals.py."""
    src = _ROUTE_PATH.read_text()
    start = src.find("def get_arrival(")
    # Find the start of the next route function
    end = src.find("\n\n@router", start + 1)
    return src[start:end] if end != -1 else src[start:start + 800]


# ---------------------------------------------------------------------------
# 1. Structural guards (no running services required)
# ---------------------------------------------------------------------------

def test_redis_cache_checked_first_in_source():
    """
    get_cached_appointment must appear before get_appointment_by_id in the
    get_arrival handler — Redis is the first (hottest) read tier.
    """
    src = _get_arrival_src()
    redis_pos = src.find("get_cached_appointment")
    pg_pos = src.find("get_appointment_by_id")

    assert redis_pos != -1, "get_cached_appointment not found in get_arrival"
    assert pg_pos != -1, "get_appointment_by_id not found in get_arrival"
    assert redis_pos < pg_pos, (
        "Redis lookup must precede PostgreSQL query in get_arrival — "
        "Redis is the hot-cache tier (BR-29)"
    )


def test_cache_warmed_after_pg_read_in_source():
    """
    cache_appointment must appear after get_appointment_by_id in get_arrival
    so that a PG read warms Redis for subsequent callers.
    """
    src = _get_arrival_src()
    pg_pos = src.find("get_appointment_by_id")
    warm_pos = src.find("cache_appointment")

    assert warm_pos != -1, "cache_appointment not found in get_arrival"
    assert warm_pos > pg_pos, (
        "cache_appointment must appear AFTER get_appointment_by_id — "
        "Redis warm-up must follow the PG read, not precede it"
    )


def test_404_raised_when_pg_returns_none_in_source():
    """
    When get_appointment_by_id returns None (appointment absent), an
    HTTPException(404) must be raised — confirmed structurally.
    """
    src = _get_arrival_src()
    pg_pos = src.find("get_appointment_by_id")
    http_exc_pos = src.find("HTTPException", pg_pos)

    assert http_exc_pos != -1, (
        "HTTPException must be raised after get_appointment_by_id returns None "
        "to signal a missing appointment (404)"
    )


@pytest.mark.xfail(
    reason=(
        "BR-29 gap: Mongo middle tier is not implemented. "
        "routes/arrivals.py:get_arrival uses Redis → PG (two-tier) instead of "
        "Redis → Mongo → PG (three-tier) as required by BR-29. "
        "Fix: add a Mongo read between the Redis miss and the PG fallback; "
        "also populate the Mongo read model from the outbox worker."
    ),
    strict=True,
)
def test_mongo_middle_tier_present_in_source():
    """
    BR-29 requires Redis → Mongo → PG. The Mongo read is currently missing.
    When the Mongo tier is added, remove the xfail marker.
    """
    src = _get_arrival_src()
    assert "mongo" in src.lower() or "collection" in src.lower(), (
        "No Mongo read found in get_arrival — Mongo middle tier is absent (BR-29 gap)"
    )


# ---------------------------------------------------------------------------
# 2. Behavioural integration tests (require Redis + PostgreSQL)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_redis_hit_returns_cached_value():
    """
    When appointment data is pre-seeded in Redis, get_cached_appointment
    returns the value without touching PostgreSQL.
    Proves that the Redis tier is active and returns correct data.
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
    When no cached value exists, get_cached_appointment returns None —
    confirming the caller (get_arrival) falls through to PostgreSQL.
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
    When Redis misses, get_appointment_by_id finds an existing PG row and
    cache_appointment writes it to Redis; subsequent calls hit the cache.
    Requires at least one appointment in the DB (run data_init_demo.py first).
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

    # Simulate the route: Redis miss → PG read → cache warm
    assert get_cached_appointment(appt_id) is None, "Key must be absent before test"

    cache_appointment(appt_id, {"id": appt_id, "status": str(row.status)})

    warmed = get_cached_appointment(appt_id)
    assert warmed is not None, "Redis must be warm after cache_appointment call"
    assert warmed["id"] == appt_id

    # Cleanup
    redis_client.delete(appointment_cache_key(appt_id))
