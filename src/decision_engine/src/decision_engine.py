import json
import logging
from confluent_kafka import Producer, Consumer, KafkaException # type: ignore
import os
import requests # type: ignore
import time
from datetime import datetime, timedelta
import itertools
from prometheus_client import start_http_server, Counter, Histogram # type: ignore


KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "10.255.32.143:9092")
GATE_ID = os.getenv("GATE_ID", 1)
KAFKA_PRODUCE_TOPIC = f"decision-results-{GATE_ID}"
KAFKA_CONSUME_TOPIC_LP = f"lp-results-{GATE_ID}"
KAFKA_CONSUME_TOPIC_HZ = f"hz-results-{GATE_ID}"
API_URL = os.getenv("API_URL", "http://localhost:8080/api/v1")
TIME_TOLERANCE_MINUTES = int(os.getenv("TIME_TOLERANCE_MINUTES", 30))
MAX_LEVENSHTEIN_DISTANCE = int(os.getenv("MAX_LEVENSHTEIN_DISTANCE", 2))
TIME_FRAME_HOURS = int(os.getenv("TIME_FRAME_HOURS", 1))

logger = logging.getLogger("Decision")

class DecisionEngine:
    def __init__(self, kafka_bootstrap: str | None = None):
        self.running = True
        
        self.un_numbers = self._load_un_numbers()
        self.kemler_codes = self._load_kemler_codes()

        self.lp_buffer = {}  # {truck_id: lp_data}
        self.hz_buffer = {}  # {truck_id: hz_data}

        bootstrap = kafka_bootstrap or KAFKA_BOOTSTRAP
        logger.info(f"[Decision/Kafka] Connecting to kafka via '{bootstrap}' …")
        
        self.consumer = Consumer({ # type: ignore
            "bootstrap.servers": bootstrap,
            "group.id": "decision-engine-group",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,        
            "max.poll.interval.ms": 300000,
        })

        self.consumer.subscribe([KAFKA_CONSUME_TOPIC_LP, KAFKA_CONSUME_TOPIC_HZ])
        
        self.producer = Producer({
            "bootstrap.servers": bootstrap,
            "log_level": 1
            })
            
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
        # logger.info("[DecisionEngine] Starting Prometheus metrics server on port 8001")
        # start_http_server(8001) - Started in init.py

        self.confusion_matrix = {
            # --- NUMBERS ---
            '0': ['O', 'D', 'Q', 'U'],
            '1': ['I', 'L', 'T', 'J'],
            '2': ['Z', '7'],
            '3': ['B', 'E', '8'],
            '4': ['A'],
            '5': ['S'],
            '6': ['G', 'b'],
            '7': ['T', 'Y', 'Z'],
            '8': ['B', 'S'],
            '9': ['g', 'q', 'P'],

            # --- LETTERS ---
            'A': ['4'],
            'B': ['8', '3'],
            'C': ['G', '0'],
            'D': ['0', 'O', 'Q'],
            'E': ['3', 'F'],
            'F': ['P', 'E'],
            'G': ['6', 'C'],
            'H': ['A', 'N', 'M'],
            'I': ['1', 'L', 'T', 'J'],
            'J': ['1', 'I'],
            'K': ['X', 'R'],
            'L': ['1', 'I'],
            'M': ['W', 'N'],
            'N': ['M', 'H'],
            'O': ['0', 'D', 'Q', 'U'],
            'P': ['R', 'F', '9'],
            'Q': ['0', 'O', 'D', '9'],
            'R': ['P', 'K'],
            'S': ['5', '8'],
            'T': ['7', '1', 'I', 'Y'],
            'U': ['0', 'O', 'V'],
            'V': ['U', 'Y'],
            'W': ['M'],
            'X': ['K', 'Y'],
            'Y': ['V', 'T', '7'],
            'Z': ['2', '7']
        }

    def _extract_truck_id_from_headers(self, headers) -> str | None:
        """Extracts truck_id from Kafka message headers."""
        for k, v in (headers or []):
            if k == "truckId":
                return v.decode("utf-8") if isinstance(v, bytes) else v
        return None

    def _parse_message(self, msg) -> tuple:
        """
        Parses a Kafka message and extracts data.
        Returns (topic, data, truck_id) or (None, None, None) on failure.
        """
        if msg.error():
            logger.error(f"[DecisionEngine/Kafka] Consumer error: {msg.error()}")
            return None, None, None

        try:
            data = json.loads(msg.value())
        except json.JSONDecodeError:
            logger.warning("[DecisionEngine] Invalid message (JSON). Ignored.")
            return None, None, None

        truck_id = self._extract_truck_id_from_headers(msg.headers())
        if not truck_id:
            logger.warning("[DecisionEngine] Message missing 'truck_id' header. Ignored.")
            return None, None, None

        return msg.topic(), data, truck_id

    def _store_in_buffer(self, topic: str, truck_id: str, data: dict):
        """Stores message data in the appropriate buffer."""
        if topic == KAFKA_CONSUME_TOPIC_LP:
            self.lp_buffer[truck_id] = data
            logger.debug(f"[DecisionEngine] LP data stored for truck_id='{truck_id}': {data}")
        elif topic == KAFKA_CONSUME_TOPIC_HZ:
            self.hz_buffer[truck_id] = data
            logger.debug(f"[DecisionEngine] HZ data stored for truck_id='{truck_id}': {data}")

    def _try_process_truck(self, truck_id: str):
        """Attempts to process a truck if both LP and HZ data are available."""
        if truck_id not in self.lp_buffer or truck_id not in self.hz_buffer:
            return

        logger.info(f"[DecisionEngine] Both LP and HZ available for truck_id='{truck_id}'. Making decision…")
        
        lp_data = self.lp_buffer[truck_id]
        hz_data = self.hz_buffer[truck_id]
        
        self._make_decision(truck_id, lp_data, hz_data)
        
        del self.lp_buffer[truck_id]
        del self.hz_buffer[truck_id]
        logger.debug(f"[DecisionEngine] Buffers cleaned for truck_id='{truck_id}'")

    def _cleanup_resources(self):
        """Releases Kafka resources gracefully."""
        logger.info("[DecisionEngine] Freeing resources…")
        try:
            self.producer.flush(5)
        except Exception:
            pass
        try:
            self.consumer.close()
        except Exception:
            pass

    def _loop(self):
        logger.info("[DecisionEngine] Starting main loop …")

        try:
            while self.running:
                msg = self.consumer.poll(1.0)
                if msg is None:
                    continue

                topic, data, truck_id = self._parse_message(msg)
                if topic is None:
                    continue

                logger.info(f"[DecisionEngine] Received from '{topic}' for truck_id='{truck_id}'")
                self._store_in_buffer(topic, truck_id, data)
                self._try_process_truck(truck_id)

        except KeyboardInterrupt:
            logger.info("[DecisionEngine] Interrupted by user.")
        except KafkaException as e:
            logger.exception(f"[DecisionEngine/Kafka] Kafka error: {e}")
        except Exception as e:
            logger.exception(f"[DecisionEngine] Unexpected error: {e}")
        finally:
            self._cleanup_resources()


    def _query_appointments_in_timeframe(self) -> dict:
        """Query Appointments API to get all candidates in time frame."""
        url = f"{API_URL}/decisions/query-appointments"
        payload = {
            "time_frame": TIME_FRAME_HOURS,
            "gate_id": GATE_ID
        }
        try:
            response = requests.post(url, json=payload, timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"[DecisionEngine] API Error {response.status_code}: {response.text}")
                return {"found": False, "candidates": [], "message": "API Error"}
            
        except Exception as e:
            logger.error(f"[DecisionEngine] API Request failed: {e}")
            return {"found": False, "candidates": [], "message": str(e)}
    
    def _find_matching_appointment(self, ocr_plate: str, candidates: list) -> tuple:
        """
        Find the best matching appointment using Levenshtein distance.
        Returns (matched_candidate, distance) or (None, -1) if no match found.
        """
        if not ocr_plate or not candidates:
            return None, -1
        
        # Normalize OCR plate (uppercase, remove spaces/dashes for comparison)
        normalized_ocr = ocr_plate.upper().replace(" ", "").replace("-", "")
        
        best_match = None
        best_distance = float('inf')
        
        for candidate in candidates:
            db_plate = candidate.get("license_plate", "")
            if not db_plate:
                continue
            
            # Normalize DB plate
            normalized_db = db_plate.upper().replace(" ", "").replace("-", "")
            
            distance = self._levenshtein_distance(normalized_ocr, normalized_db)
            
            logger.debug(f"[DecisionEngine] Comparing '{normalized_ocr}' with '{normalized_db}' -> distance: {distance}")
            
            if distance < best_distance:
                best_distance = distance
                best_match = candidate
        
        # Only return match if within threshold
        if best_distance <= MAX_LEVENSHTEIN_DISTANCE:
            logger.info(f"[DecisionEngine] Found match: '{best_match.get('license_plate')}' with distance {best_distance}") # type: ignore
            return best_match, best_distance
        
        logger.info(f"[DecisionEngine] No match found within threshold {MAX_LEVENSHTEIN_DISTANCE} (best was {best_distance})")
        return None, best_distance
        
    def _generate_plate_candidates(self, ocr_text: str):
        """
        Generates all likely license plate variations based on visual similarities.
        Use this to "fuzzy match" against a database.
        """
        # 1. Build a list of possibilities for each character position
        possibilities = []
        for char in ocr_text:
            # Start with the character itself
            options = [char]
            # Add its visual twins if they exist
            if char in self.confusion_matrix:
                options.extend(self.confusion_matrix[char])
            possibilities.append(set(options)) # Use set to remove duplicates

        # 2. Generate Cartesian product of all possibilities
        candidates = [''.join(p) for p in itertools.product(*possibilities)]
        
        return candidates
    
    def _levenshtein_distance(self, s1, s2):
        # Ensure s1 is the shorter string for memory efficiency
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        # Use a single row to save memory (we only need the previous row)
        previous_row = range(len(s2) + 1)
        
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                # Calculate costs
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                
                # append the minimum cost to the current row
                current_row.append(min(insertions, deletions, substitutions))
                
            previous_row = current_row
        
        return previous_row[-1]

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

    def _build_decision_payload(self, timestamp: str, detection: dict, lp_data: dict, hz_data: dict,
                                 decision: str, alerts: list, route: dict | None) -> dict:
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
            "decision_source": "engine"
        }

    def _handle_missing_license_plate(self, truck_id: str, timestamp: str, detection: dict,
                                       lp_data: dict, hz_data: dict):
        """Handles the case when license plate is not detected."""
        alerts = ["License plate not detected"]
        logger.warning(f"[DecisionEngine] Incomplete data for truck_id='{truck_id}'. Sending to manual review.")

        returned_data = {
            "timestamp": timestamp,
            "licensePlate": detection["license_plate"],
            "UN": detection["un_data"],
            "kemler": detection["kemler_data"],
            "alerts": alerts,
            "lp_cropUrl": lp_data.get("cropUrl"),
            "hz_cropUrl": hz_data.get("cropUrl"),
            "route": None,
            "decision": "MANUAL_REVIEW",
            "decision_source": "engine"
        }
        self._publish_decision(truck_id, returned_data)

    def _is_api_unavailable(self, api_message: str) -> bool:
        """Checks if the API is unavailable based on the response message."""
        return "Connection refused" in api_message or "Max retries" in api_message

    def _evaluate_appointment_match(self, license_plate: str, appointments_result: dict) -> tuple:
        """
        Evaluates appointment matching and returns decision details.
        Returns (decision, alerts, route, matched_appointment).
        """
        alerts = []
        route = None
        
        api_message = appointments_result.get("message", "")
        if self._is_api_unavailable(api_message):
            alerts.append("API unavailable - Manual review required")
            return "MANUAL_REVIEW", alerts, route, None

        candidates = appointments_result.get("candidates", [])
        matched_appointment, distance = self._find_matching_appointment(license_plate, candidates)

        if matched_appointment is None:
            decision = "REJECTED"
            if distance >= 0:
                alerts.append(f"License plate '{license_plate}' not matched (closest distance: {distance}, threshold: {MAX_LEVENSHTEIN_DISTANCE})")
            else:
                alerts.append(f"No appointments found in time frame for gate {GATE_ID}")
            logger.warning(f"[DecisionEngine] No matching license plate for '{license_plate}'. Rejecting.")
            return decision, alerts, route, None

        # Match found
        route = {
            "gate_id": matched_appointment.get("gate_in_id"),
            "terminal_id": matched_appointment.get("terminal_id"),
            "appointment_id": matched_appointment.get("appointment_id")
        }

        if distance > 0:
            alerts.append(f"Fuzzy match: detected '{license_plate}' matched to '{matched_appointment.get('license_plate')}' (distance: {distance})")

        logger.info(f"[DecisionEngine] Matched appointment ID: {matched_appointment.get('appointment_id')}, decision: ACCEPTED")
        return "ACCEPTED", alerts, route, matched_appointment

    def _record_decision_metrics(self, decision: str, start_time: float):
        """Records Prometheus metrics for the decision."""
        duration = time.time() - start_time
        self.decision_latency.observe(duration)
        self.decisions_processed.inc()

        if decision == "ACCEPTED":
            self.approved_access.inc()
        elif decision == "REJECTED":
            self.denied_access.inc()

    def _make_decision(self, truck_id: str, lp_data: dict, hz_data: dict):
        logger.info(f"[DecisionEngine] Making decision for truck_id='{truck_id}'")
        
        start_time = time.time()
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        detection = self._extract_detection_data(lp_data, hz_data)
        logger.info(f"[DecisionEngine] Extracted data - License Plate: '{detection['license_plate']}', UN Number: '{detection['un_number']}', Kemler Code: '{detection['kemler_code']}'")

        # Handle missing license plate
        if detection["license_plate"] == "N/A":
            self._handle_missing_license_plate(truck_id, timestamp, detection, lp_data, hz_data)
            return

        # Query and evaluate appointments
        appointments_result = self._query_appointments_in_timeframe()
        logger.info(f"[DecisionEngine] Appointments query result: {appointments_result}")

        decision, alerts, route, matched_appointment = self._evaluate_appointment_match(
            detection["license_plate"], appointments_result
        )

        # Update appointment status if needed
        if matched_appointment and decision in ["ACCEPTED", "REJECTED"]:
            appointment_id = matched_appointment.get("appointment_id")
            if appointment_id:
                self._update_appointment_status(appointment_id, decision)

        # Build and publish decision
        returned_data = self._build_decision_payload(
            timestamp, detection, lp_data, hz_data, decision, alerts, route
        )
        self._publish_decision(truck_id, returned_data)

        # Record metrics
        self._record_decision_metrics(decision, start_time)
    
    def _update_appointment_status(self, appointment_id: int, decision: str):
        """Updates the appointment status via the Data Module API."""
        # Map decision to status (same as manual review)
        if decision == "ACCEPTED":
            new_status = "in_process"  # Truck at gate, being processed
        elif decision == "REJECTED":
            new_status = "canceled"
        else:
            return  # Don't update for MANUAL_REVIEW
        
        url = f"{API_URL}/arrivals/{appointment_id}/status"
        payload = {
            "status": new_status,
            "notes": f"[Decision Engine] Auto-{decision.lower()}"
        }
        
        try:
            response = requests.patch(url, json=payload, timeout=5)
            if response.status_code == 200:
                logger.info(f"[DecisionEngine] Updated appointment {appointment_id} status to '{new_status}'")
            else:
                logger.warning(f"[DecisionEngine] Failed to update appointment status: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"[DecisionEngine] Error updating appointment status: {e}")

    def _publish_decision(self, truck_id: str, decision_data: dict):
        """Publishes decision result to Kafka gate topic."""
        
        logger.info(f"[DecisionEngine] Publishing to '{KAFKA_PRODUCE_TOPIC}' for truck_id='{truck_id}': {decision_data['decision']}")
        
        # Ensure json serializable
        payload = json.dumps(decision_data).encode("utf-8")

        self.producer.produce(
            topic=KAFKA_PRODUCE_TOPIC,
            key=truck_id.encode("utf-8"),
            value=payload,
            headers={"truck_id": truck_id}
        )
        self.producer.poll(0)
    
    def _get_un_description(self, un_number: str) -> str | None:
        return self.un_numbers.get(str(un_number), "Unknown UN Number")
    
    def _get_kemler_description(self, kemler_code: str) -> str | None:
        return self.kemler_codes.get(str(kemler_code), "Unknown Kemler Code")
    
    def stop(self):
        logger.info("[DecisionEngine] Stopping…")
        self.running = False
    
    def _load_un_numbers(self):
        dic = {}

        with open("./src/un_numbers.txt", "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue  # skip empty lines

                parts = line.split("|")
                if len(parts) != 2:
                    continue

                un, descr = parts[0].strip(), parts[1].strip()
                dic[un] = descr

        logger.info(f"[DecisionEngine] Loaded {len(dic)} UN numbers")
        return dic
    
    def _load_kemler_codes(self):
        dic = {}

        with open("./src/kemler_codes.txt", "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue  # skip empty lines

                parts = line.split("|")
                if len(parts) != 2:
                    continue

                un, descr = parts[0].strip(), parts[1].strip()
                dic[un] = descr

        logger.info(f"[DecisionEngine] Loaded {len(dic)} Kemler codes")
        return dic
