import time
import logging
from typing import Optional

logger = logging.getLogger("ScaleCorrelator")


class ScaleCorrelator:
    """
    Tracks per-truck state to decide when to scale down.

    Lifecycle of a truck:
        1. truck-detected       → register truck, mark scale-up sent
        2. lp-results received  → mark LP done
        3. hz-results received  → mark HZ done
        4. agent-decision OR (LP+HZ both done) → ready to scale down + reset
        5. timeout exceeded     → force scale down + reset

    State per truck_id:
        {
            "gate_id": str,    # which gate this truck belongs to
            "lp": bool,        # LP results received
            "hz": bool,        # HZ results received
            "decided": bool,   # agent-decision received
            "ts": float,       # timestamp of truck-detected
        }
    """

    def __init__(self, timeout_seconds: int = 30) -> None:
        self._state: dict[str, dict] = {}
        self._timeout = timeout_seconds

    # ─── Registration ────────────────────────────────────────────

    def truck_detected(self, truck_id: str, gate_id: str) -> None:
        """Register a new truck. Called when truck-detected message arrives."""
        self._state[truck_id] = {
            "gate_id": gate_id,
            "lp": False,
            "hz": False,
            "decided": False,
            "ts": time.time(),
        }
        logger.info(f"Truck registered: {truck_id} (gate {gate_id})")

    def is_tracked(self, truck_id: str) -> bool:
        """Check if a truck_id is currently being tracked."""
        return truck_id in self._state

    def get_gate_id(self, truck_id: str) -> str | None:
        """Return the gate_id associated with a tracked truck."""
        state = self._state.get(truck_id)
        return state["gate_id"] if state else None

    # ─── Result Tracking ─────────────────────────────────────────

    def lp_received(self, truck_id: str) -> bool:
        """
        Mark LP results as received.
        Returns True if both LP and HZ are now complete (ready to scale down).
        """
        if truck_id not in self._state:
            logger.warning(f"LP received for unknown truck {truck_id}, ignoring")
            return False

        self._state[truck_id]["lp"] = True
        logger.debug(f"LP received for {truck_id}: state={self._state[truck_id]}")
        return self._is_results_complete(truck_id)

    def hz_received(self, truck_id: str) -> bool:
        """
        Mark HZ results as received.
        Returns True if both LP and HZ are now complete (ready to scale down).
        """
        if truck_id not in self._state:
            logger.warning(f"HZ received for unknown truck {truck_id}, ignoring")
            return False

        self._state[truck_id]["hz"] = True
        logger.debug(f"HZ received for {truck_id}: state={self._state[truck_id]}")
        return self._is_results_complete(truck_id)

    def decision_received(self, truck_id: str) -> bool:
        """
        Mark that agent-decision was received for this truck.
        Returns True (always ready to scale down after a decision).
        """
        if truck_id not in self._state:
            logger.warning(f"Decision for unknown truck {truck_id}, ignoring")
            return False

        self._state[truck_id]["decided"] = True
        logger.info(f"Decision received for {truck_id}")
        return True

    # ─── Timeout ─────────────────────────────────────────────────

    def check_timeouts(self) -> list[str]:
        """
        Returns list of truck_ids that have exceeded the timeout
        without completing results or receiving a decision.
        """
        now = time.time()
        timed_out = []
        for truck_id, state in list(self._state.items()):  # NOSONAR
            if now - state["ts"] > self._timeout:
                logger.warning(
                    f"Truck {truck_id} timed out after {self._timeout}s "
                    f"(lp={state['lp']}, hz={state['hz']}, decided={state['decided']})"
                )
                timed_out.append(truck_id)
        return timed_out

    # ─── Cleanup ─────────────────────────────────────────────────

    def remove(self, truck_id: str) -> None:
        """Remove a truck from tracking after scale-down + reset."""
        self._state.pop(truck_id, None)
        logger.info(f"Truck removed from tracking: {truck_id}")

    def get_state(self, truck_id: str) -> Optional[dict]:
        """Get the current state of a tracked truck (for debugging)."""
        return self._state.get(truck_id)

    @property
    def active_trucks(self) -> int:
        """Number of trucks currently being tracked."""
        return len(self._state)

    # ─── Internal ────────────────────────────────────────────────

    def _is_results_complete(self, truck_id: str) -> bool:
        """Check if both LP and HZ results have been received."""
        state = self._state.get(truck_id)
        if not state:
            return False
        return state["lp"] and state["hz"]
