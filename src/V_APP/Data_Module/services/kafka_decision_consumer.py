"""
Kafka Decision Consumer - Consumes agent and operator decisions.

Responsibilities:
- Consume agent-decision (from Decision Engine)
- Consume operator-decision (from API Gateway)
- Correlate decisions:
  - MANUAL_REVIEW: Wait for operator-decision before final persistence
  - ACCEPTED: Process immediately without waiting
- Persist final decisions to database
"""

import logging
import os
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import json

from shared.src.kafka_wrapper import KafkaConsumerWrapper
from services.decision_service import persist_decision_event_from_kafka, update_appointment_after_decision
from services.notification_service import create_notification

logger = logging.getLogger("kafka_decision_consumer")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:29092")
GATE_ID = os.getenv("GATE_ID", "1")

class DecisionCorrelator:
    """
    Manages correlation between agent and operator decisions.
    Uses Redis to persist pending MANUAL_REVIEW decisions — survives container restarts.
    """
    
    PENDING_KEY_PREFIX = "pending_review:"
    PENDING_TTL = 1800  # 30 minutes
    
    def __init__(self):
        from db.redis import redis_client
        self.redis = redis_client
        
    def process_agent_decision(self, truck_id: str, decision_data: dict) -> Optional[dict]:
        """
        Process agent decision.
        
        Returns:
        - dict: Final decision to persist (if ACCEPTED)
        - None: Decision is MANUAL_REVIEW, waiting for operator
        """
        decision_status = decision_data.get("decision", "")
        
        if decision_status == "ACCEPTED":
            logger.info(f"Agent ACCEPTED truck_id={truck_id}, processing immediately.")
            return self._build_final_decision(decision_data, source="agent")
        
        elif decision_status == "MANUAL_REVIEW":
            logger.info(f"Agent MANUAL_REVIEW for truck_id={truck_id}, storing in Redis.")
            try:
                key = f"{self.PENDING_KEY_PREFIX}{truck_id}"
                self.redis.setex(key, self.PENDING_TTL, json.dumps(decision_data, default=str))
            except Exception as e:
                logger.error(f"Failed to store pending review in Redis for truck_id={truck_id}: {e}")
            return None
        
        else:
            logger.warning(f"Unknown decision status: {decision_status} for truck_id={truck_id}")
            return None
    
    def process_operator_decision(self, truck_id: str, operator_data: dict) -> Optional[dict]:
        """
        Process operator decision.
        
        Returns:
        - dict: Final decision to persist (combines agent + operator data)
        - None: No pending agent decision found
        """
        # Check Redis for pending agent decision
        agent_data = None
        try:
            key = f"{self.PENDING_KEY_PREFIX}{truck_id}"
            raw = self.redis.get(key)
            if raw:
                agent_data = json.loads(raw)
                self.redis.delete(key)
        except Exception as e:
            logger.error(f"Failed to retrieve pending review from Redis for truck_id={truck_id}: {e}")
        
        if not agent_data:
            logger.warning(f"Received operator decision for truck_id={truck_id} but no pending agent decision found.")
            # Process operator decision standalone
            return self._build_final_decision(operator_data, source="operator")
        
        logger.info(f"Operator decision received for truck_id={truck_id}, merging with agent decision.")
        
        # Merge agent and operator decisions
        final_decision = self._merge_decisions(agent_data, operator_data)
        return final_decision
    
    def _build_final_decision(self, decision_data: dict, source: str) -> dict:
        """Build final decision structure."""
        return {
            **decision_data,
            "decision_source": source,
            "processed_at": datetime.now(timezone.utc).isoformat()
        }
    
    def _merge_decisions(self, agent_data: dict, operator_data: dict) -> dict:
        """
        Merge agent and operator decisions.
        Operator decision overrides agent decision.
        """
        final_decision = agent_data.copy()
        final_decision.update({
            "agent_decision": agent_data.get("decision"),
            "agent_decision_reason": agent_data.get("decision_reason"),
            "operator_decision": operator_data.get("decision"),
            "operator_decision_reason": operator_data.get("decision_reason", ""),
            "decision": operator_data.get("decision"),  # Final decision is operator's
            "decision_reason": operator_data.get("decision_reason", ""),
            "decision_source": "operator",
            "license_plate": operator_data.get("license_plate"),
            "processed_at": datetime.now(timezone.utc).isoformat()
        })
        return final_decision


