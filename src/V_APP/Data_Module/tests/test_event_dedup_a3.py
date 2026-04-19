"""
Test A3 — Verify event dedup uses event_id instead of time-window.

Checks:
1. redis.py exposes is_duplicate_event(event_id) function.
2. decision_queries.is_duplicate_and_mark accepts event_id keyword arg.
3. decision_queries.process_incoming_decision accepts event_id keyword arg.
4. DecisionIncomingRequest schema includes event_id field.
5. Route passes event_id to process_incoming_decision.
6. Legacy time-window dedup still exists (backward compat) but is deprecated.
"""

import pytest
from pathlib import Path

SRC = Path(__file__).parent.parent

REDIS_PATH = SRC / "infrastructure" / "persistence" / "redis.py"
DECISION_QUERIES_PATH = SRC / "application" / "queries" / "decision_queries.py"
DECISIONS_ROUTE_PATH = SRC / "routes" / "decisions.py"


def _read(path: Path) -> str:
    return path.read_text()


# =================================================================
# 1. redis.py exposes is_duplicate_event
# =================================================================

@pytest.mark.unit
class TestRedisDedupEventId:
    """redis.py must provide event-id based dedup."""

    def test_is_duplicate_event_defined(self):
        source = _read(REDIS_PATH)
        assert "def is_duplicate_event(" in source

    def test_is_duplicate_event_uses_event_id_key(self):
        source = _read(REDIS_PATH)
        assert "dedup:event:" in source, (
            "is_duplicate_event must use 'dedup:event:{event_id}' key pattern"
        )

    def test_is_duplicate_event_uses_set_nx(self):
        source = _read(REDIS_PATH)
        # Find the is_duplicate_event function body
        func_start = source.index("def is_duplicate_event(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        assert "nx=True" in func_body, (
            "is_duplicate_event must use SET NX for atomic check-and-set"
        )

    def test_legacy_is_duplicate_and_mark_still_exists(self):
        source = _read(REDIS_PATH)
        assert "def is_duplicate_and_mark(" in source, (
            "Legacy time-window dedup must be preserved for backward compat"
        )

    def test_legacy_marked_deprecated(self):
        source = _read(REDIS_PATH)
        func_start = source.index("def is_duplicate_and_mark(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        assert "deprecated" in func_body.lower(), (
            "Legacy is_duplicate_and_mark should be marked as deprecated"
        )


# =================================================================
# 2. decision_queries.is_duplicate_and_mark accepts event_id
# =================================================================

@pytest.mark.unit
class TestDecisionQueriesDedupEventId:
    """decision_queries.is_duplicate_and_mark must accept event_id kwarg."""

    def test_is_duplicate_and_mark_accepts_event_id(self):
        source = _read(DECISION_QUERIES_PATH)
        func_start = source.index("def is_duplicate_and_mark(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        assert "event_id" in func_body, (
            "is_duplicate_and_mark must accept event_id parameter"
        )

    def test_prefers_event_id_over_time_window(self):
        source = _read(DECISION_QUERIES_PATH)
        func_start = source.index("def is_duplicate_and_mark(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        # event_id check must come before time_bucket fallback
        event_id_pos = func_body.index("event_id")
        assert "time_bucket" in func_body, "Must still have time_bucket fallback"
        time_bucket_pos = func_body.index("time_bucket")
        assert event_id_pos < time_bucket_pos, (
            "event_id check must come before time_bucket fallback"
        )

    def test_imports_event_id_dedup_from_redis(self):
        source = _read(DECISION_QUERIES_PATH)
        assert "is_duplicate_event" in source, (
            "decision_queries must import is_duplicate_event from redis"
        )

    def test_logs_warning_on_legacy_fallback(self):
        source = _read(DECISION_QUERIES_PATH)
        func_start = source.index("def is_duplicate_and_mark(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        assert "warning" in func_body.lower() or "logger.warn" in func_body, (
            "Must log warning when falling back to legacy time-window dedup"
        )


# =================================================================
# 3. process_incoming_decision accepts event_id
# =================================================================

@pytest.mark.unit
class TestProcessIncomingDecisionEventId:
    """process_incoming_decision must accept and forward event_id."""

    def test_accepts_event_id_parameter(self):
        source = _read(DECISION_QUERIES_PATH)
        func_start = source.index("def process_incoming_decision(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        assert "event_id" in func_body, (
            "process_incoming_decision must accept event_id parameter"
        )

    def test_passes_event_id_to_dedup(self):
        source = _read(DECISION_QUERIES_PATH)
        func_start = source.index("def process_incoming_decision(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        assert "event_id=event_id" in func_body or "event_id=event_id" in func_body.replace(" ", ""), (
            "process_incoming_decision must pass event_id to is_duplicate_and_mark"
        )

    def test_no_variable_name_collision(self):
        """event_id param must not be overwritten before the dedup call."""
        source = _read(DECISION_QUERIES_PATH)
        func_start = source.index("def process_incoming_decision(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]

        if "is_duplicate_and_mark" not in func_body:
            return  # dedup not present — nothing to check

        before_dedup = func_body.split("is_duplicate_and_mark")[0]
        # Strip the function signature (which contains "event_id: Optional") from the check
        after_signature = before_dedup.split("event_id: Optional", 1)[-1]
        # If event_id is reassigned before dedup, it shadows the parameter.
        # The code must either use a distinct name (mongo_event_id) or not reassign.
        assert "mongo_event_id" in func_body or "event_id =" not in after_signature, (
            "event_id must not be re-assigned before the is_duplicate_and_mark call — "
            "use a different variable name (e.g. mongo_event_id) for the Mongo persist ID."
        )


# =================================================================
# 4. DecisionIncomingRequest has event_id field
# =================================================================

@pytest.mark.unit
class TestDecisionRequestEventId:
    """DecisionIncomingRequest must expose event_id field."""

    def test_event_id_field_in_schema(self):
        source = _read(DECISIONS_ROUTE_PATH)
        # Find DecisionIncomingRequest class body
        class_start = source.index("class DecisionIncomingRequest")
        next_class = source.index("\nclass ", class_start + 1)
        class_body = source[class_start:next_class]
        assert "event_id" in class_body, (
            "DecisionIncomingRequest must have event_id field"
        )

    def test_event_id_is_optional(self):
        source = _read(DECISIONS_ROUTE_PATH)
        class_start = source.index("class DecisionIncomingRequest")
        next_class = source.index("\nclass ", class_start + 1)
        class_body = source[class_start:next_class]
        assert "Optional[str]" in class_body or "str] = None" in class_body, (
            "event_id must be optional for backward compatibility"
        )


# =================================================================
# 5. Route passes event_id to process_incoming_decision
# =================================================================

@pytest.mark.unit
class TestRoutePassesEventId:
    """decisions.py process_decision must pass event_id through."""

    def test_route_passes_event_id(self):
        source = _read(DECISIONS_ROUTE_PATH)
        # Find process_decision function
        func_start = source.index("def process_decision(")
        next_func_candidates = [
            source.index(m, func_start + 1)
            for m in ["\ndef ", "\nclass ", "\n@router"]
            if m in source[func_start + 1:]
        ]
        next_func = min(next_func_candidates) if next_func_candidates else len(source)
        func_body = source[func_start:next_func]
        assert "event_id" in func_body, (
            "process_decision route must pass event_id to process_incoming_decision"
        )
