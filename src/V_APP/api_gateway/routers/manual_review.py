from typing import Dict, Any, Optional

from fastapi import APIRouter, Body, Query, Path
from loguru import logger

from clients import internal_api_client as internal_client
from realtime.kafka_producer import publish_manual_review_decision

router = APIRouter(tags=["manual_review"])


# ---------------------------------
# POST: /api/manual-review/reject-entrance
# IMPORTANT: This route MUST come before the parameterized route
# ---------------------------------
@router.post("/manual-review/reject-entrance")
async def reject_entrance(
    gate_id: int = Query(..., description="Gate ID"),
    license_plate: Optional[str] = Query(None, description="Detected license plate"),
    notes: Optional[str] = Query(None, description="Operator notes"),
):
    """
    Reject an entrance without selecting a specific appointment.
    This is used when the operator wants to deny entry to a truck
    that doesn't match any known appointment.
    
    Only publishes to Kafka - no database update since there's no appointment.
    """
    # Publish rejection to Kafka for Driver UI notification
    if license_plate:
        published = await publish_manual_review_decision(
            gate_id=gate_id,
            appointment_id=0,  # No appointment
            license_plate=license_plate,
            decision="rejected",
            notes=notes or "Entry denied - no matching appointment",
        )
        if published:
            logger.info(f"Entrance rejection published to Kafka: gate={gate_id}, plate={license_plate}")
        else:
            logger.warning(f"Failed to publish entrance rejection to Kafka")
    else:
        logger.info(f"Entrance rejected at gate {gate_id} - no license plate to notify")

    return {"status": "rejected", "message": "Entrance denied"}


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
    # Original detection data to preserve in the Kafka broadcast
    original_un: Optional[str] = Query(None, description="Original UN number from detection"),
    original_kemler: Optional[str] = Query(None, description="Original Kemler code from detection"),
    original_lp_crop: Optional[str] = Query(None, description="Original license plate crop URL"),
    original_hz_crop: Optional[str] = Query(None, description="Original hazmat crop URL"),
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
            # Pass through original detection data
            original_un=original_un,
            original_kemler=original_kemler,
            original_lp_crop=original_lp_crop,
            original_hz_crop=original_hz_crop,
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
