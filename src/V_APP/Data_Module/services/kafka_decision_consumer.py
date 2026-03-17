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
import asyncio
from typing import Optional
from datetime import datetime, timezone
import json
import os

from shared.src.kafka_wrapper import KafkaConsumerWrapper
from shared.src.kafka_protocol import KafkaTopicFactory
from services.decision_service import (
    persist_decision_event_from_kafka,
    update_appointment_after_decision,
    persist_infraction_event_from_kafka,
    update_appointment_after_infraction,
)
from services.notification_service import create_notification
from config import settings

logger = logging.getLogger("kafka_decision_consumer")


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

    def __init__(self, consumer: KafkaConsumerWrapper | None = None):
        self.running = False
        self.consumer_task = None
        self.correlator = DecisionCorrelator()

        self.decision_gate_ids = self._parse_gate_ids_from_env("DECISION_GATE_IDS", settings.gate_id)
        self.infraction_gate_ids = self._parse_gate_ids_from_env("INFRACTION_GATE_IDS", settings.gate_id)

        self.agent_decision_topics = {
            KafkaTopicFactory.agent_decision(gid) for gid in self.decision_gate_ids
        }
        self.operator_decision_topics = {
            KafkaTopicFactory.operator_decision(gid) for gid in self.decision_gate_ids
        }
        self.infraction_decision_topics = {
            KafkaTopicFactory.infraction_decision(gid) for gid in self.infraction_gate_ids
        }

        # Topic names via factory — single source of truth
        topics = sorted(
            self.agent_decision_topics
            | self.operator_decision_topics
            | self.infraction_decision_topics
        )
        self.consumer = consumer or KafkaConsumerWrapper(
            bootstrap_servers=settings.kafka_bootstrap,
            group_id="data-module-decisions",
            topics=topics,
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
                # Consume message (sync, run in executor to avoid blocking)
                msg = await asyncio.get_event_loop().run_in_executor(
                    None,
                    self.consumer.consume_message,
                    1.0  # timeout
                )

                if msg is None:
                    await asyncio.sleep(0.1)
                    continue

                # parse_message handles header extraction and JSON decoding
                topic, data, truck_id = self.consumer.parse_message(msg)

                if not truck_id:
                    logger.warning(f"Message from {topic} has no truckId header, skipping")
                    continue

                if data is None:
                    logger.error(f"Failed to parse message body from {topic}")
                    continue

                # Process based on topic
                final_decision = None

                if topic in self.agent_decision_topics:
                    final_decision = self.correlator.process_agent_decision(truck_id, data)

                elif topic in self.operator_decision_topics:
                    final_decision = self.correlator.process_operator_decision(truck_id, data)

                elif topic in self.infraction_decision_topics:
                    inferred_gate_id = self._extract_gate_id_from_topic(topic)
                    if inferred_gate_id and not data.get("gate_id"):
                        data = {**data, "gate_id": inferred_gate_id}
                    await self._store_infraction_decision(truck_id, data)
                    logger.info(f"Infraction decision processed for truck_id={truck_id}")

                # If final decision ready, persist it
                if final_decision:
                    inferred_gate_id = self._extract_gate_id_from_topic(topic)
                    if inferred_gate_id and not final_decision.get("gate_id"):
                        final_decision = {**final_decision, "gate_id": inferred_gate_id}
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
            gate_id = decision_data.get("gate_id", int(settings.gate_id))
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

    
    async def _store_infraction_decision(self, truck_id: str, decision_data: dict):
        """Persist infraction event and flag appointment highway_infraction when needed."""
        try:
            logger.info(f"Storing infraction decision for truck_id={truck_id}")

            try:
                gate_id = int(decision_data.get("gate_id", settings.gate_id))
            except (TypeError, ValueError):
                gate_id = int(settings.gate_id)

            event_payload = {
                **decision_data,
                "gate_id": gate_id,
                "truck_id": truck_id,
            }


            # Store infraction event in MongoDB (separate collection) — runs in executor to avoid blocking
            event_id = await asyncio.get_event_loop().run_in_executor(
                None,
                persist_infraction_event_from_kafka,
                truck_id,
                event_payload,
            )
            logger.info(f"Infraction event persisted for truck_id={truck_id} with id={event_id}")

            # Determine if infraction flag needs to be updated on appointment
            infraction_detected = bool(decision_data.get("infraction", False))
            if not infraction_detected:
                logger.info(f"No infraction for truck_id={truck_id}; skipping appointment flag update")
                return

            license_plate = decision_data.get("license_plate")
            if not license_plate or license_plate == "N/A":
                logger.warning(f"Infraction detected for truck_id={truck_id} but license_plate is missing")
                return
            # Update appointment in PostgreSQL if infraction detected
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                update_appointment_after_infraction,
                license_plate,
                True,
            )

            if not result:
                logger.warning(
                    f"Infraction detected for truck_id={truck_id} plate={license_plate}, "
                    "but no active appointment was updated"
                )
                return

            logger.info(
                f"Appointment {result['appointment_id']} infraction flag updated for truck_id={truck_id}: "
                f"{result['old_highway_infraction']} -> {result['new_highway_infraction']}"
            )

            create_notification(
                gate_id=gate_id,
                title="Highway Infraction",
                message=f"Truck {license_plate} flagged with highway infraction.",
                notification_type="danger",
                appointment_id=result.get("appointment_id"),
                license_plate=license_plate,
            )
        except Exception as e:
            logger.error(f"Error storing infraction decision for truck_id={truck_id}: {e}", exc_info=True)

    @staticmethod
    def _extract_gate_id_from_topic(topic: str) -> Optional[str]:
        """Extract gate_id suffix from known decision topics."""
        if not topic:
            return None

        for prefix in ("agent-decision-", "operator-decision-", "infraction-decision-"):
            if topic.startswith(prefix):
                gate_id = topic[len(prefix):].strip()
                return gate_id if gate_id else None
        return None

    @staticmethod
    def _parse_gate_ids_from_env(env_key: str, fallback_gate_id: str) -> list[str]:
        """Parse gate id list from JSON array env variable with safe fallback."""
        raw = os.getenv(env_key, "").strip()
        if not raw:
            return [str(fallback_gate_id)]

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                gate_ids = [str(item).strip() for item in parsed if str(item).strip()]
                if gate_ids:
                    return gate_ids
        except json.JSONDecodeError:
            logger.warning(f"Invalid {env_key} format ('{raw}'). Falling back to GATE_ID.")

        return [str(fallback_gate_id)]