class KafkaDecisionConsumer:
    """
    Background consumer for agent and operator decisions.
    """
    
    def __init__(self):
        self.running = False
        self.consumer_task = None
        self.correlator = DecisionCorrelator()
        
        # Initialize Kafka consumer for both topics (with GATE_ID suffix)
        topics = [f"agent-decision-{GATE_ID}", f"operator-decision-{GATE_ID}"]
        self.consumer = KafkaConsumerWrapper(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            group_id="data-module-decisions",
            topics=topics
        )
        
        logger.info(f"KafkaDecisionConsumer initialized for topics: {topics}")
    
    async def start(self):
        """Start the consumer loop."""
        if self.running:
            logger.warning("Consumer already running")
            return
        
        self.running = True
        self.consumer_task = asyncio.create_task(self._consume_loop())
        logger.info("KafkaDecisionConsumer started")
    
    async def stop(self):
        """Stop the consumer loop."""
        self.running = False
        if self.consumer_task:
            self.consumer_task.cancel()
            try:
                await self.consumer_task
            except asyncio.CancelledError:
                pass
        logger.info("KafkaDecisionConsumer stopped")
    
    async def _consume_loop(self):
        """Main consumption loop."""
        logger.info("Starting Kafka consumption loop...")
        
        while self.running:
            try:
                # Consume message (this is sync, but we run in executor)
                msg = await asyncio.get_event_loop().run_in_executor(
                    None, 
                    self.consumer.consume_message,
                    1.0  # timeout
                )
                
                if msg is None:
                    await asyncio.sleep(0.1)
                    continue
                
                # Parse message
                topic = msg.topic()
                truck_id = None
                if msg.headers():
                    for key, value in msg.headers():
                        if key == "truckId":
                            truck_id = value.decode("utf-8") if isinstance(value, bytes) else value
                            break
                
                if not truck_id:
                    # Bug fix 1: try extracting truck_id from the payload body before discarding
                    try:
                        body_preview = json.loads(msg.value().decode("utf-8"))
                        truck_id = body_preview.get("truck_id") or body_preview.get("truckId")
                    except Exception:
                        pass

                if not truck_id:
                    logger.warning(f"Message from {topic} has no truckId header, skipping")
                    continue
                
                # Parse payload
                try:
                    data = json.loads(msg.value().decode("utf-8"))
                except Exception as e:
                    logger.error(f"Failed to parse message from {topic}: {e}")
                    continue
                
                # Process based on topic
                final_decision = None
                
                if topic == f"agent-decision-{GATE_ID}":
                    final_decision = self.correlator.process_agent_decision(truck_id, data)
                
                elif topic == f"operator-decision-{GATE_ID}":
                    final_decision = self.correlator.process_operator_decision(truck_id, data)
                
                # If final decision ready, persist it
                if final_decision:
                    await self._persist_decision(truck_id, final_decision)
            
            except Exception as e:
                logger.error(f"Error in consume loop: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    async def _persist_decision(self, truck_id: str, decision_data: dict):
        """Persist final decision to database."""
        try:
            logger.info(f"Persisting final decision for truck_id={truck_id}")
            
            # Extract key data from enriched payload (with fallbacks)
            license_plate = decision_data.get("license_plate")
            gate_id = decision_data.get("gate_id", int(GATE_ID))
            appointment_id = decision_data.get("appointment_id")
            
            # Persist event to MongoDB
            event_id = await asyncio.get_event_loop().run_in_executor(
                None,
                persist_decision_event_from_kafka,
                decision_data
            )
            
            logger.info(f"Decision event persisted with id={event_id}")
            
            # Update appointment in PostgreSQL if decision is ACCEPTED or approved
            decision_status = decision_data.get("decision", "").upper()
            if decision_status in ("ACCEPTED", "APPROVED"):
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    update_appointment_after_decision,
                    license_plate,
                    gate_id,
                    decision_data
                )
                if result:
                    logger.info(f"Appointment updated for license_plate={license_plate}: {result['old_status']} -> {result['new_status']}")

                    # Bug fix 3: create notification via Kafka path (mirrors HTTP path)
                    alerts = decision_data.get("alerts") or []
                    try:
                        if alerts:
                            for alert in alerts:
                                alert_type = alert if isinstance(alert, str) else alert.get("type", "")
                                if alert_type in ("highway_infraction", "highway"):
                                    title, ntype = "Highway Infraction", "danger"
                                elif alert_type == "manual_review":
                                    title, ntype = "Manual Review Needed", "warning"
                                else:
                                    title, ntype = "Vehicle Alert", "warning"
                                create_notification(
                                    gate_id=gate_id,
                                    title=title,
                                    message=f"Alert for {license_plate}: {alert_type}",
                                    notification_type=ntype,
                                    appointment_id=appointment_id,
                                    license_plate=license_plate,
                                )
                        else:
                            create_notification(
                                gate_id=gate_id,
                                title="Vehicle Approved",
                                message=f"Truck {license_plate} approved for entry.",
                                notification_type="info",
                                appointment_id=appointment_id,
                                license_plate=license_plate,
                            )
                    except Exception as notif_err:
                        logger.warning(f"Failed to create notification for truck={license_plate}: {notif_err}")
                else:
                    logger.warning(f"Failed to update appointment for license_plate={license_plate}")

            else:
                logger.info(f"Decision status '{decision_data.get('decision')}' — no appointment update needed")
                    
        except Exception as e:
            logger.error(f"Error persisting decision for truck_id={truck_id}: {e}", exc_info=True)


# Global instance
decision_consumer = KafkaDecisionConsumer()
