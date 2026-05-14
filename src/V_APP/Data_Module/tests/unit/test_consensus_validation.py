"""
Unit tests for detection schema validation / consensus rules (BR-18).

BR-18 — Consensus inserts deteccao_valida only after confidence/origin
         validation.  In the Data Module, this is implemented partially:
         `validate_agent_detection_schema` in infrastructure/persistence/mongo.py
         checks required fields and valid agent_type but does NOT enforce a
         minimum confidence threshold or an origin ∈ {IA, Manual} check.

This file:
  - Tests the implemented validation (required fields, agent_type).
  - Documents the confidence-threshold gap as xfail.
  - Documents the origin validation gap as xfail.

No running services required — mongo.py validators are pure Python.

Run:
    PYTHONPATH=. pytest tests/unit/test_consensus_validation.py -v
"""

import sys
import pathlib
import pytest

_MONGO_PATH = (
    pathlib.Path(__file__).parent.parent.parent
    / "infrastructure" / "persistence" / "mongo.py"
)


def _load_validators():
    """
    Load validate_agent_detection_schema and validate_decision_event_schema
    from mongo.py without executing module-level Mongo connection code.
    We extract and exec only the validator functions.
    """
    src = _MONGO_PATH.read_text()

    # Extract validate_agent_detection_schema function
    agent_start = src.find("def validate_agent_detection_schema")
    agent_end = src.find("\ndef ", agent_start + 1)
    agent_src = src[agent_start:agent_end] if agent_end != -1 else src[agent_start:]

    # Extract validate_decision_event_schema function
    decision_start = src.find("def validate_decision_event_schema")
    decision_end = src.find("\ndef ", decision_start + 1)
    decision_src = src[decision_start:decision_end] if decision_end != -1 else src[decision_start:]

    ns = {}
    # Both functions use logger; provide a no-op
    import logging
    ns["logger"] = logging.getLogger("test_consensus")
    exec(agent_src, ns)
    exec(decision_src, ns)
    return ns["validate_agent_detection_schema"], ns["validate_decision_event_schema"]


@pytest.fixture(scope="module")
def validators():
    return _load_validators()


# ---------------------------------------------------------------------------
# 1. validate_agent_detection_schema — implemented checks
# ---------------------------------------------------------------------------

def _valid_detection_doc():
    from datetime import datetime, timezone
    return {
        "detection_id": "det-001",
        "truck_id": "truck-1",
        "agent_type": "AgentB",
        "gate_id": 1,
        "timestamp": datetime.now(timezone.utc),
        "detection_data": {"license_plate": "AB-12-CD", "confidence": 0.92},
    }


def test_valid_detection_passes(validators):
    """A fully valid detection document must pass schema validation."""
    validate_agent, _ = validators
    assert validate_agent(_valid_detection_doc()) is True


@pytest.mark.parametrize("missing_field", [
    "detection_id", "truck_id", "agent_type", "gate_id", "timestamp", "detection_data",
])
def test_missing_required_field_fails(validators, missing_field):
    """Removing any required field must cause schema validation to return False."""
    validate_agent, _ = validators
    doc = _valid_detection_doc()
    del doc[missing_field]
    assert validate_agent(doc) is False, (
        f"Missing '{missing_field}' must fail schema validation (BR-18)"
    )


@pytest.mark.parametrize("invalid_agent", ["AgentD", "agent_a", "", "Unknown", "AI"])
def test_invalid_agent_type_fails(validators, invalid_agent):
    """agent_type must be one of {AgentA, AgentB, AgentC}; others fail (BR-18)."""
    validate_agent, _ = validators
    doc = _valid_detection_doc()
    doc["agent_type"] = invalid_agent
    assert validate_agent(doc) is False, (
        f"agent_type='{invalid_agent}' must fail validation (BR-18)"
    )


@pytest.mark.parametrize("valid_agent", ["AgentA", "AgentB", "AgentC"])
def test_valid_agent_types_accepted(validators, valid_agent):
    """agent_type ∈ {AgentA, AgentB, AgentC} must pass validation."""
    validate_agent, _ = validators
    doc = _valid_detection_doc()
    doc["agent_type"] = valid_agent
    assert validate_agent(doc) is True


# ---------------------------------------------------------------------------
# 2. Quality gates — confidence threshold and origin validation (BR-18)
# ---------------------------------------------------------------------------

def test_low_confidence_detection_fails(validators):
    """BR-18: detection with confidence < 0.5 must fail validation."""
    validate_agent, _ = validators
    doc = _valid_detection_doc()
    doc["detection_data"]["confidence"] = 0.01
    assert validate_agent(doc) is False, (
        "Confidence 0.01 is below minimum threshold — must be rejected (BR-18)"
    )


def test_high_confidence_detection_passes(validators):
    """BR-18: detection with confidence ≥ 0.5 must pass validation."""
    validate_agent, _ = validators
    doc = _valid_detection_doc()
    doc["detection_data"]["confidence"] = 0.5
    assert validate_agent(doc) is True


def test_invalid_origin_detection_fails(validators):
    """BR-18: detection with origin ∉ {IA, Manual} must fail validation."""
    validate_agent, _ = validators
    doc = _valid_detection_doc()
    doc["origin"] = "UNKNOWN_ORIGIN"
    assert validate_agent(doc) is False, (
        "origin='UNKNOWN_ORIGIN' must be rejected (BR-18)"
    )


def test_valid_origin_ia_passes(validators):
    """BR-18: detection with origin='IA' must pass validation."""
    validate_agent, _ = validators
    doc = _valid_detection_doc()
    doc["origin"] = "IA"
    assert validate_agent(doc) is True


def test_valid_origin_manual_passes(validators):
    """BR-18: detection with origin='Manual' must pass validation."""
    validate_agent, _ = validators
    doc = _valid_detection_doc()
    doc["origin"] = "Manual"
    assert validate_agent(doc) is True


def test_absent_origin_passes(validators):
    """BR-18: detection without origin field must pass (origin is optional)."""
    validate_agent, _ = validators
    doc = _valid_detection_doc()
    doc.pop("origin", None)
    assert validate_agent(doc) is True
