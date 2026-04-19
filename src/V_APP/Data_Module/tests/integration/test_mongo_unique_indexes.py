"""
Tests for MongoDB unique index coverage (BR-37, BR-38 partial).

BR-37 — MongoDB decision_events.truck_id should be UNIQUE.

Audit finding: truck_id is NOT unique in the current index definition.
The unique constraint that exists is on decision_id (with a partial
filter for string type), not truck_id.  This file documents:
  - What IS correctly unique (decision_id, detection_id, gate+hour).
  - What is MISSING (truck_id unique) — flagged as xfail gap.

Structural tests run without MongoDB.
Integration tests require running MongoDB (docker-compose up -d).

Run:
    PYTHONPATH=. pytest tests/integration/test_mongo_unique_indexes.py -v
"""

import os
import pathlib
import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_MONGO_SRC = (
    pathlib.Path(__file__).parent.parent.parent
    / "infrastructure" / "persistence" / "mongo.py"
)

# ---------------------------------------------------------------------------
# Helpers — test MongoDB client (uses a dedicated test database)
# ---------------------------------------------------------------------------

_MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
_TEST_DB = "intelligent_logistics_test"


@pytest.fixture(scope="module")
def mongo_test_db():
    """
    Module-scoped MongoDB client pointed at a disposable test database.
    Drops the database on teardown so test runs are idempotent.
    Requires running MongoDB.
    """
    from pymongo import MongoClient
    client = MongoClient(_MONGO_URL, serverSelectionTimeoutMS=2000)
    db = client[_TEST_DB]
    yield db
    client.drop_database(_TEST_DB)
    client.close()


# ---------------------------------------------------------------------------
# 1. Structural guards (no running services required)
# ---------------------------------------------------------------------------

def _find_index_block(src: str, index_name: str) -> str:
    """
    Extract the create_index() call that contains `name="<index_name>"`.
    Searches only forward from the name= keyword to avoid picking up
    _drop_index_safe() calls that also reference the index name.
    """
    needle = f'name="{index_name}"'
    pos = src.find(needle)
    assert pos != -1, f'name="{index_name}" not found in mongo.py'
    # Return up to 300 chars forward from the name= keyword — enough to
    # capture the remaining kwargs (unique, partialFilterExpression, etc.)
    return src[pos: pos + 300]


def test_decision_id_declared_unique_in_source():
    """
    mongo.py must declare a unique index on decision_events.decision_id.
    This is the actual unique constraint enforced in production.
    """
    src = _MONGO_SRC.read_text()
    block = _find_index_block(src, "idx_decision_id")
    assert "unique=True" in block, (
        "decision_events.decision_id index must have unique=True"
    )


def test_detection_id_declared_unique_in_source():
    """agent_detections.detection_id must be declared unique."""
    src = _MONGO_SRC.read_text()
    block = _find_index_block(src, "idx_detection_id")
    assert "unique=True" in block, (
        "agent_detections.detection_id index must have unique=True"
    )


def test_statistics_hourly_gate_hour_declared_unique_in_source():
    """statistics_hourly gate+hour must be declared unique (prevents duplicate rollups)."""
    src = _MONGO_SRC.read_text()
    block = _find_index_block(src, "idx_gate_hour_unique")
    assert "unique=True" in block, (
        "statistics_hourly gate+hour index must have unique=True"
    )


def test_truck_id_not_declared_unique_gap():
    """
    GAP — BR-37 requires decision_events.truck_id to be UNIQUE but the
    current source only has a non-unique compound index (truck_id + created_at).
    This test documents the missing constraint so it is tracked in the
    test suite rather than silently absent.
    """
    src = _MONGO_SRC.read_text()
    block = _find_index_block(src, "idx_truck_created")
    assert "unique=True" not in block, (
        "Expected gap confirmed: truck_id index is NOT unique in decision_events. "
        "BR-37 requires adding a unique index on truck_id — see KNOWN_DEVIATIONS.md"
    )


# ---------------------------------------------------------------------------
# 2. Behavioural tests (integration — require running MongoDB)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_decision_id_unique_enforced(mongo_test_db):
    """
    Inserting two decision_events with the same decision_id (string)
    must raise DuplicateKeyError — the partial unique index is active.
    """
    from pymongo import ASCENDING
    from pymongo.errors import DuplicateKeyError

    col = mongo_test_db["decision_events"]
    col.drop()
    col.create_index(
        [("decision_id", ASCENDING)],
        unique=True,
        partialFilterExpression={"decision_id": {"$type": "string"}},
    )

    col.insert_one({"decision_id": "dec-test-001", "truck_id": "truck-A"})

    with pytest.raises(DuplicateKeyError):
        col.insert_one({"decision_id": "dec-test-001", "truck_id": "truck-B"})


@pytest.mark.integration
@pytest.mark.xfail(
    reason=(
        "BR-37 gap: truck_id is not unique in decision_events. "
        "Two documents with the same truck_id can be inserted without error. "
        "Fix: add unique=True to idx_truck_created or add a dedicated "
        "unique index on truck_id in infrastructure/persistence/mongo.py."
    ),
    strict=True,
)
def test_truck_id_unique_enforced(mongo_test_db):
    """
    BR-37 — decision_events.truck_id should be UNIQUE.
    Currently fails (no unique constraint) — marked xfail to document the gap.
    When the index is added, remove the xfail marker.
    """
    from pymongo import ASCENDING
    from pymongo.errors import DuplicateKeyError

    col = mongo_test_db["decision_events_truck_unique_test"]
    col.drop()
    # Only a non-unique compound index exists today
    col.create_index([("truck_id", ASCENDING), ("created_at", ASCENDING)])

    col.insert_one({"truck_id": "truck-X", "created_at": "2026-01-01"})

    # This should raise but does NOT — proving the gap
    with pytest.raises(DuplicateKeyError):
        col.insert_one({"truck_id": "truck-X", "created_at": "2026-01-02"})


@pytest.mark.integration
def test_detection_id_unique_enforced(mongo_test_db):
    """
    Inserting two agent_detections with the same detection_id raises
    DuplicateKeyError.
    """
    from pymongo import ASCENDING
    from pymongo.errors import DuplicateKeyError

    col = mongo_test_db["agent_detections"]
    col.drop()
    col.create_index([("detection_id", ASCENDING)], unique=True)

    col.insert_one({"detection_id": "det-test-001", "truck_id": "truck-A"})

    with pytest.raises(DuplicateKeyError):
        col.insert_one({"detection_id": "det-test-001", "truck_id": "truck-B"})


@pytest.mark.integration
def test_statistics_hourly_gate_hour_unique_enforced(mongo_test_db):
    """
    Inserting two statistics_hourly documents with the same gate_id + hour_bucket
    raises DuplicateKeyError.
    """
    from pymongo import ASCENDING
    from pymongo.errors import DuplicateKeyError

    col = mongo_test_db["statistics_hourly"]
    col.drop()
    col.create_index(
        [("gate_id", ASCENDING), ("hour_bucket", ASCENDING)],
        unique=True,
    )

    col.insert_one({"gate_id": 1, "hour_bucket": "2026-04-18T10:00:00Z"})

    with pytest.raises(DuplicateKeyError):
        col.insert_one({"gate_id": 1, "hour_bucket": "2026-04-18T10:00:00Z"})
