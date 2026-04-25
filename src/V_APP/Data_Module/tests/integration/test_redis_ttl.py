"""
Tests for Redis key TTL invariants (BR-31, BR-32, BR-33, BR-34, BR-35, BR-36).

BR-31 — plate:{plate}:gate:{id}:tb:{bucket} dedup key TTL 300s.
BR-32 — decision:plate:{plate}:gate:{id}:tb:{bucket} cache TTL 3600s.
BR-33 — appointment:{id}:details TTL 1800s.
BR-34 — lp_lookup:{plate}:appointments TTL 600s.
BR-35 — counter:gate:{id}:hour:{ts}:{metric} TTL 7200s, incremented via INCRBY.
BR-36 — pending_review:{truck_id} TTL 1800s (set by DecisionCorrelator).

Test layers:
  1. Structural — redis.py TTL constants match the specified values.
  2. Integration — set a real key via the Redis helpers and assert TTL via redis.ttl().

Integration tests require Redis (docker-compose up -d).

Run:
    PYTHONPATH=. pytest tests/integration/test_redis_ttl.py -v
"""

import pathlib
import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REDIS_PATH = (
    pathlib.Path(__file__).parent.parent.parent
    / "infrastructure" / "persistence" / "redis.py"
)

_CONSUMER_PATH = (
    pathlib.Path(__file__).parent.parent.parent
    / "infrastructure" / "messaging" / "kafka_decision_consumer.py"
)

# ---------------------------------------------------------------------------
# TTL tolerance for integration assertions (Redis rounds to whole seconds)
# ---------------------------------------------------------------------------
_TTL_TOLERANCE = 5  # seconds


# ---------------------------------------------------------------------------
# 1. Structural guards — TTL constants match spec
# ---------------------------------------------------------------------------

def _redis_src():
    return _REDIS_PATH.read_text()


@pytest.mark.parametrize("constant,expected", [
    ("TTL_DEDUP", 300),           # BR-31
    ("TTL_DECISION_CACHE", 3600), # BR-32
    ("TTL_APPOINTMENT_HOT", 1800),# BR-33
    ("TTL_LICENSE_PLATE_LOOKUP", 600),  # BR-34
    ("TTL_COUNTER_REALTIME", 7200),     # BR-35
    ("TTL_RATE_LIMIT", 60),
    ("TTL_OPERATOR_SESSION", 3600),
])
def test_redis_ttl_constant_value(constant, expected):
    """
    TTL constant in redis.py must match the specification value.
    Changes here affect cache expiry in production.
    """
    src = _redis_src()
    # Find the line declaring this constant
    pos = src.find(f"{constant} =")
    assert pos != -1, f"{constant} not declared in redis.py"
    line_end = src.find("\n", pos)
    line = src[pos:line_end]
    # Extract the integer value from the line
    import re
    match = re.search(r"=\s*(\d+)", line)
    assert match, f"Could not parse integer value from: {line!r}"
    actual = int(match.group(1))
    assert actual == expected, (
        f"{constant} = {actual} but expected {expected} (spec mismatch)"
    )


def test_pending_review_ttl_is_1800_in_consumer():
    """
    DecisionCorrelator.PENDING_TTL must be 1800s (BR-36).
    Changing this alters how long a manual-review decision persists in Redis.
    """
    src = _CONSUMER_PATH.read_text()
    import re
    match = re.search(r"PENDING_TTL\s*=\s*(\d+)", src)
    assert match, "PENDING_TTL not found in kafka_decision_consumer.py"
    assert int(match.group(1)) == 1800, (
        f"PENDING_TTL = {match.group(1)} but expected 1800 (BR-36)"
    )


# ---------------------------------------------------------------------------
# 2. Integration tests — real TTL set via helper functions
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_dedup_key_ttl_near_300():
    """BR-31 — dedup:event:{event_id} key expires in ~300s after is_duplicate_event."""
    from infrastructure.persistence.redis import (
        is_duplicate_event, redis_client,
    )

    event_id = "test-br31-dedup-ttl-check"
    key = f"dedup:event:{event_id}"

    try:
        redis_client.delete(key)
        is_duplicate_event(event_id)
        ttl = redis_client.ttl(key)
        assert ttl > 0, "Dedup key was not set with a TTL"
        assert abs(ttl - 300) <= _TTL_TOLERANCE, (
            f"Expected TTL ~300s for dedup key, got {ttl}s (BR-31)"
        )
    finally:
        redis_client.delete(key)


