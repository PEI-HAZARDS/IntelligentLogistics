"""
Tests for MongoDB unique index coverage (BR-37, BR-38 partial).

BR-37 (Hypothesis A) — decision_events.appointment_id must be UNIQUE
(partial filter: integer type only, so documents without appointment_id
are not constrained). This enforces the business rule "one final decision
per appointment" without preventing multiple decisions across different
appointments for the same truck over time.

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


def test_appointment_id_declared_unique_in_source():
    """
    BR-37 (Hypothesis A): mongo.py must declare a unique partial index on
    decision_events.appointment_id — one final decision per appointment.
    """
    src = _MONGO_SRC.read_text()
    block = _find_index_block(src, "idx_appointment")
    assert "unique=True" in block, (
        "decision_events.appointment_id index must have unique=True (BR-37 Hypothesis A)"
    )
    assert "partialFilterExpression" in block, (
        "idx_appointment must use partialFilterExpression so NULL appointment_id "
        "documents (detections without a matched appointment) are not constrained"
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
def test_appointment_id_unique_enforced(mongo_test_db):
    """
    BR-37 (Hypothesis A): two decision_events with the same appointment_id
    (integer) must raise DuplicateKeyError — one decision per appointment.
    Documents without appointment_id are not constrained (partial index).
    """
    from pymongo import ASCENDING
    from pymongo.errors import DuplicateKeyError

    col = mongo_test_db["decision_events_br37_test"]
    col.drop()
    col.create_index(
        [("appointment_id", ASCENDING)],
        unique=True,
        partialFilterExpression={"appointment_id": {"$type": "int"}},
    )

    col.insert_one({"appointment_id": 9001, "truck_id": "truck-A", "decision": "ALLOW"})

    with pytest.raises(DuplicateKeyError):
        col.insert_one({"appointment_id": 9001, "truck_id": "truck-A", "decision": "DENY"})


@pytest.mark.integration
def test_different_appointments_same_truck_allowed(mongo_test_db):
    """
    BR-37 (Hypothesis A): two decision_events for the SAME truck but different
    appointments must be allowed — a truck visits the port multiple times.
    """
    from pymongo import ASCENDING
    col = mongo_test_db["decision_events_br37_test"]
    col.drop()
    col.create_index(
        [("appointment_id", ASCENDING)],
        unique=True,
        partialFilterExpression={"appointment_id": {"$type": "int"}},
    )

    col.insert_one({"appointment_id": 9002, "truck_id": "truck-B", "decision": "ALLOW"})
    col.insert_one({"appointment_id": 9003, "truck_id": "truck-B", "decision": "ALLOW"})


@pytest.mark.integration
def test_no_appointment_id_documents_not_constrained(mongo_test_db):
    """
    BR-37 (Hypothesis A): documents without appointment_id (detections not yet
    matched to an appointment) must not conflict with each other.
    """
    from pymongo import ASCENDING
    col = mongo_test_db["decision_events_br37_test"]
    col.drop()
    col.create_index(
        [("appointment_id", ASCENDING)],
        unique=True,
        partialFilterExpression={"appointment_id": {"$type": "int"}},
    )

    col.insert_one({"truck_id": "truck-C", "decision": "PENDING"})
    col.insert_one({"truck_id": "truck-C", "decision": "PENDING"})


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
