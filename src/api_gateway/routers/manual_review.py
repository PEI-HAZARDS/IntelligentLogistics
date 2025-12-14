from typing import Dict, Any, Optional

from fastapi import APIRouter, Body, Query, Path

from clients import internal_api_client as internal_client

router = APIRouter(tags=["manual_review"])


# ---------------------------------
# POST: /api/manual-review/{appointment_id}
# ---------------------------------
@router.post("/manual-review/{appointment_id}")
async def manual_review(
    appointment_id: int = Path(..., description="Appointment ID"),
    decision: str = Query(..., description="Decision: approved, rejected"),
    notes: Optional[str] = Query(None, description="Operator notes"),
    gate_id: Optional[int] = Query(None, description="Gate ID for visit creation"),
):
    """
    Endpoint for operator manual review.
    Proxies to POST /api/v1/decisions/manual-review/{appointment_id}
    """
    path = f"/decisions/manual-review/{appointment_id}"
    
    params = {
        "decision": decision
    }
    if notes:
        params["notes"] = notes
    if gate_id:
        params["gate_id"] = gate_id

    return await internal_client.post(path, params=params)

