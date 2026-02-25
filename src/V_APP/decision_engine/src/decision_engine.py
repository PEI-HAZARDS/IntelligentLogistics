"""Decision Engine for the V_APP gate management system.

This module implements the core decision logic that correlates license-plate
detection events with hazard-plate detection events for the same truck, queries
the scheduling API for matching appointments, and publishes an access decision
to the downstream Kafka topic.

Typical usage:
    config = DecisionEngineConfig()
    engine = DecisionEngine(config=config)
    engine.start()
"""

import logging
import time
from prometheus_client import Counter, Histogram # type: ignore
from pydantic_settings import BaseSettings # type: ignore
from pydantic import Field # type: ignore
from shared.src.utils import load_from_file
from shared.src.kafka_wrapper import KafkaConsumerWrapper, KafkaProducerWrapper
from shared.src.kafka_protocol import (
    HazardPlateResultsMessage, KafkaMessageProto, DecisionResultsMessage,
    LicensePlateResultsMessage, Message, KafkaTopicFactory
)
from V_APP.shared.src.plate_matcher import PlateMatcher
from V_APP.shared.src.database_client import DatabaseClient
from enum import Enum


logger = logging.getLogger("DecisionEngine")


class DecisionStatus(Enum):
    """Possible outcomes of the automated decision process.

    Attributes:
        ACCEPTED: The truck's license plate matched a scheduled appointment
            and access is granted automatically.
        MANUAL_REVIEW: The automated process could not reach a confident
            decision; an operator must review the event.
    """

    ACCEPTED = "ACCEPTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class DecisionEngineConfig(BaseSettings):
    """Configuration for the Decision Engine, loaded from environment variables."""
    kafka_bootstrap: str = Field(default="10.255.32.70:9092")
    gate_id: str = Field(default="1")
    api_url: str = Field(default="http://localhost:8080/api/v1")
    time_tolerance_minutes: int = Field(default=30)
    max_levenshtein_distance: int = Field(default=2)
    expiration_time_hours: int = Field(default=24)
    un_numbers_file: str = Field(default="./data/un_numbers.txt")
    kemler_codes_file: str = Field(default="./data/kemler_codes.txt")


