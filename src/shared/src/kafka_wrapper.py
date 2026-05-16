import json
import logging
from typing import Any, Optional
from confluent_kafka import Producer, Consumer, KafkaError, KafkaException # type: ignore
from shared.src.kafka_protocol import deserialize_message, KafkaTopicFactory

logger = logging.getLogger("KafkaWrapper")

class KafkaProducerWrapper:
    def __init__(self, bootstrap_servers: str):
        if not bootstrap_servers:
            raise ValueError("bootstrap_servers must be a non-empty string")
        self.producer = Producer({
            "bootstrap.servers": bootstrap_servers,
            "log_level": 1,
        })
    
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


    def produce(self, topic: str, data: Any, key: Optional[str] = None, headers: Optional[dict] = None) -> None:
        """Encode data as JSON and publish to a topic.

        Raises:
            TypeError: If data is not JSON-serializable.
            KafkaException: If the message cannot be enqueued.
        """
        logger.debug(f"Producing to {topic}")
        try:
            payload = json.dumps(data).encode("utf-8")
            
        except (TypeError, ValueError) as e:
            safe_topic = topic.replace('\n', '').replace('\r', '')
            logger.exception("Failed to serialize data for topic '%s'", safe_topic)
            raise

        try:
            self.producer.produce(
                topic=topic,
                key=key,
                value=payload,
                headers=headers,
                callback=self._delivery_callback
            )
            self.producer.poll(0)  # Trigger callbacks immediately

        except KafkaException as e:
            safe_topic = topic.replace('\n', '').replace('\r', '')
            logger.exception("Publish failed to '%s'", safe_topic)
            raise

    def flush(self, timeout: int = 10) -> None:
        """Block until all queued messages are delivered or timeout expires."""
        self.producer.flush(timeout)

    def close(self, timeout: int = 10) -> None:
        """Flush pending messages and close the producer."""
        self.producer.flush(timeout)
    
    def _delivery_callback(self, err, msg) -> None:
        """Standard delivery callback."""
        if err is not None:
            logger.error(f"Message delivery failed: {err}")
        else:
            logger.info(f"Message delivered to {msg.topic()}.")

class KafkaConsumerWrapper:
    def __init__(self, bootstrap_servers: str, group_id: str, topics: list):
        if not bootstrap_servers:
            raise ValueError("bootstrap_servers must be a non-empty string")
        
        self.consumer = Consumer({
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "latest",
            "enable.auto.commit": False,  # Commit manually after processing
        })
        
        self.consumer.subscribe(topics)
    
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
    
    def consume_message(self, timeout: float = 1.0):
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
    
    def consume_typed_message(self, timeout: float = 1.0):
        """
        Consumes and deserializes a message into a Message object.
        Returns (topic, message_obj, truck_id) or (None, None, None) on timeout or parse failure.

        Raises:
            Exception: If deserialization of a valid message fails.
        """
        msg = self.consume_message(timeout)
        if msg is None:
            return None, None, None

        topic, data, truck_id = self.parse_message(msg)
        if data is None:
            return None, None, None

        try:
            message_obj = deserialize_message(data)
        except Exception as e:
            logger.exception("Failed to deserialize message from topic '%s'", topic)
            raise

        return topic, message_obj, truck_id

    def clear_stale_messages(self, max_messages: int = 1000) -> int:
        """
        Drains all pending messages from the queue.
        
        Call this when initializing an agent to discard messages that are 
        no longer actionable (e.g., old auction data, expired time-sensitive events).

        Args:
            max_messages: Maximum number of messages to drain before stopping.

        Returns the number of messages cleared.
        """
        cleared_count = 0
        
        logger.debug("Clearing stale messages...")
        
        while cleared_count < max_messages:
            msg = self.consumer.poll(timeout=0.0)
            if msg is None:
                break
            if msg.error():
                logger.warning(f"Error while clearing: {msg.error()}")
                continue
            cleared_count += 1
        
        if cleared_count > 0:
            logger.info(f"Cleared {cleared_count} stale messages")
            
        return cleared_count
    
    def parse_message(self, msg) -> tuple:
        """
        Parses a Kafka message and extracts data.
        Returns (topic, data, truck_id) or (None, None, None) on failure.
        """
        if msg is None:
            return None, None, None
            
        if msg.error():
            logger.warning(f"Received error message: {msg.error()}")
            return None, None, None
            
        try:
            data = json.loads(msg.value())
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in message from topic '%s', skipped", msg.topic())
            return None, None, None
            
        truck_id = self.extract_truck_id_from_headers(msg.headers())
        if not truck_id and KafkaTopicFactory.requires_truck_id(msg.topic()):
            logger.warning("Missing truck_id header, skipped")
            return None, None, None
            
        return msg.topic(), data, truck_id

    def extract_truck_id_from_headers(self, headers) -> Optional[str]:
        """Extract truck_id from message headers. Accepts both 'truck_id' and 'truckId'."""
        if not headers:
            return None
        for key, value in headers:
            if key in ("truck_id", "truckId"):
                return value.decode("utf-8") if isinstance(value, bytes) else value
        return None

    def close(self) -> None:
        """Close the consumer and release resources."""
        self.consumer.close()