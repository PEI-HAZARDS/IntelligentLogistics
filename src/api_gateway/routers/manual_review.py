from typing import Dict, Any, Optional

from fastapi import APIRouter, Body, Query, Path

from ..clients import internal_api_client as internal_client

router = APIRouter(tags=["manual_review"])


# ---------------------------------
# POST: /api/manual-review/{appointment_id}
# ---------------------------------
@router.post("/manual-review/{appointment_id}")
async def manual_review(
    appointment_id: int = Path(..., description="Appointment ID"),
    decision: str = Query(..., description="Decision: approved, rejected"),
    notes: Optional[str] = Query(None, description="Operator notes"),
):
    """
    Endpoint for operator manual review.
    Proxies to POST /api/v1/decisions/manual-review/{appointment_id}
    """
    path = f"/decisions/manual-review/{appointment_id}"
    
    # DM expects decision and notes as query params in the URL?
    # Checking Data Module routes/decisions.py:
    # manual_review(..., decision: str = Query(...), notes: str = Query(...))
    
    params = {
        "decision": decision
    }
    if notes:
        params["notes"] = notes

    return await internal_client.post(path, params=params)
