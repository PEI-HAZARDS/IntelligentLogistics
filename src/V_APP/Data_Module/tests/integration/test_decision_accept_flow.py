"""
Structural guard for BR-46 — operator-gated state transition.

BR-46 — Appointment transitions to IN_PROCESS ONLY after the operator
decision is processed; the agent-side MANUAL_REVIEW must not trigger
the transition.

This is enforced structurally in KafkaDecisionConsumer._consume_loop:
    final_decision = correlator.process_agent_decision(...)
    if final_decision:                     # ← None for MANUAL_REVIEW
        dispatched = await self._dispatch_container_moved(...)

The guard below reads the consumer source to verify this ordering is
intact.  If someone moves the dispatch call outside the guard, the test
fails before any runtime regression occurs.

Run:
    PYTHONPATH=. pytest tests/integration/test_decision_accept_flow.py -v
"""

import pathlib


_CONSUMER_PATH = (
    pathlib.Path(__file__).parent.parent.parent
    / "infrastructure" / "messaging" / "kafka_decision_consumer.py"
)


def _consume_loop_src() -> str:
    src = _CONSUMER_PATH.read_text()
    start = src.find("async def _consume_loop")
    end = src.find("\n    async def ", start + 1)
    return src[start:end] if end != -1 else src[start:]


def test_dispatch_is_gated_on_final_decision_for_agent_topic():
    """
    In _consume_loop, _dispatch_container_moved must only be called inside
    an 'if final_decision:' block for agent-decision topics.
    MANUAL_REVIEW causes process_agent_decision to return None, so
    final_decision is falsy and the dispatch is skipped.
    """
    src = _consume_loop_src()

    # Confirm process_agent_decision is called
    assert "process_agent_decision" in src

    # Confirm _dispatch_container_moved is called
    assert "_dispatch_container_moved" in src

    # The dispatch call must follow an 'if final_decision' guard
    guard_pos = src.find("if final_decision")
    dispatch_pos = src.find("_dispatch_container_moved")

    assert guard_pos != -1, (
        "_consume_loop must have an 'if final_decision' guard before dispatching"
    )
    assert dispatch_pos > guard_pos, (
        "_dispatch_container_moved must appear AFTER the 'if final_decision' guard — "
        "a MANUAL_REVIEW (which returns None) must never trigger a state transition"
    )


def test_operator_decision_also_gated():
    """
    The same 'if final_decision' guard must apply to the operator-decision
    branch.  process_operator_decision can also return None when no pending
    agent decision exists; the dispatch must be skipped in that case too.
    """
    src = _consume_loop_src()

    assert "process_operator_decision" in src

    operator_pos = src.find("process_operator_decision")
    dispatch_pos = src.find("_dispatch_container_moved", operator_pos)
    guard_pos = src.find("if final_decision", operator_pos)

    # There must be a guard between the operator call and the dispatch
    assert guard_pos != -1, (
        "An 'if final_decision' guard must exist after process_operator_decision"
    )
    assert dispatch_pos > guard_pos, (
        "_dispatch_container_moved must appear after the guard for the operator branch"
    )
