"""Infraction Engine for the V_APP gate management system.

This module implements the infraction-detection logic that correlates
license-plate detection events with hazard-plate detection events for the
same truck, matches the plate against scheduled appointments, and determines
whether the truck constitutes an infraction (carries hazardous goods without
a matching appointment).  The result — ``infraction: True`` or
``infraction: False`` — is published to the ``infraction-decision-{gate_id}``
Kafka topic.

Typical usage:
    config = InfractionEngineConfig()
    engine = InfractionEngine(config=config)
    engine.start()
"""

import logging
import time
from prometheus_client import Counter, Histogram  # type: ignore
from pydantic_settings import BaseSettings  # type: ignore
from pydantic import Field  # type: ignore
from shared.src.utils import load_from_file
from shared.src.kafka_wrapper import KafkaConsumerWrapper, KafkaProducerWrapper
from shared.src.kafka_protocol import (
    HazardPlateResultsMessage, KafkaMessageProto,
    LicensePlateResultsMessage, Message, KafkaTopicFactory
)
from V_APP.shared.src.plate_matcher import PlateMatcher
from V_APP.shared.src.database_client import DatabaseClient


logger = logging.getLogger("InfractionEngine")


class InfractionEngineConfig(BaseSettings):
    """Configuration for the Infraction Engine, loaded from environment variables.

    Attributes:
        kafka_bootstrap: Kafka broker address in ``host:port`` format.
        gate_id: Logical identifier for the physical gate this engine serves.
        api_url: Base URL of the scheduling REST API.
        time_tolerance_minutes: Allowed drift (in minutes) between a truck's
            arrival time and its scheduled appointment slot.
        max_levenshtein_distance: Maximum edit distance accepted by the plate
            matcher when comparing a detected plate to a candidate in the DB.
        expiration_time_hours: Maximum age (hours) of a buffered LP or HZ
            message before it is evicted as stale.
        un_numbers_file: Path to the pipe-separated UN-number lookup file.
        kemler_codes_file: Path to the pipe-separated Kemler-code lookup file.
    """

    kafka_bootstrap: str = Field(default="10.255.32.70:9092")
    gate_id: str = Field(default="1")
    api_url: str = Field(default="http://localhost:8080/api/v1")
    time_tolerance_minutes: int = Field(default=30)
    max_levenshtein_distance: int = Field(default=2)
    expiration_time_hours: int = Field(default=24)
    un_numbers_file: str = Field(default="./data/un_numbers.txt")
    kemler_codes_file: str = Field(default="./data/kemler_codes.txt")


