import asyncio
import json
import re
from typing import Optional

from aiokafka import AIOKafkaConsumer
from loguru import logger

from config import settings
from .hub import decisions_hub

# Task global para podermos arrancar o consumer no startup
_consumer_task: Optional[asyncio.Task] = None


<<<<<<< HEAD
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
=======
def _normalize_payload(raw_payload: dict) -> dict:
    """
    Normaliza o payload do Kafka para o formato esperado pelo frontend.
    
    Kafka (Decision Engine) envia:
      - licensePlate, lp_cropUrl, hz_cropUrl, UN, kemler, decision, route, alerts
    
    Frontend espera:
      - lp_result, lp_crop, hz_crop, hz_result, decision, gate_id, timestamp
    """
    route = raw_payload.get("route") or {}
    
    normalized = {
        # Timestamps
        "timestamp": raw_payload.get("timestamp"),
        
        # License plate detection
        "lp_result": raw_payload.get("licensePlate"),
        "lp_crop": raw_payload.get("lp_cropUrl"),
        
        # Hazmat detection (UN/Kemler codes)
        "hz_crop": raw_payload.get("hz_cropUrl"),
        "hz_result": None,  # Will be set below if UN/Kemler exist
        
        # Decision
        "decision": raw_payload.get("decision"),
        
        # Route info (if matched)
        "gate_id": route.get("gate_id") if isinstance(route, dict) else None,
        "terminal_id": route.get("terminal_id") if isinstance(route, dict) else None,
        "appointment_id": route.get("appointment_id") if isinstance(route, dict) else None,
        
        # Alerts from Decision Engine
        "alerts": raw_payload.get("alerts", []),
        
        # Original truck_id (if exists)
        "truck_id": raw_payload.get("truck_id") or raw_payload.get("licensePlate"),
    }
    
    # Build hz_result from UN/Kemler if present
    un_code = raw_payload.get("UN")
    kemler_code = raw_payload.get("kemler")
    if un_code or kemler_code:
        parts = []
        if un_code:
            parts.append(f"UN {un_code}")
        if kemler_code:
            parts.append(f"Kemler {kemler_code}")
        normalized["hz_result"] = " / ".join(parts)
    
    return normalized
>>>>>>> 1dd123eab4f1c40695df311ba191cc0a927fe886


async def _run_consumer() -> None:
    """
    Loop principal do consumer Kafka.

    - Subscreve o tópico de decisões (settings.KAFKA_DECISION_TOPIC)
    - Para cada mensagem:
        * faz parse do JSON
<<<<<<< HEAD
        * extrai gate_id do nome do tópico
=======
        * normaliza para formato do frontend
        * extrai gate_id se existir (senão manda para "global")
>>>>>>> 1dd123eab4f1c40695df311ba191cc0a927fe886
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

    # Use extracted gate_id or fallback to "global"
    gate_key = gate_id if gate_id else "global"

    try:
        async for msg in consumer:
            raw_value = msg.value
            logger.info("Received Kafka message: {}", raw_value[:200] + "..." if len(raw_value) > 200 else raw_value)
            
            try:
                raw_payload = json.loads(raw_value)
            except json.JSONDecodeError:
                logger.warning("Mensagem Kafka inválida (não é JSON): {}", raw_value)
                continue

<<<<<<< HEAD
=======
            # Normalize payload for frontend consumption
            payload = _normalize_payload(raw_payload)
            
            logger.info(
                "Normalized payload: decision={}, plate={}, gate_id={}, hz_result={}",
                payload.get("decision"),
                payload.get("lp_result"),
                payload.get("gate_id"),
                payload.get("hz_result"),
            )

            # Extract gate_id from normalized payload
            gate_id = payload.get("gate_id")

            # Se não houver gate_id, manda para canal "global"
            gate_key = str(gate_id) if gate_id is not None else "global"

>>>>>>> 1dd123eab4f1c40695df311ba191cc0a927fe886
            message = {
                "type": "decision_update",
                "payload": payload,
            }

            # Enviar para todos os clientes ligados a esse gate
            logger.info(f"Broadcasting to gate '{gate_key}'")
            await decisions_hub.broadcast_to_gate(gate_key, message)
            
            # Also broadcast to "global" channel for dashboards that listen to all gates
            if gate_key != "global":
                await decisions_hub.broadcast_to_gate("global", message)

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
