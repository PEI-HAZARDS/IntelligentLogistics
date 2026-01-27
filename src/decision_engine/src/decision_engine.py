import json
import logging
import os
import requests # type: ignore
import time
from datetime import datetime, timedelta
import itertools
from prometheus_client import start_http_server, Counter, Histogram # type: ignore
from shared.src.utils import load_from_file
from shared.src.kafka_wrapper import KafkaConsumerWrapper, KafkaProducerWrapper
from decision_engine.src.plate_matcher import PlateMatcher
from decision_engine.src.database_client import DatabaseClient
from enum import Enum


KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "10.255.32.143:9092")
GATE_ID = os.getenv("GATE_ID", "1")
KAFKA_PRODUCE_TOPIC = f"decision-results-{GATE_ID}"
KAFKA_CONSUME_TOPIC_LP = f"lp-results-{GATE_ID}"
KAFKA_CONSUME_TOPIC_HZ = f"hz-results-{GATE_ID}"
API_URL = os.getenv("API_URL", "http://localhost:8080/api/v1")
TIME_TOLERANCE_MINUTES = int(os.getenv("TIME_TOLERANCE_MINUTES", 30))
MAX_LEVENSHTEIN_DISTANCE = int(os.getenv("MAX_LEVENSHTEIN_DISTANCE", 2))
TIME_FRAME_HOURS = int(os.getenv("TIME_FRAME_HOURS", 1))

logger = logging.getLogger("DecisionEngine")

class DecisionStatus(Enum):
    ACCEPTED = "ACCEPTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"

