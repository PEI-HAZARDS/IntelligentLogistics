"""
Unit tests for final_decision_source derivation (BR-44).

BR-44 — The persisted Mongo decision_event document must carry
        `final_decision_source` = "agent" for auto-accepted decisions
        and "operator" for operator-override decisions.

Two layers tested here:

  1. Structural — persist_decision_event source confirms the mapping
     `decision_data.get("decision_source", "agent")` → `final_decision_source`.

  2. Unit — persist_decision_event called with mocked Mongo collection;
     the document passed to insert_one is inspected for the correct field.

Note: the correlator-level `decision_source` logic (how the field is
populated in the payload before persist_decision_event is called) is
already covered in kafka_decision_consumer_unit_test.py.

Run:
    PYTHONPATH=. pytest tests/unit/test_decision_source_derivation.py -v
"""

import sys
import pathlib
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DQ_PATH = (
    pathlib.Path(__file__).parent.parent.parent
    / "application" / "queries" / "decision_queries.py"
)


# ---------------------------------------------------------------------------
# 1. Structural guard
# ---------------------------------------------------------------------------

def test_final_decision_source_reads_from_decision_source_key():
    """
    persist_decision_event must derive final_decision_source from
    decision_data.get("decision_source", "agent").
    Structural check: the exact expression appears in the source.
    """
    src = _DQ_PATH.read_text()

    # Locate persist_decision_event function
    start = src.find("def persist_decision_event")
    end = src.find("\ndef ", start + 1)
    fn_src = src[start:end] if end != -1 else src[start:]

    assert "final_decision_source" in fn_src, (
        "persist_decision_event must set final_decision_source in the document"
    )
    assert 'decision_data.get("decision_source"' in fn_src or \
           "decision_data.get('decision_source'" in fn_src, (
        "final_decision_source must be derived from decision_data['decision_source']"
    )


def test_default_decision_source_is_agent_in_source():
    """
    When decision_source is absent, the default must be 'agent' —
    confirming auto-accepted decisions are attributed to the agent.
    """
    src = _DQ_PATH.read_text()
    start = src.find("def persist_decision_event")
    end = src.find("\ndef ", start + 1)
    fn_src = src[start:end] if end != -1 else src[start:]

    assert '"agent"' in fn_src or "'agent'" in fn_src, (
        "The default value for final_decision_source must be 'agent' "
        "so that auto-accepted events are correctly attributed"
    )


# ---------------------------------------------------------------------------
# Module-level mock setup — patch Mongo + Redis + notification_queries
# before decision_queries is imported.
# ---------------------------------------------------------------------------

def _get_decision_queries():
    """
    Import decision_queries with all infrastructure dependencies mocked.
    Returns the module.  Safe to call multiple times (sys.modules caches).
    """
    # Infrastructure mocks
    _mongo_mod = MagicMock()
    _redis_mod = MagicMock()
    _notif_mod = MagicMock()

    sys.modules.setdefault("infrastructure.persistence.mongo", _mongo_mod)
    sys.modules.setdefault("infrastructure.persistence.redis", _redis_mod)
    sys.modules.setdefault("application.queries.notification_queries", _notif_mod)

    import application.queries.decision_queries as dq
    return dq


# ---------------------------------------------------------------------------
# 2. Behavioural unit tests
# ---------------------------------------------------------------------------

def test_agent_decision_sets_final_decision_source_agent():
    """
    When decision_data carries decision_source='agent' (ACCEPTED path),
    the document built by persist_decision_event must have
    final_decision_source='agent'.
    """
    dq = _get_decision_queries()

    captured = {}

    def fake_insert_one(doc):
        captured.update(doc)
        m = MagicMock()
        m.inserted_id = "fake-id"
        return m

    with patch.object(dq, "decision_events_collection") as mock_col, \
         patch.object(dq, "validate_decision_event_schema", return_value=True), \
         patch.object(dq, "increment_counter"):
        mock_col.insert_one.side_effect = fake_insert_one

        dq.persist_decision_event(
            license_plate="AB-12-CD",
            gate_id=1,
            appointment_id=42,
            decision="approved",
            decision_data={"decision_source": "agent", "truck_id": "truck-1"},
        )

    assert captured.get("final_decision_source") == "agent", (
        f"Expected final_decision_source='agent', got {captured.get('final_decision_source')!r}"
    )


def test_operator_decision_sets_final_decision_source_operator():
    """
    When decision_data carries decision_source='operator' (operator override),
    the document must have final_decision_source='operator'.
    """
    dq = _get_decision_queries()

    captured = {}

    def fake_insert_one(doc):
        captured.update(doc)
        m = MagicMock()
        m.inserted_id = "fake-id"
        return m

    with patch.object(dq, "decision_events_collection") as mock_col, \
         patch.object(dq, "validate_decision_event_schema", return_value=True), \
         patch.object(dq, "increment_counter"):
        mock_col.insert_one.side_effect = fake_insert_one

        dq.persist_decision_event(
            license_plate="AB-12-CD",
            gate_id=1,
            appointment_id=42,
            decision="approved",
            decision_data={"decision_source": "operator", "truck_id": "truck-1"},
        )

    assert captured.get("final_decision_source") == "operator", (
        f"Expected final_decision_source='operator', got {captured.get('final_decision_source')!r}"
    )


def test_missing_decision_source_defaults_to_agent():
    """
    When decision_source is absent from decision_data (e.g. legacy callers),
    final_decision_source must default to 'agent'.
    """
    dq = _get_decision_queries()

    captured = {}

    def fake_insert_one(doc):
        captured.update(doc)
        m = MagicMock()
        m.inserted_id = "fake-id"
        return m

    with patch.object(dq, "decision_events_collection") as mock_col, \
         patch.object(dq, "validate_decision_event_schema", return_value=True), \
         patch.object(dq, "increment_counter"):
        mock_col.insert_one.side_effect = fake_insert_one

        dq.persist_decision_event(
            license_plate="AB-12-CD",
            gate_id=1,
            appointment_id=42,
            decision="approved",
            decision_data={"truck_id": "truck-1"},  # no decision_source key
        )

    assert captured.get("final_decision_source") == "agent", (
        f"Expected default 'agent', got {captured.get('final_decision_source')!r}"
    )


def test_manual_review_resolved_by_operator_is_operator_source():
    """
    MANUAL_REVIEW resolved by the operator (decision_source='operator')
    must produce final_decision_source='operator', not 'agent'.
    This covers the MANUAL_REVIEW → operator approval path (BR-46 / BR-44).
    """
    dq = _get_decision_queries()

    captured = {}

    def fake_insert_one(doc):
        captured.update(doc)
        m = MagicMock()
        m.inserted_id = "fake-id"
        return m

    with patch.object(dq, "decision_events_collection") as mock_col, \
         patch.object(dq, "validate_decision_event_schema", return_value=True), \
         patch.object(dq, "increment_counter"):
        mock_col.insert_one.side_effect = fake_insert_one

        dq.persist_decision_event(
            license_plate="AB-12-CD",
            gate_id=1,
            appointment_id=42,
            decision="approved",
            decision_data={
                "decision_source": "operator",
                "agent_decision": "MANUAL_REVIEW",
                "operator_decision": "APPROVED",
                "truck_id": "truck-1",
            },
        )

    assert captured.get("final_decision_source") == "operator", (
        "MANUAL_REVIEW resolved by operator must set final_decision_source='operator'"
    )
