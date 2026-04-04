from typing import Optional, List

from fastapi import APIRouter, Query, Depends # type: ignore
from loguru import logger # type: ignore

from dependencies import get_kafka_producer, get_ws_manager
from shared.src.kafka_wrapper import KafkaProducerWrapper
from shared.src.kafka_protocol import DecisionResultsMessage, KafkaTopicFactory
from web_socket_manager import WebSocketManager
from auth.token_validator import require_role, TokenPayload

router = APIRouter(tags=["manual_review"], dependencies=[Depends(require_role("operator", "manager"))])


# ---------------------------------
# POST: /api/manual-review
# ---------------------------------
@router.post("/manual-review/")
async def produce_manual_review(
    kafka_producer: KafkaProducerWrapper = Depends(get_kafka_producer),
    ws_manager: WebSocketManager = Depends(get_ws_manager),
    gate_id: str = Query(..., description="Gate ID the operator is working on"),
    license_plate: str = Query(..., description="Detected license plate"),
    license_crop_url: str = Query("", description="License plate crop URL"),
    un: str = Query("", description="UN number"),
    kemler: str = Query("", description="Kemler code"),
    hazard_crop_url: str = Query("", description="Hazard plate crop URL"),
    alerts: Optional[List[str]] = Query(None, description="List of alerts"),
    route: str = Query("", description="Assigned route"),
    decision: str = Query(..., description="Decision: approved or rejected"),
    decision_reason: str = Query(..., description="Reason for the decision"),
    decision_source: str = Query("operator", description="Source of the decision"),
    truck_id: Optional[str] = Query(None, description="ID of the truck, if available"),
):
    """
    Propagate a manual decision to kafka, which will be consumed by the Data Module and stored in the database.
    The gate_id is provided by the frontend and used to route the message to the correct operator-decision topic.
    """
    msg = DecisionResultsMessage(
        license_plate=license_plate,
        license_crop_url=license_crop_url,
        un=un,
        kemler=kemler,
        hazard_crop_url=hazard_crop_url,
        alerts=alerts or [],
        route=route,
        decision=decision,
        decision_reason=decision_reason,
        decision_source=decision_source,
    )

    # Build the correct topic for this gate
    produce_topic = KafkaTopicFactory.operator_decision(gate_id)
    
    logger.info(f"Propagating manual review decision for {license_plate}: {decision} "
                f"(reason: {decision_reason}) to topic '{produce_topic}'")
    
    if truck_id is not None:
        kafka_producer.produce(
            topic=produce_topic,
            data=msg.to_dict(),
            headers={"truckId": truck_id}
        )
    else:
        kafka_producer.produce(
            topic=produce_topic,
            data=msg.to_dict(),
        )

    # Broadcast the decision to connected WebSocket clients for this gate
    ws_payload = msg.to_dict()
    ws_payload["truck_id"] = truck_id
    
    await ws_manager.broadcast(gate_id, ws_payload)
    logger.info(f"Manual review decision broadcast via WebSocket for gate '{gate_id}'")

    return {"status": decision, "message": f"Decision '{decision}' propagated"}