class DecisionEngine:
    """Stateful service that correlates LP and HZ Kafka messages and emits decisions.

    The engine maintains two in-memory buffers — one for license-plate results
    (LP) and one for hazard-plate results (HZ). Whenever both buffers hold an
    entry for the same ``truck_id``, a decision is made and the entries are
    cleared. Stale entries are evicted on every loop iteration to prevent
    unbounded memory growth.

    All heavy dependencies (Kafka wrappers, plate matcher, database client) are
    injectable to facilitate unit testing without live infrastructure.
    """

    def __init__(
        self,
        config: DecisionEngineConfig | None = None,
        kafka_producer: KafkaProducerWrapper | None = None,
        kafka_consumer: KafkaConsumerWrapper | None = None,
        plate_matcher: PlateMatcher | None = None,
        database_client: DatabaseClient | None = None,
    ) -> None:
        """Initialise the engine and all its dependencies.

        Args:
            config: Engine configuration. When ``None``, a default
                ``DecisionEngineConfig`` is constructed, which will read
                values from environment variables.
            kafka_producer: Pre-constructed producer. When ``None``, a new
                ``KafkaProducerWrapper`` is created with the configured broker.
            kafka_consumer: Pre-constructed consumer. When ``None``, a new
                ``KafkaConsumerWrapper`` is created subscribed to the LP and HZ
                topics for this gate.
            plate_matcher: Strategy object for fuzzy license-plate matching.
                When ``None``, a default ``PlateMatcher`` is instantiated.
            database_client: Client for the scheduling REST API. When ``None``,
                a default ``DatabaseClient`` is instantiated with the configured
                URL and gate ID.
        """
        # The loop is started explicitly via start(); False prevents accidental
        # blocking if the constructor is called without immediately running.
        self.running = False
        self.config = config or DecisionEngineConfig()

        # Topic names via factory — single source of truth
        self.produce_topic = KafkaTopicFactory.agent_decision(self.config.gate_id)
        self._lp_topic = KafkaTopicFactory.license_plate_results(self.config.gate_id)
        self._hz_topic = KafkaTopicFactory.hazard_plate_results(self.config.gate_id)

        # Load UN numbers — fall back to an empty dict so the engine can still
        # run (decisions will lack descriptions but will not crash).
        try:
            self.un_numbers = load_from_file(self.config.un_numbers_file, separator="|")
            logger.info(f"Loaded {len(self.un_numbers)} UN numbers.")
        except Exception:
            logger.exception("Error loading UN numbers")
            self.un_numbers = {}

        # Load Kemler codes — same degraded-mode strategy as UN numbers above.
        try:
            self.kemler_codes = load_from_file(self.config.kemler_codes_file, separator="|")
            logger.info(f"Loaded {len(self.kemler_codes)} Kemler codes.")
        except Exception:
            logger.exception("Error loading Kemler codes")
            self.kemler_codes = {}

        # Store typed message objects instead of dicts; keyed by truck_id.
        self.lp_buffer: dict[str, LicensePlateResultsMessage] = {}
        self.hz_buffer: dict[str, HazardPlateResultsMessage] = {}

        # Pre-compute once so _clear_stale_buffer_entries() avoids repeated
        # multiplication on every loop iteration.
        self.expiration_time_seconds = self.config.expiration_time_hours * 3600

        # Dependencies — injectable for testing
        self.kafka_producer = kafka_producer or KafkaProducerWrapper(self.config.kafka_bootstrap)
        self.kafka_consumer = kafka_consumer or KafkaConsumerWrapper(
            self.config.kafka_bootstrap, "decision-engine-group", [self._lp_topic, self._hz_topic]
        )
        self.plate_matcher = plate_matcher or PlateMatcher()
        self.database_client = database_client or DatabaseClient(self.config.api_url, self.config.gate_id)

        self._init_metrics()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _init_metrics(self) -> None:
        """Initialize Prometheus metrics."""
        self.decisions_processed = Counter(
            'decision_engine_decisions_processed_total',
            'Total number of decisions made'
        )
        self.decision_latency = Histogram(
            'decision_engine_decision_latency_seconds',
            'Time spent making a decision',
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0]
        )
        self.approved_access = Counter(
            'decision_engine_approved_access_total',
            'Total number of approved access decisions'
        )
        self.manual_review_decisions = Counter(
            'decision_engine_manual_review_total',
            'Total number of decisions routed to manual review'
        )

    def start(self) -> None:
        """Start the blocking main loop and consume Kafka messages indefinitely.

        Sets ``self.running = True`` implicitly via the ``while`` condition,
        then consumes messages from the LP and HZ Kafka topics in a tight loop.
        Each iteration:
          1. Evicts stale buffer entries.
          2. Polls for a single typed message (1-second timeout).
          3. Dispatches the message to the appropriate buffer.
          4. Attempts to make a decision if both LP and HZ are now available.

        Exceptions raised by individual message handling are caught and logged
        so that a single bad message cannot terminate the entire service.
        The loop exits when ``stop()`` is called from another thread or when
        an unhandled ``KeyboardInterrupt`` propagates out of the inner block.
        Resources are always released in the ``finally`` clause.
        """
        self.running = True
        logger.info("Starting main loop …")
        try:
            while self.running:
                try:
                    # Clear stale buffer entries
                    self._clear_stale_buffer_entries()

                    topic, message_obj, truck_id = self.kafka_consumer.consume_typed_message(timeout=1.0)

                    # consume_typed_message returns None-filled tuples on timeout.
                    if message_obj is None or topic is None or truck_id is None:
                        continue

                    # Type-specific logging — each branch logs the fields most
                    # relevant for its message type.
                    if isinstance(message_obj, LicensePlateResultsMessage):
                        logger.debug(
                            f"Received LP for truck {truck_id}: "
                            f"{message_obj.license_plate} (conf={message_obj.confidence:.2f})"
                        )
                    elif isinstance(message_obj, HazardPlateResultsMessage):
                        logger.debug(
                            f"Received HZ for truck {truck_id}: "
                            f"UN={message_obj.un}, Kemler={message_obj.kemler} (conf={message_obj.confidence:.2f})"
                        )

                    self._store_in_buffer(topic, truck_id, message_obj)
                    self._try_process_truck(truck_id)
                except Exception:
                    # Log but do not re-raise so the loop survives transient errors.
                    logger.exception("Unexpected error")
        finally:
            self._cleanup_resources()

    def stop(self) -> None:
        """Signal the main loop to exit on its next iteration.

        Thread-safe for a single writer because assignment to a boolean is
        atomic in CPython. Does not block; the loop exits after the current
        ``consume_typed_message`` call returns (at most one ``timeout`` second).
        """
        logger.info("Stopping…")
        self.running = False

    # ------------------------------------------------------------------
    # Decision logic
    # ------------------------------------------------------------------

    def _make_decision(
        self,
        truck_id: str,
        lp_msg: LicensePlateResultsMessage,
        hz_msg: HazardPlateResultsMessage,
    ) -> None:
        """Evaluate a complete LP + HZ pair and publish an access decision.

        Decision flow (each branch publishes a result and returns early):
          1. If the detected plate is ``"N/A"``, route to manual review.
          2. If the API is unavailable or raises, route to manual review.
          3. If no appointments are found in the DB, route to manual review.
          4. If the plate cannot be fuzzy-matched to any candidate, route to
             manual review.
          5. Otherwise, accept the truck automatically.

        Args:
            truck_id: Unique identifier for the truck being evaluated.
            lp_msg: License-plate detection result for this truck.
            hz_msg: Hazard-plate detection result for this truck.
        """
        logger.info(f"Both LP and HZ available for truck_id='{truck_id}'. Making decision…")
        start_time = time.time()

        license_plate = lp_msg.license_plate
        raw_un = hz_msg.un
        raw_kemler = hz_msg.kemler

        # Enrich codes with human-readable descriptions
        un_desc = self._get_un_description(raw_un) if raw_un else None
        kemler_desc = self._get_kemler_description(raw_kemler) if raw_kemler else None
        un_number = f"{raw_un}: {un_desc}" if un_desc and raw_un else raw_un
        kemler_code = f"{raw_kemler}: {kemler_desc}" if kemler_desc and raw_kemler else raw_kemler

        logger.info(
            f"Extracted data: License Plate: '{license_plate}' "
            f"UN: '{un_number}' Kemler: '{kemler_code}'"
        )

        # Handle missing license plate
        if license_plate == "N/A":
            self._publish_decision(
                truck_id, license_plate, lp_msg, hz_msg, un_number, kemler_code,
                decision=DecisionStatus.MANUAL_REVIEW.value,
                reason="license_plate_not_detected",
                start_time=start_time,
            )
            return

        # Query and evaluate appointments
        try:
            appointments = self.database_client.get_appointments()
            logger.debug(f"Appointments query result: {appointments}")
        except Exception:
            logger.exception("Error querying appointments")
            appointments = None  # treated as "no data" in the checks below

        # Handle API unavailability
        if appointments is not None and self.database_client.is_api_unavailable(appointments.get("message", "")):
            self._publish_decision(
                truck_id, license_plate, lp_msg, hz_msg, un_number, kemler_code,
                decision=DecisionStatus.MANUAL_REVIEW.value,
                reason="api_unavailable",
                start_time=start_time,
            )
            return

        # Handle no appointments found
        if appointments is None or appointments.get("found") is False:
            self._publish_decision(
                truck_id, license_plate, lp_msg, hz_msg, un_number, kemler_code,
                decision=DecisionStatus.MANUAL_REVIEW.value,
                reason="empty_db_appointments",
                start_time=start_time,
            )
            return

        # Match license plate with appointments
        candidate_plates = [appt["license_plate"] for appt in appointments.get("candidates", [])]
        matched_plate = self.plate_matcher.match_plate(license_plate, candidate_plates)

        if matched_plate is None:
            self._publish_decision(
                truck_id, license_plate, lp_msg, hz_msg, un_number, kemler_code,
                decision=DecisionStatus.MANUAL_REVIEW.value,
                reason="license_plate_not_found",
                start_time=start_time,
            )
        else:
            self._publish_decision(
                truck_id, license_plate, lp_msg, hz_msg, un_number, kemler_code,
                decision=DecisionStatus.ACCEPTED.value,
                reason="license_plate_matched",
                start_time=start_time,
            )

    def _publish_decision(
        self,
        truck_id: str,
        license_plate: str,
        lp_msg: LicensePlateResultsMessage,
        hz_msg: HazardPlateResultsMessage,
        un_number: str,
        kemler_code: str,
        decision: str,
        reason: str,
        start_time: float,
        alerts: list | None = None,
        route: str = "",
    ) -> None:
        """Serialise and publish the final decision to the output Kafka topic.

        Constructs a ``DecisionResultsMessage`` via the protocol factory,
        produces it to the per-gate decision topic with the ``truckId`` header,
        and records the associated Prometheus metrics.

        Args:
            truck_id: Unique identifier forwarded as the Kafka message header.
            license_plate: Detected (or sentinel) plate string.
            lp_msg: Original LP message — provides the license crop URL.
            hz_msg: Original HZ message — provides the hazard crop URL.
            un_number: UN number string, optionally enriched with its description.
            kemler_code: Kemler code string, optionally enriched with its description.
            decision: One of the ``DecisionStatus`` enum values.
            reason: Machine-readable string identifying the decision branch taken.
            start_time: ``time.time()`` value recorded at the start of
                ``_make_decision()``; used to compute decision latency.
            alerts: Optional list of alert payloads to include in the message.
                Defaults to an empty list when ``None``.
            route: Optional routing instruction for the gate hardware.
                Defaults to an empty string.
        """
        logger.info(f"Decision: [{decision} - {reason}]")

        message = KafkaMessageProto.decision_result(
            license_plate=license_plate,
            license_crop_url=lp_msg.crop_url,
            un=un_number,
            kemler=kemler_code,
            hazard_crop_url=hz_msg.crop_url,
            alerts=alerts or [],
            route=route,
            decision=decision,
            decision_reason=reason,
            decision_source="automated",
        )

        self.kafka_producer.produce(
            topic=self.produce_topic,
            data=message.to_dict(),
            headers={"truckId": truck_id},
        )

        self._record_decision_metrics(decision, start_time)

    # ------------------------------------------------------------------
    # Buffer management
    # ------------------------------------------------------------------

    def _try_process_truck(self, truck_id: str) -> None:
        """Attempt to make a decision if both LP and HZ data are buffered.

        Does nothing when only one of the two message types has arrived yet.
        On success, the entries are removed from both buffers immediately so
        that a subsequent message for the same truck starts a fresh pair.

        Args:
            truck_id: Identifier of the truck to evaluate.
        """
        if truck_id not in self.lp_buffer or truck_id not in self.hz_buffer:
            # Wait until the partner message arrives before deciding.
            return

        lp_msg = self.lp_buffer[truck_id]
        hz_msg = self.hz_buffer[truck_id]

        self._make_decision(truck_id, lp_msg, hz_msg)

        del self.lp_buffer[truck_id]
        del self.hz_buffer[truck_id]

        logger.debug(f"Buffers cleaned for truck_id='{truck_id}'")

    def _store_in_buffer(self, topic: str, truck_id: str, msg: Message) -> None:
        """Route an incoming typed message to the correct buffer.

        Performs a runtime type-check as a defensive guard against malformed
        routing in the Kafka consumer layer. Messages of an unexpected type
        for a given topic are discarded with a warning rather than silently
        overwriting valid buffered data.

        Args:
            topic: The Kafka topic the message was consumed from.
            truck_id: Identifier used as the buffer key.
            msg: The typed, deserialized message object.
        """
        if topic == self._lp_topic:
            if not isinstance(msg, LicensePlateResultsMessage):
                logger.warning(f"Expected LicensePlateResultsMessage but got {type(msg).__name__}")
                return
            self.lp_buffer[truck_id] = msg
            logger.debug(f"LP data stored for truck_id='{truck_id}': {msg.license_plate}")

        elif topic == self._hz_topic:
            if not isinstance(msg, HazardPlateResultsMessage):
                logger.warning(f"Expected HazardPlateResultsMessage but got {type(msg).__name__}")
                return
            self.hz_buffer[truck_id] = msg
            logger.debug(f"HZ data stored for truck_id='{truck_id}': UN={msg.un}, Kemler={msg.kemler}")

    def _clear_stale_buffer_entries(self) -> None:
        """Evict buffer entries whose partner message never arrived in time.

        Iterates over a snapshot of each buffer's keys (via ``list(...)``) so
        that deletions during iteration do not raise ``RuntimeError``. An entry
        is considered stale when the wall-clock age of its message exceeds
        ``self.expiration_time_seconds``.

        Note:
            Assumes that ``LicensePlateResultsMessage.timestamp`` and
            ``HazardPlateResultsMessage.timestamp`` are Unix epoch floats.
        """
        current_time = time.time()

        for truck_id in list(self.lp_buffer.keys()):
            lp_msg = self.lp_buffer[truck_id]
            if current_time - lp_msg.timestamp > self.expiration_time_seconds:
                del self.lp_buffer[truck_id]
                logger.debug(f"Cleared stale LP entry for truck_id='{truck_id}'")

        for truck_id in list(self.hz_buffer.keys()):
            hz_msg = self.hz_buffer[truck_id]
            if current_time - hz_msg.timestamp > self.expiration_time_seconds:
                del self.hz_buffer[truck_id]
                logger.debug(f"Cleared stale HZ entry for truck_id='{truck_id}'")

    # ------------------------------------------------------------------
    # Lookup helpers
    # ------------------------------------------------------------------

    def _get_un_description(self, un_number: str) -> str | None:
        """Get description for UN number."""
        return self.un_numbers.get(str(un_number), "Unknown UN Number")

    def _get_kemler_description(self, kemler_code: str) -> str | None:
        """Get description for Kemler code."""
        return self.kemler_codes.get(str(kemler_code), "Unknown Kemler Code")

    def _record_decision_metrics(self, decision: str, start_time: float):
        """Records Prometheus metrics for the decision."""
        duration = time.time() - start_time
        self.decision_latency.observe(duration)
        self.decisions_processed.inc()

        if decision == DecisionStatus.ACCEPTED.value:
            self.approved_access.inc()
        elif decision == DecisionStatus.MANUAL_REVIEW.value:
            self.manual_review_decisions.inc()

    def _cleanup_resources(self) -> None:
        """Flush and close all Kafka connections gracefully.

        Called unconditionally from the ``finally`` block in ``start()``
        to ensure that in-flight producer messages are delivered and
        connection resources are released even on abnormal exit.
        """
        logger.info("Freeing resources…")
        self.kafka_consumer.close()
        self.kafka_producer.flush()
        self.kafka_producer.close()