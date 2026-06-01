"""
Energy/RAN spike telemetry routes.

Stores one document per scale_up spike (timestamped) and serves recent spikes to
the simulated energy graph so spikes survive a page refresh. This is telemetry,
not a domain event, so it writes MongoDB directly (same pattern as notifications)
— no Outbox / Unit of Work involved.
"""

from typing import Annotated, List, Optional, Union
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from infrastructure.persistence.mongo import record_energy_spike, get_energy_spikes

__all__ = ["router"]

router = APIRouter(prefix="/energy", tags=["Energy"])


class EnergySpikeIn(BaseModel):
    gate_id: int
    value: float = Field(..., description="Power reading (kW) at the spike")
    mode: str = "scale_up"
    # ISO-8601 string, or an epoch number (seconds or milliseconds). Accepting the
    # numeric form avoids dropping spikes whose caller forwards a raw Kafka
    # Message timestamp (epoch-ms int). Defaults to now (UTC).
    timestamp: Optional[Union[str, int, float]] = None


class EnergySpikeOut(BaseModel):
    gate_id: int
    value: float
    mode: str
    timestamp: str


def _parse_ts(raw: Optional[Union[str, int, float]]) -> datetime:
    if raw is None or raw == "":
        return datetime.now(timezone.utc)
    # Numeric epoch (seconds or milliseconds — our Kafka messages use ms).
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        seconds = raw / 1000.0 if raw > 1e12 else float(raw)
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            return datetime.now(timezone.utc)
    try:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


@router.post("/spikes", response_model=EnergySpikeOut)
def create_energy_spike(payload: EnergySpikeIn):
    """Record a single energy spike (called by the API Gateway on scale_up)."""
    return record_energy_spike(
        gate_id=payload.gate_id,
        value=payload.value,
        mode=payload.mode,
        timestamp=_parse_ts(payload.timestamp),
    )


@router.get("/spikes", response_model=List[EnergySpikeOut])
def list_energy_spikes(
    gate_id: Annotated[Optional[int], Query(description="Filter by gate")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    """Recent energy spikes, newest first."""
    return get_energy_spikes(gate_id=gate_id, limit=limit)