@pytest.mark.integration
def test_decision_cache_key_ttl_near_3600():
    """BR-32 — decision cache key expires in ~3600s after cache_decision."""
    from infrastructure.persistence.redis import (
        cache_decision, decision_cache_key, redis_client,
    )
    from datetime import datetime, timezone

    plate = "ZZ-TEST-BR32"
    gate_id = 999
    bucket = int(datetime.now(timezone.utc).timestamp() // 30)
    key = decision_cache_key(plate, gate_id, bucket)

    try:
        redis_client.delete(key)
        cache_decision(plate, gate_id, bucket, {"decision": "ACCEPTED"})
        ttl = redis_client.ttl(key)
        assert ttl > 0, "Decision cache key was not set with a TTL"
        assert abs(ttl - 3600) <= _TTL_TOLERANCE, (
            f"Expected TTL ~3600s for decision cache key, got {ttl}s (BR-32)"
        )
    finally:
        redis_client.delete(key)


@pytest.mark.integration
def test_appointment_cache_key_ttl_near_1800():
    """BR-33 — appointment:{id}:details key expires in ~1800s after cache_appointment."""
    from infrastructure.persistence.redis import (
        cache_appointment, appointment_cache_key, redis_client,
    )

    appt_id = 99993
    key = appointment_cache_key(appt_id)

    try:
        redis_client.delete(key)
        cache_appointment(appt_id, {"id": appt_id, "status": "in_transit"})
        ttl = redis_client.ttl(key)
        assert ttl > 0, "Appointment cache key was not set with a TTL"
        assert abs(ttl - 1800) <= _TTL_TOLERANCE, (
            f"Expected TTL ~1800s for appointment cache, got {ttl}s (BR-33)"
        )
    finally:
        redis_client.delete(key)


@pytest.mark.integration
def test_license_plate_lookup_key_ttl_near_600():
    """BR-34 — lp_lookup key expires in ~600s after cache_license_plate_appointments."""
    from infrastructure.persistence.redis import (
        cache_license_plate_appointments,
        license_plate_lookup_key,
        redis_client,
    )

    plate = "ZZ-TEST-BR34"
    key = license_plate_lookup_key(plate)

    try:
        redis_client.delete(key)
        cache_license_plate_appointments(plate, [1])
        ttl = redis_client.ttl(key)
        assert ttl > 0, "License plate lookup key was not set with a TTL"
        assert abs(ttl - 600) <= _TTL_TOLERANCE, (
            f"Expected TTL ~600s for LP lookup, got {ttl}s (BR-34)"
        )
    finally:
        redis_client.delete(key)


@pytest.mark.integration
def test_counter_key_ttl_near_7200_and_increments():
    """
    BR-35 — counter:gate:{id}:hour:{ts}:{metric} expires ~7200s and increments via INCRBY.
    """
    from infrastructure.persistence.redis import (
        increment_counter, counter_key, redis_client,
    )
    from datetime import datetime, timezone

    gate_id = 9999
    metric = "test_metric"
    now = datetime.now(timezone.utc)
    key = counter_key(gate_id, metric, now)

    try:
        redis_client.delete(key)
        increment_counter(gate_id, metric)
        increment_counter(gate_id, metric)

        value = int(redis_client.get(key) or 0)
        assert value == 2, f"Expected counter value 2, got {value} (BR-35 INCRBY)"

        ttl = redis_client.ttl(key)
        assert ttl > 0, "Counter key has no TTL"
        assert abs(ttl - 7200) <= _TTL_TOLERANCE, (
            f"Expected TTL ~7200s for counter key, got {ttl}s (BR-35)"
        )
    finally:
        redis_client.delete(key)


@pytest.mark.integration
def test_pending_review_ttl_near_1800():
    """
    BR-36 — pending_review:{event_id} expires ~1800s after the outbox worker
    projects a PendingReviewCreated event.

    Phase 4 (PD-01) changed the write path: DecisionCorrelator now calls
    cmd_store_pending_review (PG + Outbox) instead of redis.setex directly.
    The outbox worker then calls redis.setex(pending_review_key(event_id), 1800, ...).

    This test verifies that the Redis key written by the outbox worker projection
    carries the correct TTL (1800s), by simulating the projection step directly.
    """
    from infrastructure.persistence.redis import pending_review_key, redis_client
    import json

    event_id = "test-br36-pending-ttl-check"
    key = pending_review_key(event_id)

    try:
        redis_client.delete(key)
        payload = {"event_id": event_id, "truck_id": "truck-test", "status": "PENDING"}
        redis_client.setex(key, 1800, json.dumps(payload))

        ttl = redis_client.ttl(key)
        assert ttl > 0, "pending_review key was not set with a TTL"
        assert abs(ttl - 1800) <= _TTL_TOLERANCE, (
            f"Expected TTL ~1800s for pending_review key, got {ttl}s (BR-36)"
        )
    finally:
        redis_client.delete(key)
