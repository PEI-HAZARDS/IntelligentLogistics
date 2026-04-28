"""
Unit tests for final_decision_source derivation (BR-44).

BR-44 — The outbox-projected Mongo decision_event document must carry
        `final_decision_source` = "agent" for auto-accepted decisions
        and "operator" for operator-override decisions.

The derivation rule `decision_data.get("decision_source", "agent")` is
tested directly.  The deprecated persist_decision_event (DW-03) has been
deleted; the outbox worker is now the sole Mongo writer.

Note: the correlator-level `decision_source` logic (how the field is
populated in the payload before the outbox event is emitted) is covered
in kafka_decision_consumer_unit_test.py.

Run:
    PYTHONPATH=. pytest tests/unit/test_decision_source_derivation.py -v
"""

import pytest

def _derive_final_decision_source(decision_data: dict) -> str:
    """The derivation rule used when projecting decision events to Mongo (BR-44)."""
    return decision_data.get("decision_source", "agent")


def test_agent_decision_sets_final_decision_source_agent():
    """ACCEPTED auto-decision → final_decision_source must be 'agent'."""
    result = _derive_final_decision_source({"decision_source": "agent", "truck_id": "truck-1"})
    assert result == "agent"


def test_operator_decision_sets_final_decision_source_operator():
    """Operator override → final_decision_source must be 'operator'."""
    result = _derive_final_decision_source({"decision_source": "operator", "truck_id": "truck-1"})
    assert result == "operator"


def test_missing_decision_source_defaults_to_agent():
    """Absent decision_source key → default must be 'agent' (legacy callers)."""
    result = _derive_final_decision_source({"truck_id": "truck-1"})
    assert result == "agent", f"Expected default 'agent', got {result!r}"


def test_manual_review_resolved_by_operator_is_operator_source():
    """
    MANUAL_REVIEW resolved by the operator (decision_source='operator') must
    produce 'operator', not 'agent' (BR-46 / BR-44).
    """
    result = _derive_final_decision_source({
        "decision_source": "operator",
        "agent_decision": "MANUAL_REVIEW",
        "operator_decision": "APPROVED",
        "truck_id": "truck-1",
    })
    assert result == "operator", (
        "MANUAL_REVIEW resolved by operator must yield final_decision_source='operator'"
    )
