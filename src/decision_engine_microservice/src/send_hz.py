from confluent_kafka import Producer, Consumer, KafkaException # type: ignore
import logging
import os
import json
import time
import uuid

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "10.255.32.143:9092")
TOPIC_PRODUCE = "hz_result"
logger = logging.getLogger("TEST_HZ")

producer = Producer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            # "enable.idempotence": True, "acks": "all"  # liga em produção se precisares de garantias fortes
        })

def publish_hz_results(timestamp, truck_id, un_number, kemler_code, conf):
        """Publica evento 'hz_result' com propagação do correlationId."""

        # Payload com o conteudo da mensagem
        payload = {
            "timestamp": timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "un_number": un_number,
            "kemler_code": kemler_code,
            "confidence": float(conf if conf is not None else 0.0)
        }
        
        logger.info(f"[TEST] Publishing '{TOPIC_PRODUCE}' (truckId={truck_id}, un={un_number}, kemler={kemler_code}) …")

        # Publica o topico de deteção de matrícula
        producer.produce(
            topic=TOPIC_PRODUCE,
            key=None,
            value=json.dumps(payload).encode("utf-8"),
            headers={"truck_id": truck_id or str(uuid.uuid4())}
        )
        producer.poll(0)


def main():
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    truck_id = "truck123"
    un_number = "1203"
    kemler_code = "33"
    conf = 0.95
    publish_hz_results(timestamp, truck_id, un_number, kemler_code, conf)
    
    # Wait for all messages to be delivered
    producer.flush()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()