class InfractionEngine:
    """Stateful service that determines whether a truck is committing a hazardous-goods infraction.

    The engine correlates LP and HZ Kafka messages by ``truck_id``. Once both
    are available it checks whether hazardous material is present (non-empty
    UN or Kemler code), matches the license plate to the scheduling DB, and
    publishes an ``InfractionDecisionMessage`` with ``infraction`` set to
    ``True`` or ``False``.

    Infraction logic:
      - If the truck carries NO hazardous goods → no infraction (``False``).
      - If the truck carries hazardous goods AND its plate matches a scheduled
        appointment → no infraction (``False``).
      - If the truck carries hazardous goods but there is NO matching
        appointment (or the plate/API is unavailable) → infraction (``True``).
    """

    def __init__(
        self,
        config: InfractionEngineConfig | None = None,
        kafka_producer: KafkaProducerWrapper | None = None,
        kafka_consumer: KafkaConsumerWrapper | None = None,
        plate_matcher: PlateMatcher | None = None,
        database_client: DatabaseClient | None = None,
    ) -> None:
        """Initialise the engine and all its dependencies.

        Args:
            config: Engine configuration. When ``None``, a default
                ``InfractionEngineConfig`` is constructed from env vars.
            kafka_producer: Pre-constructed producer for testing injection.
            kafka_consumer: Pre-constructed consumer for testing injection.
            plate_matcher: Strategy object for fuzzy license-plate matching.
            database_client: Client for the scheduling REST API.
        """
        self.running = False
        self.config = config or InfractionEngineConfig()

        # Topic names via factory — single source of truth
        self.produce_topic = KafkaTopicFactory.infraction_decision(self.config.gate_id)
        self._lp_topic = KafkaTopicFactory.license_plate_results(self.config.gate_id)
        self._hz_topic = KafkaTopicFactory.hazard_plate_results(self.config.gate_id)

        # Load UN numbers — fall back to empty dict on failure.
        try:
            self.un_numbers = load_from_file(self.config.un_numbers_file, separator="|")
            logger.info(f"Loaded {len(self.un_numbers)} UN numbers.")
        except Exception:
            logger.exception("Error loading UN numbers")
            self.un_numbers = {}

        # Load Kemler codes — same degraded-mode strategy.
        try:
            self.kemler_codes = load_from_file(self.config.kemler_codes_file, separator="|")
            logger.info(f"Loaded {len(self.kemler_codes)} Kemler codes.")
        except Exception:
            logger.exception("Error loading Kemler codes")
            self.kemler_codes = {}

        # In-memory buffers keyed by truck_id.
        self.lp_buffer: dict[str, LicensePlateResultsMessage] = {}
        self.hz_buffer: dict[str, HazardPlateResultsMessage] = {}

        self.expiration_time_seconds = self.config.expiration_time_hours * 3600

        # Dependencies — injectable for testing
        self.kafka_producer = kafka_producer or KafkaProducerWrapper(self.config.kafka_bootstrap)
        self.kafka_consumer = kafka_consumer or KafkaConsumerWrapper(
            self.config.kafka_bootstrap, "infraction-engine-group", [self._lp_topic, self._hz_topic]
        )
        self.plate_matcher = plate_matcher or PlateMatcher()
        self.database_client = database_client or DatabaseClient(self.config.api_url, self.config.gate_id)

        self._init_metrics()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _init_metrics(self) -> None:
        """Initialize Prometheus metrics."""
        self.infractions_processed = Counter(
            'infraction_engine_processed_total',
            'Total number of infraction evaluations made'
        )
        self.infraction_latency = Histogram(
            'infraction_engine_latency_seconds',
            'Time spent evaluating an infraction',
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0]
        )
        self.infractions_detected = Counter(
            'infraction_engine_infractions_total',
            'Total number of highway infractions detected'
        )
        self.no_infractions = Counter(
            'infraction_engine_no_infractions_total',
            'Total number of evaluations with no infraction'
        )

    def start(self) -> None:
        """Start the blocking main loop consuming LP and HZ Kafka messages.

        Each iteration evicts stale buffer entries, polls for a single typed
        message, buffers it, and attempts an infraction evaluation when both
        LP and HZ are available for the same truck.
        """
        self.running = True
        logger.info("Starting main loop …")
        try:
            while self.running:
                try:
                    self._clear_stale_buffer_entries()

                    topic, message_obj, truck_id = self.kafka_consumer.consume_typed_message(timeout=1.0)

                    if message_obj is None or topic is None or truck_id is None:
                        continue

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
                    logger.exception("Unexpected error")
        finally:
            self._cleanup_resources()

    def stop(self) -> None:
        """Signal the main loop to exit on its next iteration."""
        logger.info("Stopping…")
        self.running = False

    # ------------------------------------------------------------------
    # Infraction logic
    # ------------------------------------------------------------------

    def _evaluate_infraction(
        self,
        truck_id: str,
        lp_msg: LicensePlateResultsMessage,
        hz_msg: HazardPlateResultsMessage,
    ) -> None:
        """Evaluate whether a truck is committing a hazardous-goods infraction.

        Logic:
          1. Check if the truck carries hazardous goods (non-empty UN or Kemler).
             If not → no infraction.
          2. Try to match the license plate against scheduled appointments.
             If a match is found → no infraction (authorised transport).
          3. Otherwise → infraction detected.

        Args:
            truck_id: Unique identifier for the truck being evaluated.
            lp_msg: License-plate detection result for this truck.
            hz_msg: Hazard-plate detection result for this truck.
        """
        logger.info(f"Both LP and HZ available for truck_id='{truck_id}'. Evaluating infraction…")
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

        # If the truck has no hazardous goods, there can be no infraction.
        if not self._is_hazardous(raw_un, raw_kemler):
            logger.info(f"Truck '{truck_id}' carries no hazardous goods — no infraction.")
            self._publish_infraction(
                truck_id, license_plate, lp_msg, hz_msg,
                un_number, kemler_code,
                infraction=False,
                start_time=start_time,
            )
            return

        # Truck IS hazardous — check if it has a matching appointment.
        has_appointment = self._has_matching_appointment(license_plate)

        if has_appointment:
            logger.info(f"Truck '{lp_msg.license_plate}' is hazardous but has a valid appointment — no infraction.")
        else:
            logger.warning(f"Truck '{lp_msg.license_plate}' is hazardous but could NOT be matched to any appointment.")

        self._publish_infraction(
            truck_id, license_plate, lp_msg, hz_msg,
            un_number, kemler_code,
            infraction=False,
            start_time=start_time,
        )

    def _is_hazardous(self, raw_un: str, raw_kemler: str) -> bool:
        """Determine if the truck carries hazardous goods.

        A truck is considered hazardous if either the UN number or the Kemler
        code is present (non-empty and not ``"N/A"``).

        Args:
            raw_un: The raw UN number string from the HZ agent.
            raw_kemler: The raw Kemler code string from the HZ agent.

        Returns:
            ``True`` if hazardous material is detected, ``False`` otherwise.
        """
        return bool(raw_un and raw_un != "N/A") or bool(raw_kemler and raw_kemler != "N/A")

    def _has_matching_appointment(self, license_plate: str) -> bool:
        """Check whether the license plate matches any scheduled appointment.

        Queries the scheduling API and fuzzy-matches the detected plate
        against all candidate plates. If the plate is ``"N/A"`` or the API
        is unavailable, returns ``False`` (no match).

        Args:
            license_plate: The detected license plate string.

        Returns:
            ``True`` if a matching appointment exists, ``False`` otherwise.
        """
        if license_plate == "N/A":
            logger.info("License plate is N/A — cannot match appointment.")
            return False

        # Query appointments
        try:
            appointments = self.database_client.get_appointments()
            logger.debug(f"Appointments query result: {appointments}")
        except Exception:
            logger.exception("Error querying appointments")
            return False

        # API unavailable
        if appointments is not None and self.database_client.is_api_unavailable(appointments.get("message", "")):
            logger.warning("API unavailable — treating as no match.")
            return False

        # No appointments found
        if appointments is None or appointments.get("found") is False:
            logger.info("No appointments found in database.")
            return False

        # Fuzzy-match plate against candidates
        candidate_plates = [appt["license_plate"] for appt in appointments.get("candidates", [])]
        matched_plate = self.plate_matcher.match_plate(license_plate, candidate_plates)

        if matched_plate is not None:
            return True

        return False

    def _publish_infraction(
        self,
        truck_id: str,
        license_plate: str,
        lp_msg: LicensePlateResultsMessage,
        hz_msg: HazardPlateResultsMessage,
        un_number: str,
        kemler_code: str,
        infraction: bool,
        start_time: float,
    ) -> None:
        """Build and publish the infraction decision to the output Kafka topic.

        Args:
            truck_id: Unique identifier forwarded as the Kafka message header.
            license_plate: Detected (or sentinel) plate string.
            lp_msg: Original LP message — provides the license crop URL.
            hz_msg: Original HZ message — provides the hazard crop URL.
            un_number: UN number string, optionally enriched with description.
            kemler_code: Kemler code string, optionally enriched with description.
            infraction: Whether the truck is committing a highway infraction.
            start_time: Wall-clock time at the start of evaluation for latency.
        """
        logger.info(f"Infraction result: infraction={infraction}")

        message = KafkaMessageProto.infraction_decision(
            license_plate=license_plate,
            license_crop_url=lp_msg.crop_url,
            un=un_number,
            kemler=kemler_code,
            hazard_crop_url=hz_msg.crop_url,
            infraction=infraction,
        )

        self.kafka_producer.produce(
            topic=self.produce_topic,
            data=message.to_dict(),
            headers={"truckId": truck_id},
        )

        self._record_metrics(infraction, start_time)

    # ------------------------------------------------------------------
    # Buffer management
    # ------------------------------------------------------------------

    def _try_process_truck(self, truck_id: str) -> None:
        """Attempt an infraction evaluation if both LP and HZ data are buffered.

        Args:
            truck_id: Identifier of the truck to evaluate.
        """
        if truck_id not in self.lp_buffer or truck_id not in self.hz_buffer:
            return

        lp_msg = self.lp_buffer[truck_id]
        hz_msg = self.hz_buffer[truck_id]

        self._evaluate_infraction(truck_id, lp_msg, hz_msg)

        del self.lp_buffer[truck_id]
        del self.hz_buffer[truck_id]

        logger.debug(f"Buffers cleaned for truck_id='{truck_id}'")

    def _store_in_buffer(self, topic: str, truck_id: str, msg: Message) -> None:
        """Route an incoming typed message to the correct buffer.

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
        """Evict buffer entries whose partner message never arrived in time."""
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

    # ------------------------------------------------------------------
    # Metrics & cleanup
    # ------------------------------------------------------------------

    def _record_metrics(self, infraction: bool, start_time: float) -> None:
        """Record Prometheus metrics for the infraction evaluation.

        Args:
            infraction: Whether an infraction was detected.
            start_time: Wall-clock time at the start of evaluation.
        """
        duration = time.time() - start_time
        self.infraction_latency.observe(duration)
        self.infractions_processed.inc()

        if infraction:
            self.infractions_detected.inc()
        else:
            self.no_infractions.inc()

    def _cleanup_resources(self) -> None:
        """Flush and close all Kafka connections gracefully."""
        logger.info("Freeing resources…")
        self.kafka_consumer.close()
        self.kafka_producer.flush()
        self.kafka_producer.close()