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
from decision_engine.src.database_client import DatabaseClient
from enum import Enum


logger = logging.getLogger("DecisionEngine")


class DecisionStatus(Enum):
    ACCEPTED = "ACCEPTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class DecisionEngineConfig(BaseSettings):
    """Configuration for the Decision Engine, loaded from environment variables."""
    kafka_bootstrap: str = Field(default="10.255.32.70:9092")
    gate_id: str = Field(default="1")
    api_url: str = Field(default="http://localhost:8080/api/v1")
    time_tolerance_minutes: int = Field(default=30)
    max_levenshtein_distance: int = Field(default=2)



class DecisionEngine:
    def __init__(
        self,
        config: DecisionEngineConfig | None = None,
        kafka_producer: KafkaProducerWrapper | None = None,
        kafka_consumer: KafkaConsumerWrapper | None = None,
        plate_matcher: PlateMatcher | None = None,
        database_client: DatabaseClient | None = None,
    ) -> None:
        self.running = True
        self.config = config or DecisionEngineConfig()

        # Topic names via factory — single source of truth
        self.produce_topic = KafkaTopicFactory.agent_decision(self.config.gate_id)
        consume_topics = [
            KafkaTopicFactory.license_plate_results(self.config.gate_id),
            KafkaTopicFactory.hazard_plate_results(self.config.gate_id),
        ]

        self.un_numbers = load_from_file("./data/un_numbers.txt", separator="|")
        self.kemler_codes = load_from_file("./data/kemler_codes.txt", separator="|")
        logger.info(f"Loaded {len(self.un_numbers)} UN numbers and {len(self.kemler_codes)} Kemler codes.")

        # Store typed message objects instead of dicts
        self.lp_buffer: dict[str, LicensePlateResultsMessage] = {}
        self.hz_buffer: dict[str, HazardPlateResultsMessage] = {}

        # Dependencies — injectable for testing
        self.kafka_producer = kafka_producer or KafkaProducerWrapper(self.config.kafka_bootstrap)
        self.kafka_consumer = kafka_consumer or KafkaConsumerWrapper(
            self.config.kafka_bootstrap, "decision-engine-group", consume_topics
        )
        self.plate_matcher = plate_matcher or PlateMatcher()
        self.database_client = database_client or DatabaseClient(self.config.api_url, self.config.gate_id)

        self._init_metrics()

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
        self.denied_access = Counter(
            'decision_engine_denied_access_total',
            'Total number of denied access decisions'
        )

    def loop(self):
        logger.info("Starting main loop …")
        try:
            while self.running:
                topic, message_obj, truck_id = self.kafka_consumer.consume_typed_message(timeout=1.0)

                if message_obj is None or topic is None or truck_id is None:
                    continue

                # Type-specific logging
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

        except KeyboardInterrupt:
            logger.info("Interrupted by user.")
        except Exception as e:
            logger.exception(f"Unexpected error: {e}")
        finally:
            self._cleanup_resources()

    def stop(self):
        logger.info("Stopping…")
        self.running = False

    def _make_decision(
        self,
        truck_id: str,
        lp_msg: LicensePlateResultsMessage,
        hz_msg: HazardPlateResultsMessage,
    ):
        """Makes a decision for the truck based on LP and HZ message objects."""
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
        appointments = self.database_client.get_appointments()
        logger.debug(f"Appointments query result: {appointments}")

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
        un_number: str | None,
        kemler_code: str | None,
        decision: str,
        reason: str,
        start_time: float,
        alerts: list | None = None,
        route: str = "",
    ) -> None:
        """Build, publish the Kafka decision message and record metrics."""
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

    def _try_process_truck(self, truck_id: str):
        """Attempts to process a truck if both LP and HZ data are available."""
        if truck_id not in self.lp_buffer or truck_id not in self.hz_buffer:
            return

        lp_msg = self.lp_buffer[truck_id]
        hz_msg = self.hz_buffer[truck_id]

        self._make_decision(truck_id, lp_msg, hz_msg)

        del self.lp_buffer[truck_id]
        del self.hz_buffer[truck_id]

        logger.debug(f"Buffers cleaned for truck_id='{truck_id}'")

    def _store_in_buffer(self, topic: str, truck_id: str, msg: Message):
        """Stores typed message object in the appropriate buffer."""
        lp_topic = KafkaTopicFactory.license_plate_results(self.config.gate_id)
        hz_topic = KafkaTopicFactory.hazard_plate_results(self.config.gate_id)

        if topic == lp_topic:
            if not isinstance(msg, LicensePlateResultsMessage):
                logger.warning(f"Expected LicensePlateResultsMessage but got {type(msg).__name__}")
                return
            self.lp_buffer[truck_id] = msg
            logger.debug(f"LP data stored for truck_id='{truck_id}': {msg.license_plate}")

        elif topic == hz_topic:
            if not isinstance(msg, HazardPlateResultsMessage):
                logger.warning(f"Expected HazardPlateResultsMessage but got {type(msg).__name__}")
                return
            self.hz_buffer[truck_id] = msg
            logger.debug(f"HZ data stored for truck_id='{truck_id}': UN={msg.un}, Kemler={msg.kemler}")

    def _get_appointment_from_plate(self, license_plate: str, appointments: list) -> dict | None:
        """
        Find appointment(s) matching the license plate.
        If multiple appointments exist for the same plate, returns the one with the earliest scheduled_time.
        """
        matches = [appt for appt in appointments if appt.get("license_plate") == license_plate]

        if not matches:
            return None

        if len(matches) == 1:
            return matches[0]

        # Multiple matches - return the earliest scheduled appointment
        return min(matches, key=lambda appt: appt.get("scheduled_time", ""))

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
            self.denied_access.inc()

    def _cleanup_resources(self):
        """Releases resources gracefully."""
        logger.info("Freeing resources…")
        self.kafka_consumer.close()
        self.kafka_producer.flush()