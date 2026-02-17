from typing import Dict, Any, Optional, List

from fastapi import APIRouter, Body, Query, Path, Depends # type: ignore
from loguru import logger # type: ignore

from clients import internal_api_client as internal_client
from dependencies import get_kafka_producer, get_produce_topic
from shared.src.kafka_wrapper import KafkaProducerWrapper
from shared.src.kafka_protocol import DecisionResultsMessage
router = APIRouter(tags=["manual_review"])


# ---------------------------------
# POST: /api/manual-review
# ---------------------------------
@router.post("/manual-review/")
async def produce_manual_review(
    kafka_producer: KafkaProducerWrapper = Depends(get_kafka_producer),
    produce_topic: str = Depends(get_produce_topic),
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
):
    """
    Propagate a manual decision to kafka, which will be consumed by the Data Module and stored in the database.
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
    
    logger.info(f"Propagating manual review decision for {license_plate}: {decision} (reason: {decision_reason})")

    kafka_producer.produce(
        topic=produce_topic,
        data=msg.to_dict(),
        key=license_plate,
    )

    return {"status": decision, "message": f"Decision '{decision}' propagated"}