import json
import logging
from confluent_kafka import Producer, Consumer, KafkaException # type: ignore
import os


KAFKA_CONSUME_TOPIC_LP = "lp_result"
KAFKA_CONSUME_TOPIC_HZ = "hz_result"
KAFKA_PRODUCE_TOPIC = "decision_results"
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "10.255.32.143:9092")

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
                    
                    # TODO: Make decision based on lp_data and hz_data
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


    def _make_decision(self, truck_id: str, lp_data: dict, hz_data: dict):
        logger.info(f"[DecisionEngine] Making decision for truck_id='{truck_id}'")
        returned_data = {
            "licensePlate": lp_data.get("licensePlate"),
            "lp_confidence": lp_data.get("confidence"),
            "un_number": hz_data.get("un_number"),
            "un_description": self._get_un_description(hz_data.get("un_number", "")),
            "kemler_code": hz_data.get("kemler_code"),
            "kemler_description": self._get_un_kemler_description(hz_data.get("kemler_code", "")),
            "hz_confidence": hz_data.get("confidence"),
        }

        self._publish_decision(truck_id, returned_data)
    

    def _publish_decision(self, truck_id: str, decision_data: dict):
        """Publishes decision result to Kafka."""
        payload = {
            **decision_data
        }
        
        logger.info(f"[DecisionEngine] Publishing decision for truck_id='{truck_id}'")
        
        self.producer.produce(
            topic=KAFKA_PRODUCE_TOPIC,
            key=truck_id.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8"),
            headers={"truck_id": truck_id}
        )
        self.producer.poll(0)
    
    def _get_un_description(self, un_number: str) -> str | None:
        return self.un_numbers.get(un_number, "Unknown UN Number")
    
    def _get_un_kemler_description(self, kemler_code: str) -> str | None:
        return self.kemler_codes.get(kemler_code, "Unknown Kemler Code")
    
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
