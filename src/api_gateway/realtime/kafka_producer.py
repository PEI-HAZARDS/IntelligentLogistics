"""
Kafka Producer for API Gateway.
Used to publish manual review decisions to the same topic as DecisionEngine.
"""
import json
from typing import Optional
from datetime import datetime, timezone

from aiokafka import AIOKafkaProducer
from loguru import logger

from config import settings

# Global producer instance
_producer: Optional[AIOKafkaProducer] = None


async def get_producer() -> AIOKafkaProducer:
    """Get or create the Kafka producer instance."""
    global _producer
    if _producer is None:
        _producer = AIOKafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None,
        )
        await _producer.start()
        logger.info(f"Kafka producer started: {settings.KAFKA_BOOTSTRAP_SERVERS}")
    return _producer


async def stop_producer():
    """Stop the Kafka producer (call on app shutdown)."""
    global _producer
    if _producer:
        await _producer.stop()
        _producer = None
        logger.info("Kafka producer stopped")


async def publish_manual_review_decision(
    gate_id: int,
    appointment_id: int,
    license_plate: str,
    decision: str,
    notes: Optional[str] = None,
    # Optional original detection data to preserve
    original_un: Optional[str] = None,
    original_kemler: Optional[str] = None,
    original_lp_crop: Optional[str] = None,
    original_hz_crop: Optional[str] = None,
) -> bool:
    """
    Publish manual review decision to Kafka.
    
    This message will be consumed by the same WebSocket infrastructure
    that handles DecisionEngine decisions, allowing the Driver UI to
    receive real-time updates.
    
    The payload format matches DecisionEngine._publish_decision() exactly.
    
    Args:
        gate_id: Gate ID for topic routing
        appointment_id: The appointment being reviewed
        license_plate: Truck license plate
        decision: 'approved' or 'rejected'
        notes: Optional operator notes
        original_*: Original detection data to preserve in the decision
    
    Returns:
        True if published successfully
    """
    try:
        producer = await get_producer()
        
        # Build topic name matching DecisionEngine pattern
        topic = f"decision-results-{gate_id}"
        
        # Normalize decision to match frontend expectations
        decision_upper = "ACCEPTED" if decision.lower() == "approved" else "REJECTED"
        
        # Build payload matching DecisionEngine._publish_decision() format exactly
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "licensePlate": license_plate,
            "UN": original_un,
            "kemler": original_kemler,
            "alerts": [f"Operator decision: {decision.lower()}" + (f" - {notes}" if notes else "")],
            "lp_cropUrl": original_lp_crop,
            "hz_cropUrl": original_hz_crop,
            "route": {
                "appointment_id": appointment_id,
                "gate_id": gate_id,
            } if appointment_id else None,
            "decision": decision_upper,
            "decision_source": "operator"
        }
        
        # Generate a unique key for the message
        key = f"manual-review-{appointment_id}"
        
        await producer.send_and_wait(topic, value=payload, key=key)
        
        logger.info(
            f"Published manual review to '{topic}': "
            f"appointment_id={appointment_id}, decision={decision_upper}, source=operator"
        )
        return True
        
    except Exception as e:
        logger.error(f"Failed to publish manual review decision: {e}")
        return False
