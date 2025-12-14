import asyncio
import json
import re
from typing import Optional

from aiokafka import AIOKafkaConsumer
from loguru import logger

from config import settings
from .hub import decisions_hub
from clients import internal_api_client as internal_client

# Task global para podermos arrancar o consumer no startup
_consumer_task: Optional[asyncio.Task] = None


def _extract_gate_id_from_topic(topic: str) -> Optional[str]:
    """
    Extrai o gate_id do nome do tópico Kafka.
    
    Exemplo: 'decision-results-1' -> '1'
             'decision-results-42' -> '42'
    """
    match = re.search(r'-(\d+)$', topic)
    if match:
        return match.group(1)
    return None


async def _persist_decision(payload: dict, gate_id: Optional[str]) -> None:
    """
    Persists the decision to the database via Data Module API.
    
    For ACCEPTED decisions:
    - Updates Appointment.status to 'in_process'
    - Creates Visit with state='unloading'
    """
    decision = payload.get("decision", "").upper()
    license_plate = payload.get("licensePlate", "")
    
    # Extract appointment_id from route object (required for status update)
    route = payload.get("route") or {}
    appointment_id = route.get("appointment_id")
    
    if decision not in ("ACCEPTED", "REJECTED"):
        logger.debug(f"Decision '{decision}' does not require DB persistence (MANUAL_REVIEW)")
        return
    
    if not license_plate or license_plate == "N/A":
        logger.warning("Cannot persist decision: no valid license plate")
        return
    
    if not appointment_id:
        logger.warning(f"Cannot persist decision: no appointment_id in payload for plate={license_plate}")
        return
    
    try:
        # Call Data Module to process the decision
        # This updates Appointment.status and optionally creates Visit
        path = "/decisions/process"
        body = {
            "license_plate": license_plate,
            "gate_id": int(gate_id) if gate_id else (route.get("gate_id") or 0),
            "appointment_id": appointment_id,
            "decision": decision.lower(),  # 'accepted' or 'rejected'
            "status": "in_process" if decision == "ACCEPTED" else "canceled",
            "notes": f"[AUTO] Decision Engine: {decision}",
        }
        
        logger.info(f"Persisting decision to DB: {decision} for plate={license_plate}, appointment_id={appointment_id}, gate={gate_id}")
        result = await internal_client.post(path, json=body)
        logger.info(f"Decision persisted successfully: {result}")
        
    except Exception as e:
        logger.error(f"Failed to persist decision to DB: {e}")


async def _run_consumer() -> None:
    """
    Loop principal do consumer Kafka.

    - Subscreve o tópico de decisões (settings.KAFKA_DECISION_TOPIC)
    - Para cada mensagem:
        * faz parse do JSON
        * normaliza para formato do frontend
        * persiste decisão na BD se for ACCEPTED/REJECTED
        * extrai gate_id se existir (senão manda para "global")
        * faz broadcast via DecisionsHub
    """
    topic = settings.KAFKA_DECISION_TOPIC
    
    # Extract gate_id from topic name (e.g., 'decision-results-1' -> gate 1)
    gate_id = _extract_gate_id_from_topic(topic)
    logger.info(f"Extracted gate_id '{gate_id}' from topic '{topic}'")
    
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=settings.KAFKA_CONSUMER_GROUP or None,
        value_deserializer=lambda v: v.decode("utf-8"),
        enable_auto_commit=True,
        auto_offset_reset="latest",
    )

    await consumer.start()
    logger.info(
        "Kafka consumer started. topic='{}', servers='{}', group_id='{}', gate_id='{}'",
        topic,
        settings.KAFKA_BOOTSTRAP_SERVERS,
        settings.KAFKA_CONSUMER_GROUP,
        gate_id,
    )

    try:
        async for msg in consumer:
            raw_value = msg.value
            logger.info("Received Kafka message: {}", raw_value[:200] + "..." if len(raw_value) > 200 else raw_value)
            
            try:
                raw_payload = json.loads(raw_value)
            except json.JSONDecodeError:
                logger.warning("Mensagem Kafka inválida (não é JSON): {}", raw_value)
                continue

            logger.info(
                "Raw payload: decision={}, plate={}, gate_id={}, hz_result={}",
                raw_payload.get("decision"),
                raw_payload.get("licensePlate"),
                raw_payload.get("gate_id"),
                raw_payload.get("kemler"),
            )

            # Persist decision to database (ACCEPTED/REJECTED)
            await _persist_decision(raw_payload, gate_id)

            # Generate unique message ID for tracking duplicates
            import uuid
            msg_id = str(uuid.uuid4())[:8]
            
            message = {
                "type": "decision_update",
                "payload": raw_payload,
                "msg_id": msg_id,  # Debug: track message uniqueness
            }

            # Log connections before broadcast
            from .hub import decisions_hub
            conns_count = len(decisions_hub._connections.get(gate_id, set()))
            logger.info(f"[DEBUG] msg_id={msg_id} Broadcasting to gate '{gate_id}' with {conns_count} connections")
            
            await decisions_hub.broadcast_to_gate(gate_id, message)
            
            logger.info(f"[DEBUG] msg_id={msg_id} Broadcast complete")
            
            #if not gate_id:
            #    await decisions_hub.broadcast_to_gate("global", message)

    finally:
        await consumer.stop()
        logger.info("Kafka consumer stopped.")


def start_consumer(loop: asyncio.AbstractEventLoop) -> None:
    """
    Arranca o consumer Kafka em background.
    Deve ser chamado no evento de startup do FastAPI.
    """
    global _consumer_task
    if _consumer_task is None or _consumer_task.done():
        _consumer_task = loop.create_task(_run_consumer())

