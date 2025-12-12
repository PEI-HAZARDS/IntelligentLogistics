import asyncio
import json
from typing import Optional

from aiokafka import AIOKafkaConsumer
from loguru import logger

from config import settings
from .hub import decisions_hub

# Task global para podermos arrancar o consumer no startup
_consumer_task: Optional[asyncio.Task] = None


async def _run_consumer() -> None:
    """
    Loop principal do consumer Kafka.

    - Subscreve o tópico de decisões (settings.KAFKA_DECISION_TOPIC)
    - Para cada mensagem:
        * faz parse do JSON
        * extrai gate_id se existir (senão manda para "global")
        * faz broadcast via DecisionsHub
    """
    consumer = AIOKafkaConsumer(
        settings.KAFKA_DECISION_TOPIC,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=settings.KAFKA_CONSUMER_GROUP or None,
        value_deserializer=lambda v: v.decode("utf-8"),
        enable_auto_commit=True,
        auto_offset_reset="latest",
    )

    await consumer.start()
    logger.info(
        "Kafka consumer started. topic='{}', servers='{}', group_id='{}'",
        settings.KAFKA_DECISION_TOPIC,
        settings.KAFKA_BOOTSTRAP_SERVERS,
        settings.KAFKA_CONSUMER_GROUP,
    )

    try:
        async for msg in consumer:
            raw_value = msg.value
            logger.info("Received Kafka message: {}", raw_value)
            try:
                payload = json.loads(raw_value)
            except json.JSONDecodeError:
                logger.warning("Mensagem Kafka inválida (não é JSON): {}", raw_value)
                continue

            # Esperamos payload do tipo:
            # {
            #   "truck_id": "TRCK_123",
            #   "lp_crop": "http://IP/lp_crop_123",
            #   "hz_crop": "http://IP/hz_crop_123",
            #   "lp_result": "17-AA-18",
            #   "hz_result": "flammable",
            #   "decision": "ACCEPTED",
            #   "route": "example_route",
            #   "gate_id": 1,              # (idealmente)
            #   ...
            # }
            gate_id = payload.get("gate_id")

            # Se não houver gate_id, podes decidir mandar para um canal "global"
            gate_key = str(gate_id) if gate_id is not None else "global"

            message = {
                "type": "decision_update",
                "payload": payload,
            }

            # Enviar para todos os clientes ligados a esse gate
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
