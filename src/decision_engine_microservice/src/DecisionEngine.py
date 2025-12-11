import json
import logging
from confluent_kafka import Producer, Consumer, KafkaException # type: ignore
import os
import requests
import time
from datetime import datetime, timedelta


KAFKA_CONSUME_TOPIC_LP = "lp_result"
KAFKA_CONSUME_TOPIC_HZ = "hz_result"
KAFKA_PRODUCE_TOPIC = "decision_results"
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "10.255.32.143:9092")
GATE_ID = int(os.getenv("GATE_ID", 1))
API_URL = os.getenv("API_URL", "http://localhost:8080/api/v1")
TIME_TOLERANCE_MINUTES = int(os.getenv("TIME_TOLERANCE_MINUTES", 30))

logger = logging.getLogger("Decision")

class DecisionEngine:
    def __init__(self, kafka_bootstrap: str | None = None):
        self.running = True
        
        self.un_numbers = self._load_un_numbers()
        self.kemler_codes = self._load_kemler_codes()
        # Mock database
        self.database = {}

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


    def _loop(self):
        logger.info("[DecisionEngine] Starting main loop …")

        try:
            while self.running:
                msg = self.consumer.poll(1.0)

                if msg is None:
                    continue

                if msg.error():
                    logger.error(f"[DecisionEngine/Kafka] Consumer error: {msg.error()}")
                    continue

                topic = msg.topic()
                
                # Parse message payload
                try:
                    data = json.loads(msg.value())
                except json.JSONDecodeError:
                    logger.warning("[DecisionEngine] Invalid message (JSON). Ignored.")
                    continue

                # Extract truck_id from headers
                truck_id = None
                for k, v in (msg.headers() or []):
                    if k == "truck_id":
                        truck_id = v.decode("utf-8") if isinstance(v, bytes) else v
                        break

                if not truck_id:
                    logger.warning("[DecisionEngine] Message missing 'truck_id' header. Ignored.")
                    continue

                logger.info(f"[DecisionEngine] Received from '{topic}' for truck_id='{truck_id}'")

                # Store in appropriate buffer
                if topic == KAFKA_CONSUME_TOPIC_LP:
                    self.lp_buffer[truck_id] = data
                    logger.debug(f"[DecisionEngine] LP data stored for truck_id='{truck_id}': {data}")
                
                elif topic == KAFKA_CONSUME_TOPIC_HZ:
                    self.hz_buffer[truck_id] = data
                    logger.debug(f"[DecisionEngine] HZ data stored for truck_id='{truck_id}': {data}")

                # Check if we have both LP and HZ for this truck
                if truck_id in self.lp_buffer and truck_id in self.hz_buffer:
                    logger.info(f"[DecisionEngine] Both LP and HZ available for truck_id='{truck_id}'. Making decision…")
                    
                    lp_data = self.lp_buffer[truck_id]
                    hz_data = self.hz_buffer[truck_id]
                    
                    self._make_decision(truck_id, lp_data, hz_data)
                    
                    # Clean up buffers after processing
                    del self.lp_buffer[truck_id]
                    del self.hz_buffer[truck_id]

                    logger.debug(f"[DecisionEngine] Buffers cleaned for truck_id='{truck_id}'")

        except KeyboardInterrupt:
            logger.info("[DecisionEngine] Interrupted by user.")
        
        except KafkaException as e:
            logger.exception(f"[DecisionEngine/Kafka] Kafka error: {e}")
        except Exception as e:
            logger.exception(f"[DecisionEngine] Unexpected error: {e}")
        finally:
            logger.info("[DecisionEngine] Freeing resources…")
            try:
                self.producer.flush(5)
            except Exception:
                pass
            try:
                self.consumer.close()
            except Exception:
                pass


    def _query_arrivals(self, license_plate: str) -> dict:
        """Query Arrivals API to validate incoming vehicle."""
        url = f"{API_URL}/decisions/query-arrivals"
        payload = {
            "matricula": license_plate,
            "gate_id": GATE_ID
        }
        try:
            response = requests.post(url, json=payload, timeout=2)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"[DecisionEngine] API Error {response.status_code}: {response.text}")
                return {"found": False, "message": "API Error"}
            
        except Exception as e:
            logger.error(f"[DecisionEngine] API Request failed: {e}")
            return {"found": False, "message": str(e)}

    def _make_decision(self, truck_id: str, lp_data: dict, hz_data: dict):
        logger.info(f"[DecisionEngine] Making decision for truck_id='{truck_id}'")
        
        license_plate = lp_data.get("licensePlate", "UNKNOWN")
        un_number = hz_data.get("un_number")
        kemler_code = hz_data.get("kemler_code")
        
        # 1. Query Database
        arrivals_result = self._query_arrivals(license_plate)

        logger.info(f"[DecisionEngine] Arrivals query result: {arrivals_result}")
        
        decision = "MANUAL_REVIEW"
        alerts = []
        route = None
        
        # Check if API query was successful
        if not arrivals_result.get("found"):
            # If API failed or vehicle not found in system
            api_message = arrivals_result.get("message", "Unknown error")
            if "Connection refused" in api_message or "Max retries" in api_message:
                decision = "MANUAL_REVIEW"
                alerts.append(f"API unavailable - Manual review required")
                logger.warning(f"[DecisionEngine] API unavailable for truck_id='{truck_id}'. Sending to manual review.")
            else:
                decision = "REJECTED"
                alerts.append(f"Vehicle not registered in arrivals system")
                logger.warning(f"[DecisionEngine] Vehicle '{license_plate}' not found in arrivals. Rejecting.")
        
        if arrivals_result.get("found"):
            candidates = arrivals_result.get("candidates", [])
            # Pick first candidate (earliest scheduled)
            candidate = candidates[0] if candidates else None
            
            if candidate:
                route = {
                    "gate_id": candidate.get("id_gate_entrada"),
                    "cais_id": candidate.get("id_cais"),
                    "gps": candidate.get("cais", {}).get("localizacao_gps")
                }
                
                # 2. Time Window Validation
                hora_prevista_str = candidate.get("hora_prevista") # ISO format expected
                logger.info(f"[DecisionEngine] Hora prevista: {hora_prevista_str}")
                if hora_prevista_str:
                    try:
                        try:
                            scheduled_dt = datetime.fromisoformat(hora_prevista_str)
                        except ValueError:
                             # Fallback for Time only string
                             t = datetime.strptime(hora_prevista_str, "%H:%M:%S").time()
                             scheduled_dt = datetime.combine(datetime.now().date(), t)

                        current_dt = datetime.now()
                        tolerance = timedelta(minutes=TIME_TOLERANCE_MINUTES)
                        
                        if not (scheduled_dt - tolerance <= current_dt <= scheduled_dt + tolerance):
                            decision = "REJECTED"
                            diff = (current_dt - scheduled_dt).total_seconds() / 60
                            status_time = "Early" if diff < 0 else "Late"
                            alerts.append(f"Outside time window ({status_time} by {abs(int(diff))} mins). Scheduled: {hora_prevista_str}")
                    
                    except Exception as e:
                         logger.warning(f"[DecisionEngine] Error parsing time: {e}")
                         pass           
            else:
                decision = "REJECTED"
                alerts.append("No valid candidate details found.")
            
        # Validate confidence
        hz_confidence = hz_data.get("confidence", 0.0)
        lp_confidence = lp_data.get("confidence", 0.0)
        
        if lp_confidence < 0.7:
            decision = "MANUAL_REVIEW"
            alerts.append(f"License plate detection confidence too low ({lp_confidence:.2f})")    
        
        if hz_confidence < 0.7:
            decision = "MANUAL_REVIEW"
            alerts.append(f"Hazardous material detection confidence too low ({hz_confidence:.2f})")    

        # Prepare Decision Data
        returned_data = {
            "timestamp": int(time.time()),
            "licensePlate": license_plate,
            "UN": int(un_number) if un_number and un_number.isdigit() else None,
            "kemler": int(kemler_code) if kemler_code and kemler_code.isdigit() else None,
            "alerts": alerts,
            "lp_cropUrl": lp_data.get("crop_url"),
            "hz_cropUrl": hz_data.get("crop_url"),
            "route": route,
            "decision": decision
        }

        self._publish_decision(truck_id, returned_data)
    

    def _publish_decision(self, truck_id: str, decision_data: dict):
        """Publishes decision result to Kafka gate topic."""
        topic_name = f"decision-{GATE_ID}"
        
        logger.info(f"[DecisionEngine] Publishing to '{topic_name}' for truck_id='{truck_id}': {decision_data['decision']}")
        
        # Ensure json serializable
        payload = json.dumps(decision_data).encode("utf-8")

        self.producer.produce(
            topic=topic_name,
            key=truck_id.encode("utf-8"),
            value=payload,
            headers={"truck_id": truck_id}
        )
        self.producer.poll(0)
    
    def _get_un_description(self, un_number: str) -> str | None:
        return self.un_numbers.get(str(un_number), "Unknown UN Number")
    
    def _get_un_kemler_description(self, kemler_code: str) -> str | None:
        return self.kemler_codes.get(str(kemler_code), "Unknown Kemler Code")
    
    def stop(self):
        logger.info("[DecisionEngine] Stopping…")
        self.running = False
    
    def _load_un_numbers(self):
        dic = {}

        with open("./decision_engine_microservice/src/un_numbers.txt", "r") as f:
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

        with open("./decision_engine_microservice/src/kemler_codes.txt", "r") as f:
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
