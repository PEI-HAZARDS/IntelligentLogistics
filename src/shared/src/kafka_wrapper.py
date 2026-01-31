import json
import logging
from confluent_kafka import Producer, Consumer, KafkaError # type: ignore
from shared.src.kafka_protocol import deserialize_message

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
            logger.error(f"Message delivery failed: {err}")
        else:
            logger.info(f"Message delivered to {msg.topic()}.")

    def produce(self, topic, data, key=None, headers=None):
        """
        Encodes data as JSON and publishes it.
        """
        logger.debug(f"Producing to {topic}")
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
            logger.error(f"Publish failed to {topic}: {e}")

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
    
    def consume_message(self, timeout=1.0):
        """
        Consumes a single message from Kafka.
        Returns the next message in order, or None if timeout expires.
        """
        msg = self.consumer.poll(timeout=timeout)
        
        if msg is None:
            return None
            
        if msg.error():
            if msg.error().code() != KafkaError._PARTITION_EOF:
                logger.error(f"Consumer error: {msg.error()}")
            return None
        
        logger.debug(f"Consumed message from {msg.topic()}")
        return msg
    
    def consume_typed_message(self, timeout=1.0):
        """
        Consumes and deserializes a message into a Message object.
        Returns (topic, message_obj, truck_id) or (None, None, None).
        """
        msg = self.consume_message(timeout)
        topic, data, truck_id = self.parse_message(msg)
        
        if data is None:
            return None, None, None
        
        message_obj = deserialize_message(data)
        return topic, message_obj, truck_id

    def clear_stale_messages(self):
        """
        Drains all pending messages from the queue.
        
        Call this when initializing an agent to discard messages that are 
        no longer actionable (e.g., old auction data, expired time-sensitive events).
        
        Returns the number of messages cleared.
        """
        cleared_count = 0
        
        logger.debug("Clearing stale messages...")
        
        while True:
            msg = self.consumer.poll(timeout=0.1)
            if msg is None:
                break
            if msg.error():
                logger.warning(f"Error while clearing: {msg.error()}")
                continue
            cleared_count += 1
        
        if cleared_count > 0:
            logger.info(f"Cleared {cleared_count} stale messages")
            
        return cleared_count
    
    def parse_message(self, msg):
        """
        Parses a Kafka message and extracts data.
        Returns (topic, data, truck_id) or (None, None, None) on failure.
        """
        if msg is None:
            return None, None, None
            
        if msg.error():
            logger.debug(f"Consumer error: {msg.error()}")
            return None, None, None
            
        try:
            data = json.loads(msg.value())
        except json.JSONDecodeError:
            logger.debug("Invalid JSON message, skipped")
            return None, None, None
            
        truck_id = self.extract_truck_id_from_headers(msg.headers())
        if not truck_id:
            logger.warning("Missing truck_id header, skipped")
            return None, None, None
            
        return msg.topic(), data, truck_id

    def extract_truck_id_from_headers(self, headers):
        """Extract truck_id from message headers. Accepts both 'truck_id' and 'truckId'."""
        if not headers:
            return None
        for key, value in headers:
            if key in ("truck_id", "truckId"):
                return value.decode("utf-8") if isinstance(value, bytes) else value
        return None

    def close(self):
        self.consumer.close()