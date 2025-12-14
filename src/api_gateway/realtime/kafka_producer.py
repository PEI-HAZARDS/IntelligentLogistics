"""
Kafka Producer for API Gateway.
Used to publish manual review decisions to the same topic as DecisionEngine.
"""
import json
from typing import Optional
from datetime import datetime

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
) -> bool:
    """
    Publish manual review decision to Kafka.
    
    This message will be consumed by the same WebSocket infrastructure
    that handles DecisionEngine decisions, allowing the Driver UI to
    receive real-time updates.
    
    Args:
        gate_id: Gate ID for topic routing
        appointment_id: The appointment being reviewed
        license_plate: Truck license plate
        decision: 'approved' or 'rejected'
        notes: Optional operator notes
    
    Returns:
        True if published successfully
    """
    try:
        producer = await get_producer()
        
        # Build topic name matching DecisionEngine pattern
        topic = f"decision-results-{gate_id}"
        
        # Normalize decision to match frontend expectations
        decision_upper = "ACCEPTED" if decision.lower() == "approved" else "REJECTED"
        
        # Build payload matching DecisionEngine._publish_decision() format
        payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "licensePlate": license_plate,
            "decision": decision_upper,
            "alerts": [f"[MANUAL REVIEW] Operator {decision.lower()}"],
            "gate_id": gate_id,
            "route": {
                "appointment_id": appointment_id,
                "gate_id": gate_id,
            },
            # Mark as manual review for frontend distinction
            "manual_review": True,
            # No crop URLs for manual review updates
            "lp_cropUrl": None,
            "hz_cropUrl": None,
            "UN": None,
            "kemler": None,
        }
        
        # Generate a unique key for the message
        key = f"manual-review-{appointment_id}"
        
        await producer.send_and_wait(topic, value=payload, key=key)
        
        logger.info(
            f"Published manual review to '{topic}': "
            f"appointment_id={appointment_id}, decision={decision_upper}"
        )
        return True
        
    except Exception as e:
        logger.error(f"Failed to publish manual review decision: {e}")
        return False
