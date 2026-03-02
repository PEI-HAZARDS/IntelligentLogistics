"""Decision Engine for the V_APP gate management system.

This module implements the core decision logic that correlates license-plate
detection events with hazard-plate detection events across multiple gates.
"""

import time
from enum import Enum
from prometheus_client import Counter # type: ignore
from shared.src.kafka_protocol import (
    HazardPlateResultsMessage, KafkaMessageProto,
    LicensePlateResultsMessage, KafkaTopicFactory
)
from V_APP.shared.src.base_decision_engine import BaseDecisionEngine, BaseDecisionEngineConfig


class DecisionStatus(Enum):
    """Possible outcomes of the automated decision process."""
    ACCEPTED = "ACCEPTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class DecisionEngineConfig(BaseDecisionEngineConfig):
    """Configuration for the Decision Engine."""
    pass


class DecisionEngine(BaseDecisionEngine):
    """Stateful service that correlates LP and HZ Kafka messages and emits decisions."""

    def _get_active_gate_ids(self) -> list[str]:
        return self.config.decision_gate_id_list

    def _get_consumer_group(self) -> str:
        return "decision-engine-group"

    def _init_specific_metrics(self) -> None:
        """Initialize Prometheus metrics for DecisionEngine."""
        self.decisions_processed = Counter(
            'decision_engine_decisions_processed_total',
            'Total number of decisions made'
        )
        self.approved_access = Counter(
            'decision_engine_approved_access_total',
            'Total number of approved access decisions'
        )
        self.manual_review_decisions = Counter(
            'decision_engine_manual_review_total',
            'Total number of decisions routed to manual review'
        )

    def _execute_logic(
        self,
        gate_id: str,
        truck_id: str,
        lp_msg: LicensePlateResultsMessage,
        hz_msg: HazardPlateResultsMessage,
    ) -> None:
        """Evaluate a complete LP + HZ pair and publish an access decision."""
        self.logger.info(f"Both LP and HZ available for truck_id='{truck_id}' (gate {gate_id}). Making decision…")
        start_time = time.time()

        license_plate = lp_msg.license_plate
        un_number, kemler_code = self._enrich_hazard_codes(hz_msg.un, hz_msg.kemler)

        self.logger.info(
            f"Gate {gate_id} | Extracted: LP='{license_plate}' UN='{un_number}' Kemler='{kemler_code}'"
        )

        # Handle missing license plate
        if license_plate == "N/A":
            self._publish_decision(
                gate_id, truck_id, license_plate, lp_msg, hz_msg, un_number, kemler_code,
                decision=DecisionStatus.MANUAL_REVIEW.value,
                reason="license_plate_not_detected",
                start_time=start_time,
            )
            return

        # Query appointments for THIS gate
        try:
            # Temporarily override gate_id for the query
            original_gid = self.database_client.gate_id
            self.database_client.gate_id = gate_id
            appointments = self.database_client.get_appointments()
            self.database_client.gate_id = original_gid
        except Exception:
            self.logger.exception(f"Error querying appointments for gate {gate_id}")
            appointments = None

        # Handle API unavailability
        if appointments is not None and self.database_client.is_api_unavailable(appointments.get("message", "")):
            self._publish_decision(
                gate_id, truck_id, license_plate, lp_msg, hz_msg, un_number, kemler_code,
                decision=DecisionStatus.MANUAL_REVIEW.value,
                reason="api_unavailable",
                start_time=start_time,
            )
            return

        # Handle no appointments found
        if appointments is None or appointments.get("found") is False:
            self._publish_decision(
                gate_id, truck_id, license_plate, lp_msg, hz_msg, un_number, kemler_code,
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
                gate_id, truck_id, license_plate, lp_msg, hz_msg, un_number, kemler_code,
                decision=DecisionStatus.MANUAL_REVIEW.value,
                reason="license_plate_not_found",
                start_time=start_time,
            )
        else:
            self._publish_decision(
                gate_id, truck_id, license_plate, lp_msg, hz_msg, un_number, kemler_code,
                decision=DecisionStatus.ACCEPTED.value,
                reason="license_plate_matched" if matched_plate != self.last_truck_detected.get(gate_id) else "same_truck_detection", # Differente reason if same truck twice ina row
                start_time=start_time,
            )
            # Refresh the last detected truck to prevent duplicate decisions if the same truck is detected again shortly after
            self.last_truck_detected[gate_id] = matched_plate

    def _publish_decision(
        self,
        gate_id: str,
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
        """Serialise and publish the final decision to the gate-specific topic."""
        produce_topic = KafkaTopicFactory.agent_decision(gate_id)
        self.logger.info(f"Decision for gate {gate_id}: [{decision} - {reason}]")

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
            topic=produce_topic,
            data=message.to_dict(),
            headers={"truckId": truck_id},
        )

        self._record_decision_metrics(decision, start_time)

    def _record_decision_metrics(self, decision: str, start_time: float):
        """Records Prometheus metrics for the decision."""
        duration = time.time() - start_time
        self.processing_latency.observe(duration)
        self.decisions_processed.inc()

        if decision == DecisionStatus.ACCEPTED.value:
            self.approved_access.inc()
        elif decision == DecisionStatus.MANUAL_REVIEW.value:
            self.manual_review_decisions.inc()
