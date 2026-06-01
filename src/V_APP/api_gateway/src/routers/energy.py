from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query

from clients import internal_api_client as internal_client
from auth.token_validator import require_role, TokenPayload

router = APIRouter(tags=["energy"])


# ---------------------------------
# GET: /api/energy/spikes
# Proxy to the Data Module energy-spike telemetry (read-only).
# ---------------------------------
@router.get("/energy/spikes")
async def get_energy_spikes(
    _user: Annotated[TokenPayload, Depends(require_role("operator", "manager"))],
    gate_id: Annotated[Optional[int], Query(description="Filter by gate")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    """Recent energy spikes for the simulated energy graph, newest first."""
    params: dict = {"limit": limit}
    if gate_id is not None:
        params["gate_id"] = gate_id
    return await internal_client.get("/energy/spikes", params=params)
