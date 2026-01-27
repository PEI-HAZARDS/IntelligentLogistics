import json
import logging
from confluent_kafka import Producer, Consumer, KafkaError # type: ignore

logger = logging.getLogger("KafkaWrapper")

class KafkaProducerWrapper:
    def __init__(self, bootstrap_servers):
        self.producer = Producer({
            "bootstrap.servers": bootstrap_servers,
            "log_level": 1,
        })

    def _delivery_callback(self, err, msg):
        """Standard delivery callback."""
        if err is not None:
            logger.debug(f"Message delivery failed: {err}")
        else:
            logger.info(f"Message delivered to {msg.topic()} [{msg.partition()}]")

    def produce(self, topic, data, key=None, headers=None):
        """
        Encodes data as JSON and publishes it.
        """
        logger.info(f"Producing message to topic {topic}...")
        try:
            payload = json.dumps(data).encode("utf-8")
            self.producer.produce(
                topic=topic,
                key=key,
                value=payload,
                headers=headers,
                callback=self._delivery_callback
            )
            self.producer.poll(0) # Trigger callbacks immediately
        except Exception as e:
            logger.exception(f"Failed to publish to {topic}: {e}")

    def flush(self, timeout=10):
        self.producer.flush(timeout)


class KafkaConsumerWrapper:
    def __init__(self, bootstrap_servers, group_id, topics):
        self.consumer = Consumer({
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "latest",
            "enable.auto.commit": True,
        })
        self.consumer.subscribe(topics)

    def get_latest_message(self, timeout=1.0):
        """
        Consumes messages, skipping old ones to return only the latest.
        """
        msgs_buffer = []
        
        # Drain the queue
        while True:
            msg = self.consumer.poll(timeout=0.1)
            if msg is None:
                break
            if msg.error():
                logger.error(f"Consumer error: {msg.error()}")
                continue
            msgs_buffer.append(msg)
        
        # Return the last valid message
        if msgs_buffer:
            return msgs_buffer[-1]
            
        # If queue was empty, wait for one
        return self.consumer.poll(timeout=timeout)
    
    
    def parse_message(self, msg):
        """
        Parses a Kafka message and extracts data.
        Returns (topic, data, truck_id) or (None, None, None) on failure.
        """
        if msg is None:
            return None, None, None
            
        if msg.error():
            logger.error(f"Consumer error: {msg.error()}")
            return None, None, None
            
        try:
            data = json.loads(msg.value())
        except json.JSONDecodeError:
            logger.warning("Invalid message (JSON). Ignored.")
            return None, None, None
            
        truck_id = self._extract_truck_id_from_headers(msg.headers())
        if not truck_id:
            logger.warning("Message missing 'truck_id' header. Ignored.")
            return None, None, None
            
        return msg.topic(), data, truck_id

    def _extract_truck_id_from_headers(self, headers):
        """Extract truck_id from message headers. Accepts both 'truck_id' and 'truckId'."""
        if not headers:
            return None
        for key, value in headers:
            if key in ("truck_id", "truckId"):
                return value.decode("utf-8") if isinstance(value, bytes) else value
        return None

    def close(self):
        self.consumer.close()