"""Infraction Engine for the V_APP gate management system.

This module implements the infraction-detection logic that correlates
license-plate detection events with hazard-plate detection events across
multiple gates.
"""

import time
from typing import Tuple
from prometheus_client import Counter # type: ignore
from shared.src.kafka_protocol import (
    HazardPlateResultsMessage, KafkaMessageProto,
    LicensePlateResultsMessage, KafkaTopicFactory
)
from V_APP.shared.src.base_decision_engine import BaseDecisionEngine, BaseDecisionEngineConfig


class InfractionEngineConfig(BaseDecisionEngineConfig):
    """Configuration for the Infraction Engine."""
    pass


class InfractionEngine(BaseDecisionEngine):
    """Stateful service that determines hazardous-goods infractions."""

    def _get_active_gate_ids(self) -> list[str]:
        return self.config.infraction_gate_id_list

    def _get_consumer_group(self) -> str:
        return "infraction-engine-group"

    def _init_specific_metrics(self) -> None:
        """Initialize Prometheus metrics for InfractionEngine."""
        self.infractions_processed = Counter(
            'infraction_engine_processed_total',
            'Total number of infraction evaluations made'
        )
        self.infractions_detected = Counter(
            'infraction_engine_infractions_total',
            'Total number of highway infractions detected'
        )
        self.no_infractions = Counter(
            'infraction_engine_no_infractions_total',
            'Total number of evaluations with no infraction'
        )

    def _execute_logic(
        self,
        gate_id: str,
        truck_id: str,
        lp_msg: LicensePlateResultsMessage,
        hz_msg: HazardPlateResultsMessage,
    ) -> None:
        """Evaluate whether a truck is committing a hazardous-goods infraction."""
        self.logger.info(f"Both LP and HZ available for truck_id='{truck_id}' (gate {gate_id}). Evaluating infraction…")
        start_time = time.time()

        license_plate = lp_msg.license_plate
        un_number, kemler_code = self._enrich_hazard_codes(hz_msg.un, hz_msg.kemler)

        self.logger.info(
            f"Gate {gate_id} | Extracted: LP='{license_plate}' UN='{un_number}' Kemler='{kemler_code}'"
        )

        # If the truck has no hazardous goods, there can be no infraction.
        if not self._is_hazardous(hz_msg.un, hz_msg.kemler):
            self.logger.info(f"Truck '{truck_id}' (gate {gate_id}) carries no hazardous goods — no infraction.")
            self._publish_infraction(
                gate_id, truck_id, license_plate, lp_msg, hz_msg,
                un_number, kemler_code,
                infraction=False,
                start_time=start_time,
            )
            return

        # Truck IS hazardous — check if it has a matching appointment at THIS gate.
        has_appointment, license_plate = self._has_matching_appointment("1", license_plate)
        infraction = True
        
        if has_appointment:
            self.logger.info(f"Truck '{license_plate}' (gate {gate_id}) is hazardous and a valid appointment — infraction detected")
        else:
            self.logger.warning(f"Truck '{license_plate}' (gate {gate_id}) is hazardous but could NOT be matched to any appointment - infraction detected regardless")

        self._publish_infraction(
            gate_id, truck_id, license_plate, lp_msg, hz_msg,
            un_number, kemler_code,
            infraction=infraction,
            start_time=start_time,
        )

    def _is_hazardous(self, raw_un: str, raw_kemler: str) -> bool:
        """Determine if the truck carries hazardous goods."""
        return bool(raw_un and raw_un != "N/A") or bool(raw_kemler and raw_kemler != "N/A")

    def _has_matching_appointment(self, gate_id: str, license_plate: str) -> Tuple[bool, str]:
        """Check whether the license plate matches any scheduled appointment for this gate."""
        if license_plate == "N/A":
            return False, license_plate

        try:
            # Temporarily override gate_id for the query
            original_gid = self.database_client.gate_id
            self.database_client.gate_id = gate_id
            appointments = self.database_client.get_appointments()
            self.database_client.gate_id = original_gid
        except Exception:
            self.logger.exception(f"Error querying appointments for gate {gate_id}")
            return False, license_plate

        if appointments is not None and self.database_client.is_api_unavailable(appointments.get("message", "")):
            return False, license_plate

        if appointments is None or appointments.get("found") is False:
            return False, license_plate

        candidate_plates = [appt["license_plate"] for appt in appointments.get("candidates", [])]
        matched_plate = self.plate_matcher.match_plate(license_plate, candidate_plates)
        
        if matched_plate is None:
            return False, license_plate

        return matched_plate is not None, matched_plate

    def _publish_infraction(
        self,
        gate_id: str,
        truck_id: str,
        license_plate: str,
        lp_msg: LicensePlateResultsMessage,
        hz_msg: HazardPlateResultsMessage,
        un_number: str,
        kemler_code: str,
        infraction: bool,
        start_time: float,
    ) -> None:
        """Build and publish the infraction decision to the gate-specific topic."""
        produce_topic = KafkaTopicFactory.infraction_decision(gate_id)
        self.logger.info(f"Infraction result for gate {gate_id}: infraction={infraction}")

        message = KafkaMessageProto.infraction_decision(
            license_plate=license_plate,
            license_crop_url=lp_msg.crop_url,
            un=un_number,
            kemler=kemler_code,
            hazard_crop_url=hz_msg.crop_url,
            infraction=infraction,
        )

        self.kafka_producer.produce(
            topic=produce_topic,
            data=message.to_dict(),
            headers={"truckId": truck_id},
        )

        self._record_infraction_metrics(infraction, start_time)

    def _record_infraction_metrics(self, infraction: bool, start_time: float) -> None:
        """Record Prometheus metrics for the infraction evaluation."""
        duration = time.time() - start_time
        self.processing_latency.observe(duration)
        self.infractions_processed.inc()

        if infraction:
            self.infractions_detected.inc()
        else:
            self.no_infractions.inc()
