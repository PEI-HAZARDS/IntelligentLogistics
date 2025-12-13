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


async def _run_consumer() -> None:
    """
    Loop principal do consumer Kafka.

    - Subscreve o tópico de decisões (settings.KAFKA_DECISION_TOPIC)
    - Para cada mensagem:
        * faz parse do JSON
        * extrai gate_id do nome do tópico
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
                payload = json.loads(raw_value)
            except json.JSONDecodeError:
                logger.warning("Mensagem Kafka inválida (não é JSON): {}", raw_value)
                continue

            message = {
                "type": "decision_update",
                "payload": payload,
            }

            # Enviar para todos os clientes ligados a esse gate
            logger.info(f"Broadcasting to gate '{gate_key}'")
            await decisions_hub.broadcast_to_gate(gate_key, message)

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
