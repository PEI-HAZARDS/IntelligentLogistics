from typing import Dict, Any, Optional

from fastapi import APIRouter, Body, Query, Path
from loguru import logger

from clients import internal_api_client as internal_client
from realtime.kafka_producer import publish_manual_review_decision

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
    license_plate: Optional[str] = Query(None, description="License plate for Kafka notification"),
):
    """
    Endpoint for operator manual review.
    
    1. Proxies to Data Module to update appointment status
    2. Publishes decision to Kafka for real-time Driver UI notification
    """
    path = f"/decisions/manual-review/{appointment_id}"
    
    params = {
        "decision": decision
    }
    if notes:
        params["notes"] = notes
    if gate_id:
        params["gate_id"] = gate_id

    # 1. Process the decision via Data Module
    result = await internal_client.post(path, params=params)
    
    # 2. Publish to Kafka for real-time WebSocket broadcast to Driver UI
    if gate_id and license_plate:
        published = await publish_manual_review_decision(
            gate_id=gate_id,
            appointment_id=appointment_id,
            license_plate=license_plate,
            decision=decision,
            notes=notes,
        )
        if published:
            logger.info(f"Manual review decision published to Kafka: {appointment_id} -> {decision}")
        else:
            logger.warning(f"Failed to publish manual review to Kafka for appointment {appointment_id}")
    else:
        logger.debug(
            f"Skipping Kafka publish for manual review: "
            f"gate_id={gate_id}, license_plate={license_plate}"
        )

    return result
