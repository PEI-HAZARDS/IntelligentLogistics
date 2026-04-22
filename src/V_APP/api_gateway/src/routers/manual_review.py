from typing import Annotated, Optional, List

from fastapi import APIRouter, Query, Depends # type: ignore
from loguru import logger # type: ignore
from pydantic import BaseModel

from dependencies import get_kafka_producer, get_ws_manager
from shared.src.kafka_wrapper import KafkaProducerWrapper
from shared.src.kafka_protocol import DecisionResultsMessage, KafkaTopicFactory
from web_socket_manager import WebSocketManager
from auth.token_validator import require_role, TokenPayload

router = APIRouter(tags=["manual_review"], dependencies=[Depends(require_role("operator", "manager"))])


class ManualReviewParams(BaseModel):
    license_plate: str
    license_crop_url: str = ""
    un: str = ""
    kemler: str = ""
    hazard_crop_url: str = ""
    route: str = ""
    decision: str
    decision_reason: str
    alerts: Optional[List[str]] = None
    decision_source: str = "operator"
    truck_id: Optional[str] = None


# ---------------------------------
# POST: /api/manual-review
# ---------------------------------
@router.post("/manual-review/")
async def produce_manual_review(
    kafka_producer: Annotated[KafkaProducerWrapper, Depends(get_kafka_producer)],
    ws_manager: Annotated[WebSocketManager, Depends(get_ws_manager)],
    gate_id: Annotated[str, Query(description="Gate ID the operator is working on")],
    params: Annotated[ManualReviewParams, Depends()],
    alerts: Annotated[Optional[List[str]], Query(description="Manual review alerts")] = None,
    frontend_alerts: Annotated[Optional[List[str]], Query(alias="alerts[]", description="Axios-style alerts array")] = None,
):
    """
    Propagate a manual decision to kafka, which will be consumed by the Data Module and stored in the database.
    The gate_id is provided by the frontend and used to route the message to the correct operator-decision topic.
    """
    request_alerts = alerts if alerts is not None else frontend_alerts

    msg = DecisionResultsMessage(
        license_plate=params.license_plate,
        license_crop_url=params.license_crop_url,
        un=params.un,
        kemler=params.kemler,
        hazard_crop_url=params.hazard_crop_url,
        alerts=request_alerts or params.alerts or [],
        route=params.route,
        decision=params.decision,
        decision_reason=params.decision_reason,
        decision_source=params.decision_source,
    )

    # Build the correct topic for this gate
    produce_topic = KafkaTopicFactory.operator_decision(gate_id)

    logger.info(f"Propagating manual review decision for {params.license_plate}: {params.decision} "
                f"(reason: {params.decision_reason}) to topic '{produce_topic}'")

    if params.truck_id is not None:
        kafka_producer.produce(
            topic=produce_topic,
            data=msg.to_dict(),
            headers={"truckId": params.truck_id}
        )
    else:
        kafka_producer.produce(
            topic=produce_topic,
            data=msg.to_dict(),
        )

    # Broadcast the decision to connected WebSocket clients for this gate
    ws_payload = msg.to_dict()
    ws_payload["truck_id"] = params.truck_id

    await ws_manager.broadcast(gate_id, ws_payload)
    logger.info(f"Manual review decision broadcast via WebSocket for gate '{gate_id}'")

    return {"status": params.decision, "message": f"Decision '{params.decision}' propagated"}