class DecisionEngine:
    def __init__(self) -> None:
        self.running = True
        
        self.un_numbers = load_from_file("./src/un_numbers.txt", separator="|")
        self.kemler_codes = load_from_file("./src/kemler_codes.txt", separator="|")
        logger.info(f"Loaded {len(self.un_numbers)} UN numbers and {len(self.kemler_codes)} Kemler codes.")

        self.lp_buffer = {}  # {truck_id: lp_data}
        self.hz_buffer = {}  # {truck_id: hz_data}

        self.kafka_producer = KafkaProducerWrapper(KAFKA_BOOTSTRAP)
        self.kafka_consumer = KafkaConsumerWrapper(KAFKA_BOOTSTRAP, "decision-engine-group", [KAFKA_CONSUME_TOPIC_LP, KAFKA_CONSUME_TOPIC_HZ])
        
        self.plate_matcher = PlateMatcher()
        self.database_client = DatabaseClient(API_URL, GATE_ID)
            
        # --- Prometheus Metrics ---
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
        
        # Start Prometheus metrics server (Port 8001 as configured in prometheus.yml)
        # logger.info("Starting Prometheus metrics server on port 8001")
        # start_http_server(8001) - Started in init.py
        
        
    def loop(self):
        logger.info("Starting main loop …")

        try:
            while self.running:
                msg = self.kafka_consumer.consume_message(timeout=1.0)
                if msg is None:
                    continue

                topic, data, truck_id = self.kafka_consumer.parse_message(msg)
                if topic is None or data is None or truck_id is None:
                    continue

                self._store_in_buffer(topic, truck_id, data)
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
    
    
    def _make_decision(self, truck_id: str, lp_data: dict, hz_data: dict):
        """Makes a decision for the truck based on LP and HZ data."""
        logger.info(f"Both LP and HZ available for truck_id='{truck_id}'. Making decision…")
        
        start_time = time.time()
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        detection = self._extract_detection_data(lp_data, hz_data)
        logger.debug(f"Extracted data:\nLicense Plate: '{detection['license_plate']}'\nUN Number: '{detection['un_number']}'\nKemler Code: '{detection['kemler_code']}'")

        decision = ""
        reason = ""
        
        # Handle missing license plate
        if detection["license_plate"] == "N/A":
            decision = DecisionStatus.MANUAL_REVIEW.value
            reason = "license_plate_not_detected"
            logger.info(f"Decision: [{decision} - {reason}]")
            payload = self._build_decision_payload(timestamp, detection, lp_data, hz_data, decision, [], reason, None)
            self.kafka_producer.produce(KAFKA_PRODUCE_TOPIC, payload, headers={"truckId": truck_id})
            return
        
        # Query and evaluate appointments
        appointments = self.database_client.get_appointments()
        logger.debug(f"Appointments query result: {appointments}")
        
        # Handle API unavailability
        if self.database_client.is_api_unavailable(appointments.get("message", "")):
            decision = DecisionStatus.MANUAL_REVIEW.value
            reason = "api_unavailable"
            logger.info(f"Decision: [{decision} - {reason}]")
            payload = self._build_decision_payload(timestamp, detection, lp_data, hz_data, decision, [], reason, None)
            self.kafka_producer.produce(KAFKA_PRODUCE_TOPIC, payload, headers={"truckId": truck_id})
            return
        
        # Handle no appointments found
        if appointments.get("found") is False:
            decision = DecisionStatus.MANUAL_REVIEW.value
            reason = "empty_db_appointments"
            logger.info(f"Decision: [{decision} - {reason}]")
            payload = self._build_decision_payload(timestamp, detection, lp_data, hz_data, decision, [], reason, None)
            self.kafka_producer.produce(KAFKA_PRODUCE_TOPIC, payload, headers={"truckId": truck_id})
            return
        
        ocr_plate = detection["license_plate"]
        candidate_plates = [appt["license_plate"] for appt in appointments.get("candidates", [])]
        
        matched_plate = self.plate_matcher.match_plate(ocr_plate, candidate_plates)
        
        # Handle no matched plate
        if matched_plate is None:
            decision = DecisionStatus.MANUAL_REVIEW.value
            reason = "license_plate_not_found"
            logger.info(f"Decision: [{decision} - {reason}]")
            payload = self._build_decision_payload(timestamp, detection, lp_data, hz_data, decision, [], reason, None)
        
        # Handle matched plate
        else:
            decision = DecisionStatus.ACCEPTED.value
            reason = "license_plate_matched"
            logger.info(f"Decision: [{decision} - {reason}]")
            payload = self._build_decision_payload(timestamp, detection, lp_data, hz_data, decision, [], reason, None)
            
            # Update appointment status in the database
            matched_appointment = self._get_appointment_from_plate(matched_plate, appointments.get("candidates", [])) if matched_plate else None
            matched_appointment_id = int(matched_appointment.get("appointment_id")) # type: ignore
            self.database_client.update_appointment_status(matched_appointment_id, DecisionStatus.ACCEPTED.value)
            
        # Publish decision result
        self.kafka_producer.produce(KAFKA_PRODUCE_TOPIC, payload, headers={"truckId": truck_id})
        
        # Record metrics
        self._record_decision_metrics(decision, start_time)


    def _try_process_truck(self, truck_id: str):
        """Attempts to process a truck if both LP and HZ data are available."""
        
        if truck_id not in self.lp_buffer or truck_id not in self.hz_buffer:
            return
                
        lp_data = self.lp_buffer[truck_id]
        hz_data = self.hz_buffer[truck_id]
        
        self._make_decision(truck_id, lp_data, hz_data)
        
        del self.lp_buffer[truck_id]
        del self.hz_buffer[truck_id]
        
        logger.debug(f"Buffers cleaned for truck_id='{truck_id}'")


    def _extract_detection_data(self, lp_data: dict, hz_data: dict) -> dict:
        """Extracts and formats detection data from LP and HZ payloads."""
        
        license_plate = lp_data.get("licensePlate", "N/A")
        un_number = hz_data.get("un", "N/A")
        kemler_code = hz_data.get("kemler", "N/A")

        un_data = f"{un_number}: {self._get_un_description(un_number)}" if un_number and un_number != "N/A" else "No UN number detected"
        kemler_data = f"{kemler_code}: {self._get_kemler_description(kemler_code)}" if kemler_code and kemler_code != "N/A" else "No Kemler code detected"

        return {
            "license_plate": license_plate,
            "un_number": un_number,
            "kemler_code": kemler_code,
            "un_data": un_data,
            "kemler_data": kemler_data
        }

    

    def _store_in_buffer(self, topic: str, truck_id: str, data: dict):
        """Stores message data in the appropriate buffer."""
        
        if topic == KAFKA_CONSUME_TOPIC_LP:
            self.lp_buffer[truck_id] = data
            logger.debug(f"LP data stored for truck_id='{truck_id}': {data}")
        
        elif topic == KAFKA_CONSUME_TOPIC_HZ:
            self.hz_buffer[truck_id] = data
            logger.debug(f"HZ data stored for truck_id='{truck_id}': {data}")

    
    
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
    
    
            
    def _build_decision_payload(self, timestamp: str, detection: dict, lp_data: dict, hz_data: dict,
                                 decision: str, alerts: list, decision_reason: str | None, route: dict | None) -> dict:
        """Builds the decision payload for publishing."""
        return {
            "timestamp": timestamp,
            "licensePlate": detection["license_plate"],
            "UN": detection["un_data"],
            "kemler": detection["kemler_data"],
            "alerts": alerts,
            "lp_cropUrl": lp_data.get("cropUrl"),
            "hz_cropUrl": hz_data.get("cropUrl"),
            "route": route,
            "decision": decision,
            "decision_reason": decision_reason,
            "decision_source": "engine"
        }
    
    def _get_un_description(self, un_number: str) -> str | None:
        return self.un_numbers.get(str(un_number), "Unknown UN Number")
    
    def _get_kemler_description(self, kemler_code: str) -> str | None:
        return self.kemler_codes.get(str(kemler_code), "Unknown Kemler Code")
    
    # TODO: Change decision metrics to the correct ones (There is no denied access decision currently)
    def _record_decision_metrics(self, decision: str, start_time: float):
        """Records Prometheus metrics for the decision."""
        duration = time.time() - start_time
        self.decision_latency.observe(duration)
        self.decisions_processed.inc()

        if decision == "ACCEPTED":
            self.approved_access.inc()
        elif decision == "REJECTED":
            self.denied_access.inc()
    
    def _cleanup_resources(self):
        """Releases resources gracefully."""
        logger.info("Freeing resources…")
        self.kafka_consumer.close()
        self.kafka_producer.flush()
    

    
