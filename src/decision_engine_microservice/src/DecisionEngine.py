import json
import logging
import os
from confluent_kafka import Producer # type: ignore


KAFKA_CONSUME_TOPIC_LP = "lp_results"
KAFKA_CONSUME_TOPIC_HZ = "hz_results"
KAFKA_PRODUCE_TOPIC = "decision_results"
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "10.255.32.143:9092")

logger = logging.getLogger("AgentA")

class DecisionEngine:
    def __init__(self, kafka_bootstrap: str | None = None):
        self.running = True
        
        self.un_numbers = self._load_un_numbers()
        self.kemler_codes = self._load_kemler_codes()
        # Mock database
        self.database = {}

        self.lp_buffer = {}
        self.hz_buffer = {}

        bootstrap = kafka_bootstrap or KAFKA_BOOTSTRAP
        logger.info(f"[AgentA/Kafka] Connecting to kafka via '{bootstrap}' …")
        
        self.consumer = Consumer({ # type: ignore
            "bootstrap.servers": bootstrap,
            "group.id": "agentB-group",
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

        while self.running:
            msg = self.consumer.poll(1.0)

            if msg is None:
                continue

            if msg.error():
                logger.error(f"[DecisionEngine/Kafka] Consumer error: {msg.error()}")
                continue

            topic = msg.topic()
            try:
                data = json.loads(msg.value())

            except json.JSONDecodeError:
                logger.warning("[DecisonEngine] Invalid message (JSON). Ignored.")
                continue

        return "Decision made based on data"
    

    def _publish_decision(self, max_conf: float, num_boxes: int):
        # Placeholder for publishing decision logic
        pass
    
    def _get_un_description(self, un_number: str) -> str | None:
        return self.un_numbers.get(un_number, "Unknown UN Number")
    
    def _get_un_kemler_description(self, kemler_code: str) -> str | None:
        return self.kemler_codes.get(kemler_code, "Unknown Kemler Code")
    
    def stop(self):
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
                    logger.warning(f"[DecisionEngine] Invalid line format: {line}")
                    continue

                un, descr = parts[0].strip(), parts[1].strip()
                dic[un] = descr
                logger.info(f"[DecisionEngine] Loaded UN number: {un} - {descr}")

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
                    logger.warning(f"[DecisionEngine] Invalid line format: {line}")
                    continue

                un, descr = parts[0].strip(), parts[1].strip()
                dic[un] = descr
                logger.info(f"[DecisionEngine] Loaded kemler code: {un} - {descr}")

        return dic
