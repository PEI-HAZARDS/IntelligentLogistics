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
from infrastructure.messaging.dlq_producer import DLQProducer
from application.queries.decision_queries import (
    update_appointment_after_infraction,
)
from config import settings
from domain.events import EventEnvelope, ConsumeContext
from application.use_cases.container_moved_handler import ContainerMovedHandler
from application.use_cases.notification_handlers import cmd_create_notification
from application.use_cases.pending_review_handlers import cmd_store_pending_review
from infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from infrastructure.persistence.postgres import SessionLocal

logger = logging.getLogger("kafka_decision_consumer")


class DecisionCorrelator:
    """
    Manages correlation between agent and operator decisions.
    Uses Redis to persist pending MANUAL_REVIEW decisions — survives container restarts.
    """
    
    PENDING_KEY_PREFIX = "pending_review:"
    PENDING_TTL = 1800  # 30 minutes
    
    def __init__(self):
        from infrastructure.persistence.redis import redis_client
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
            logger.info(f"Agent MANUAL_REVIEW for truck_id={truck_id}, storing in PG + Outbox.")
            try:
                event_id = decision_data.get("event_id") or str(__import__("uuid").uuid4())
                gate_id = int(decision_data.get("gate_id") or 0)
                license_plate = decision_data.get("license_plate", "UNKNOWN")

                def _uow_factory():
                    return SqlAlchemyUnitOfWork(SessionLocal)

                cmd_store_pending_review(
                    _uow_factory,
                    event_id=event_id,
                    truck_id=truck_id,
                    gate_id=gate_id,
                    license_plate=license_plate,
                    payload=decision_data,
                )
            except Exception as e:
                logger.error(f"Failed to store pending review for truck_id={truck_id}: {e}")
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
        self.dlq_producer = DLQProducer(settings.kafka_bootstrap)

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
        await asyncio.sleep(0)
        logger.info("KafkaDecisionConsumer started")
    
    async def stop(self):
        """Stop the consumer loop."""
        self.running = False
        if self.consumer_task:
            self.consumer_task.cancel()
            try:
                await self.consumer_task
            except asyncio.CancelledError:
                logger.debug("Consumer task cancelled cleanly")
                raise
        logger.info("KafkaDecisionConsumer stopped")
    
    async def _consume_loop(self):
        """Main consumption loop."""
        logger.info("Starting Kafka consumption loop...")

        while self.running:
            msg = None
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
                dispatched = False

                if topic in self.agent_decision_topics:
                    final_decision = self.correlator.process_agent_decision(truck_id, data)
                    if final_decision:
                        dispatched = await self._dispatch_container_moved(truck_id, final_decision, msg)

                elif topic in self.operator_decision_topics:
                    final_decision = self.correlator.process_operator_decision(truck_id, data)
                    if final_decision:
                        dispatched = await self._dispatch_container_moved(truck_id, final_decision, msg)

                elif topic in self.infraction_decision_topics:
                    inferred_gate_id = self._extract_gate_id_from_topic(topic)
                    if inferred_gate_id and not data.get("gate_id"):
                        data = {**data, "gate_id": inferred_gate_id}
                    await self._store_infraction_decision(truck_id, data, msg)
                    # Commit offset ONLY after successful infraction processing (Guardrail 4).
                    # Without this, consumer restart replays the same event repeatedly.
                    await asyncio.get_event_loop().run_in_executor(
                        None, self.consumer.consumer.commit, msg
                    )
                    logger.info(f"Infraction decision processed and offset committed for truck_id={truck_id}")

                # If final decision ready, persist it
                if final_decision and dispatched:
                    inferred_gate_id = self._extract_gate_id_from_topic(topic)
                    if inferred_gate_id and not final_decision.get("gate_id"):
                        final_decision = {**final_decision, "gate_id": inferred_gate_id}
                    await self._persist_decision(truck_id, final_decision)

            except Exception as e:
                logger.error(f"Error in consume loop: {e}", exc_info=True)
                # Route to DLQ if we have message context (Guardrail 8)
                if msg is not None:
                    try:
                        src_topic = msg.topic() if callable(getattr(msg, "topic", None)) else "unknown"
                        src_partition = msg.partition() if callable(getattr(msg, "partition", None)) else -1
                        src_offset = msg.offset() if callable(getattr(msg, "offset", None)) else -1
                        raw_headers = msg.headers() if callable(getattr(msg, "headers", None)) else []
                        hdr_dict = {
                            k: v.decode("utf-8") if isinstance(v, bytes) else v
                            for k, v in raw_headers or []
                        }
                        raw_value = msg.value()
                        try:
                            payload = json.loads(raw_value) if raw_value else {}
                        except Exception:
                            payload = {"raw": raw_value.decode("utf-8", errors="replace") if raw_value else ""}

                        if DLQProducer.is_permanent_error(e):
                            self.dlq_producer.send_to_dlq(
                                source_topic=src_topic,
                                source_partition=src_partition,
                                source_offset=src_offset,
                                key=hdr_dict.get("truckId"),
                                headers=hdr_dict,
                                payload=payload,
                                error=e,
                            )
                        else:
                            logger.warning(
                                "Transient error on topic=%s offset=%s, will retry: %s",
                                src_topic, src_offset, e,
                            )
                    except Exception as dlq_err:
                        logger.critical("DLQ routing itself failed: %s", dlq_err)
                await asyncio.sleep(1)

    async def _dispatch_container_moved(self, truck_id: str, decision_data: dict, msg) -> bool:
        """
        Strangler Fig — route container-moved decisions through the clean
        ContainerMovedHandler instead of the legacy multi-DB write path.

        Kafka offset is committed ONLY after the handler returns successfully.
        """
        from uuid import uuid4

        # ── Resolve appointment_id from decision data or DB lookup ──
        appointment_id = decision_data.get("appointment_id")
        if not appointment_id:
            # Look up active appointment by truck license plate
            license_plate = decision_data.get("license_plate")
            if license_plate:
                appointment_id = await self._resolve_appointment_id(license_plate)
            if not appointment_id:
                logger.warning(
                    "Cannot dispatch ContainerMoved for truck_id=%s: "
                    "no appointment_id in decision data and no active appointment found",
                    truck_id,
                )
                return False

        # ── Build EventEnvelope from correlated decision ──────────
        headers_raw = msg.headers() or []
        headers_dict = {
            k: (v.decode("utf-8") if isinstance(v, bytes) else v)
            for k, v in headers_raw
        }

        envelope = EventEnvelope(
            event_id=str(uuid4()),
            correlation_id=truck_id,
            causation_id=None,
            aggregate_type="appointment",
            aggregate_id=str(appointment_id),
            event_type="ContainerMoved",
            event_version=1,
            occurred_at=datetime.now(timezone.utc),
            producer=msg.topic(),
            partition_key=truck_id,
            payload=decision_data,
        )

        ctx = ConsumeContext(
            topic=msg.topic(),
            partition=msg.partition(),
            offset=msg.offset(),
            key=truck_id,
            headers=headers_dict,
        )

        # ── Dispatch to clean handler (sync — run in executor) ────
        handler = ContainerMovedHandler(
            uow_factory=SqlAlchemyUnitOfWork,
            session_factory=SessionLocal,
        )

        await asyncio.get_event_loop().run_in_executor(
            None, handler.handle, envelope, ctx
        )

        # ── Commit Kafka offset ONLY after success (Guardrail 4) ──
        await asyncio.get_event_loop().run_in_executor(
            None, self.consumer.consumer.commit, msg
        )
        logger.info(
            "ContainerMoved dispatched and offset committed for truck_id=%s",
            truck_id,
        )
        return True


    async def _resolve_appointment_id(self, license_plate: str) -> Optional[int]:
        """Look up the active appointment ID by truck license plate in PostgreSQL."""
        def _query():
            from infrastructure.persistence.sql_models import Appointment as AppointmentORM
            db = SessionLocal()
            try:
                appt = (
                    db.query(AppointmentORM)
                    .filter(
                        AppointmentORM.truck_license_plate == license_plate,
                        AppointmentORM.status.in_(["in_transit", "delayed", "in_process", "unloading"]),
                    )
                    .order_by(AppointmentORM.scheduled_start_time.desc())
                    .first()
                )
                return appt.id if appt else None
            finally:
                db.close()

        try:
            return await asyncio.get_event_loop().run_in_executor(None, _query)
        except Exception as e:
            logger.error("Failed to resolve appointment_id for plate=%s: %s", license_plate, e)
            return None

    async def _persist_decision(self, truck_id: str, decision_data: dict):
        """No-op — Mongo projection is handled by the outbox worker (DW-03)."""
        logger.debug("_persist_decision: outbox worker handles Mongo projection for truck_id=%s", truck_id)

    async def _store_infraction_decision(self, truck_id: str, decision_data: dict, msg) -> None:
        """Persist infraction event, flag appointment, create alert, and notify gate + driver.

        DW-06: inbox dedup prevents double-processing on consumer restart.
        DW-01: notifications emitted via outbox instead of direct Mongo writes.
        """
        import uuid as _uuid

        # ── Derive stable inbox dedup key ─────────────────────────
        raw_event_id = decision_data.get("event_id")
        if raw_event_id:
            dedup_event_id = str(raw_event_id)
        else:
            dedup_event_id = str(_uuid.uuid5(
                _uuid.NAMESPACE_URL,
                f"{msg.topic()}:{msg.partition()}:{msg.offset()}",
            ))

        headers_raw = msg.headers() or []
        headers_dict = {
            k: (v.decode("utf-8") if isinstance(v, bytes) else v)
            for k, v in headers_raw
        }

        inbox_envelope = EventEnvelope(
            event_id=dedup_event_id,
            correlation_id=truck_id,
            causation_id=None,
            aggregate_type="infraction",
            aggregate_id=truck_id,
            event_type="InfractionDecisionReceived",
            event_version=1,
            occurred_at=datetime.now(timezone.utc),
            producer=msg.topic(),
            partition_key=truck_id,
            payload=decision_data,
        )
        inbox_ctx = ConsumeContext(
            topic=msg.topic(),
            partition=msg.partition(),
            offset=msg.offset(),
            key=truck_id,
            headers=headers_dict,
        )

        # ── Inbox dedup gate (DW-06) ──────────────────────────────
        def _inbox_check() -> bool:
            with SqlAlchemyUnitOfWork(SessionLocal) as uow:
                if not uow.inbox.try_insert_received(inbox_envelope, inbox_ctx):
                    return False
                uow.inbox.mark_processing(dedup_event_id)
                uow.commit()
                return True

        is_new = await asyncio.get_event_loop().run_in_executor(None, _inbox_check)
        if not is_new:
            logger.info(
                "Duplicate infraction event skipped: event_id=%s truck_id=%s",
                dedup_event_id, truck_id,
            )
            return

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

            # Mongo projection handled by the outbox worker (DW-03)

            # Determine if infraction flag needs to be updated on appointment
            infraction_detected = bool(decision_data.get("infraction", False))
            if not infraction_detected:
                logger.info(f"No infraction for truck_id={truck_id}; skipping appointment flag update")
            else:
                license_plate = decision_data.get("license_plate")
                if not license_plate or license_plate == "N/A":
                    logger.warning(
                        f"Infraction detected for truck_id={truck_id} but license_plate is missing"
                    )
                else:
                    # Update appointment highway_infraction flag in PostgreSQL via UoW + Outbox
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
                    else:
                        appointment_id = result.get("appointment_id")
                        logger.info(
                            f"Appointment {appointment_id} infraction flag updated for truck_id={truck_id}: "
                            f"{result['old_highway_infraction']} -> {result['new_highway_infraction']}"
                        )

                        # Route warnings to the appointment gate (gate_in_id) when available.
                        notification_gate_id = await self._get_driver_gate_id(appointment_id, gate_id)
                        if notification_gate_id != gate_id:
                            logger.info(
                                "Infraction notification gate remapped from source gate=%s to "
                                "appointment gate=%s for truck_id=%s",
                                gate_id, notification_gate_id, truck_id,
                            )

                        # Create PG alert record via UoW + Outbox (Guardrails 2, 3, 6)
                        infraction_type = decision_data.get("infraction_type", "highway_route")
                        alert_description = (
                            f"Highway infraction detected: truck {license_plate} "
                            f"flagged for {infraction_type}. Driver must return to highway or face a fine."
                        )
                        try:
                            def _create_infraction_alert():
                                from application.use_cases.alert_handlers import create_alerts_for_appointment
                                def _uow_factory():
                                    return SqlAlchemyUnitOfWork(SessionLocal)
                                create_alerts_for_appointment(
                                    _uow_factory,
                                    appointment_id=appointment_id,
                                    alerts_payload=[{
                                        "type": "operational",
                                        "description": alert_description,
                                    }],
                                )

                            await asyncio.get_event_loop().run_in_executor(None, _create_infraction_alert)
                            logger.info(f"PG alert created for infraction on appointment={appointment_id}")
                        except Exception as alert_err:
                            logger.error(f"Failed to create PG alert for infraction: {alert_err}")

                        # Gate + driver notifications via outbox (DW-01)
                        def _uow_factory():
                            return SqlAlchemyUnitOfWork(SessionLocal)

                        try:
                            await asyncio.get_event_loop().run_in_executor(
                                None,
                                lambda: cmd_create_notification(
                                    _uow_factory,
                                    gate_id=notification_gate_id,
                                    title="Highway Infraction",
                                    message=f"Truck {license_plate} flagged with highway infraction.",
                                    notification_type="danger",
                                    appointment_id=appointment_id,
                                    license_plate=license_plate,
                                ),
                            )
                        except Exception as notif_err:
                            logger.error(f"Failed to emit gate notification for infraction: {notif_err}")

                        try:
                            await asyncio.get_event_loop().run_in_executor(
                                None,
                                lambda: cmd_create_notification(
                                    _uow_factory,
                                    gate_id=notification_gate_id,
                                    title="Highway Infraction Warning",
                                    message=(
                                        f"Your truck ({license_plate}) has been flagged for a highway route infraction. "
                                        "Please return to the designated highway route or you may be fined."
                                    ),
                                    notification_type="warning",
                                    appointment_id=appointment_id,
                                    license_plate=license_plate,
                                    extra={"target": "driver"},
                                ),
                            )
                            logger.info(f"Driver notification emitted for infraction on appointment={appointment_id}")
                        except Exception as notif_err:
                            logger.error(f"Failed to emit driver notification for infraction: {notif_err}")

            # ── Mark inbox event processed ────────────────────────
            def _mark_processed():
                with SqlAlchemyUnitOfWork(SessionLocal) as uow:
                    uow.inbox.mark_processed(dedup_event_id)
                    uow.commit()

            await asyncio.get_event_loop().run_in_executor(None, _mark_processed)

        except Exception as e:
            logger.error(f"Error storing infraction decision for truck_id={truck_id}: {e}", exc_info=True)

            def _mark_failed():
                with SqlAlchemyUnitOfWork(SessionLocal) as uow:
                    uow.inbox.mark_failed(dedup_event_id, str(e)[:500], retryable=True)
                    uow.commit()

            try:
                await asyncio.get_event_loop().run_in_executor(None, _mark_failed)
            except Exception as mark_err:
                logger.error("Failed to mark infraction inbox event as failed: %s", mark_err)

    async def _get_driver_gate_id(self, appointment_id: int, fallback_gate_id: int) -> int:
        """Get the gate_in_id for the appointment, or fallback."""
        def _query():
            from infrastructure.persistence.sql_models import Appointment as AppointmentORM
            db = SessionLocal()
            try:
                appt = db.query(AppointmentORM).filter(AppointmentORM.id == appointment_id).first()
                return appt.gate_in_id if appt and appt.gate_in_id else fallback_gate_id
            finally:
                db.close()
        try:
            return await asyncio.get_event_loop().run_in_executor(None, _query)
        except Exception:
            return fallback_gate_id

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
