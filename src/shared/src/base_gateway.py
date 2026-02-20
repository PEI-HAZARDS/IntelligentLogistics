from abc import ABC, abstractmethod
import logging
import os
import threading
from typing import Optional
import httpx  # type: ignore
import uvicorn  # type: ignore
from fastapi import FastAPI, Request  # type: ignore
from prometheus_fastapi_instrumentator import Instrumentator  # type: ignore
from shared.src.kafka_wrapper import KafkaConsumerWrapper, KafkaProducerWrapper
from shared.src.kafka_protocol import Message, deserialize_message


class BaseGateway(ABC):
    """
    Base class for inter-app gateways.

    A gateway bridges two or more applications by:
      1. Consuming messages from the LOCAL Kafka broker
      2. Forwarding (POST) those messages to RECEIVER gateways (the other(s) app)
      3. Receiving messages (POST) from other gateways and producing them to the LOCAL Kafka broker

    Architecture (two threads):
      - Main thread:   FastAPI/uvicorn server  (handles /receive_message, /health)
      - Daemon thread: Kafka consumer loop      (consumes → processes → forwards via HTTP)
    """

    def __init__(
        self,
        kafka_producer: Optional[KafkaProducerWrapper] = None,
        kafka_consumer: Optional[KafkaConsumerWrapper] = None,
    ) -> None:
        self._load_config()

        self.kafka_producer = kafka_producer or KafkaProducerWrapper(self.kafka_bootstrap)
        self.kafka_consumer = kafka_consumer or KafkaConsumerWrapper(
            self.kafka_bootstrap,
            f"{self.gateway_name.lower()}-group",
            self.topics_consume,
        )
        self.running = False
        self._consumer_thread: Optional[threading.Thread] = None

        self.logger = logging.getLogger(self.gateway_name)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        # Build FastAPI app with routes bound to this instance
        self.app = self._create_app()

    def _load_config(self):
        self.gate_id = os.getenv("GATE_ID", "gate_1")
        self.gateway_port = int(os.getenv("GATEWAY_PORT", "8000"))
        self.kafka_bootstrap = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
        self.topics_consume = self.get_topics_consume()
        self.gateway_name = self.get_gateway_name()
        self.recievers = self.get_recievers()

    # ──────────────────────────────────────────────
    #  Abstract methods (subclasses must implement)
    # ──────────────────────────────────────────────

    @abstractmethod
    def get_topics_consume(self) -> list[str]:
        """Kafka topics this gateway consumes FROM (local broker)."""
        pass

    @abstractmethod
    def get_topics_produce(self) -> dict[str, str]:
        """Kafka topics this gateway produces TO when it receives a message from another gateway."""
        pass

    @abstractmethod
    def get_gateway_name(self) -> str:
        """Unique name of this gateway (used for logging & consumer group)."""
        pass

    @abstractmethod
    def get_recievers(self) -> list[str]:
        """List of receiver gateway addresses (ip:port) to forward messages to."""
        pass

    @abstractmethod
    def process_message(self, message: Message) -> Optional[Message]:
        """
        Pre-process a message before forwarding / producing.
        Return the (possibly transformed) message, or None to drop it.
        """
        pass

    # ──────────────────────────────────────────────
    #  FastAPI App & Endpoints
    # ──────────────────────────────────────────────

    def _create_app(self) -> FastAPI:
        """Create the FastAPI app with routes bound to this gateway instance."""
        app = FastAPI(title=self.gateway_name)

        @app.get("/health")
        def health_check():
            return {"status": "ok"}

        @app.post("/receive_message")
        async def receive_message(request: Request):
            """
            Called by OTHER gateways.
            Receives a message via HTTP POST and produces it to the LOCAL Kafka broker.
            """
            payload = await request.json()
            self.logger.info(f"Received message from external gateway: {payload.get('message_type', 'unknown')}")

            # Extract truck_id from HTTP header (mirrors Kafka header convention)
            truck_id = request.headers.get("X-Truck-ID")

            try:
                message = deserialize_message(payload)
            except ValueError as e:
                self.logger.warning(f"Invalid message in payload: {e}")
                return {"status": "error", "detail": str(e)}

            # Build Kafka headers with truck_id if present
            headers = {"truck_id": truck_id} if truck_id else None

            # Route to the correct topic based on message_type
            topic_map = self.get_topics_produce()
            msg_type = payload.get("message_type", "")
            topic = topic_map.get(msg_type)

            if topic is None:
                self.logger.warning(f"No produce topic mapped for message_type '{msg_type}'")
                return {"status": "error", "detail": f"No topic for message_type '{msg_type}'"}

            try:
                self.kafka_producer.produce(topic, message.to_dict(), headers=headers)
                self.logger.info(f"Produced '{msg_type}' to local topic '{topic}'")
            except Exception as e:
                self.logger.error(f"Failed to produce to '{topic}': {e}")
                return {"status": "error", "detail": str(e)}

            self.kafka_producer.flush()
            return {"status": "ok", "message": f"Message produced to '{topic}'"}

        # Prometheus metrics at /metrics
        Instrumentator().instrument(app).expose(app)

        return app

    # ──────────────────────────────────────────────
    #  Forwarding to receiver gateways (HTTP POST)
    # ──────────────────────────────────────────────

    def _forward_to_recievers(self, message: Message, truck_id: str = None) -> None: # type: ignore
        """POST a message to every receiver gateway's /receive_message endpoint."""
        payload = message.to_dict()

        # Pass truck_id as an HTTP header
        http_headers = {}
        if truck_id:
            http_headers["X-Truck-ID"] = truck_id

        for receiver in self.recievers:
            receiver_url = receiver if receiver.startswith("http") else f"http://{receiver}"
            endpoint = f"{receiver_url}/receive_message"
            try:
                with httpx.Client(timeout=10.0) as client:
                    response = client.post(endpoint, json=payload, headers=http_headers)
                    response.raise_for_status()
                    self.logger.info(f"Forwarded message to {receiver} ✔")
            except httpx.HTTPError as e:
                self.logger.error(f"HTTP error forwarding to {receiver}: {e}")
            except Exception as e:
                self.logger.error(f"Error forwarding to {receiver}: {e}")

    # ──────────────────────────────────────────────
    #  Kafka consumer loop (runs in daemon thread)
    # ──────────────────────────────────────────────

    def _consumer_loop(self):
        """Consume from local Kafka, process, and forward to receivers."""
        self.logger.info(f"[Consumer thread] Listening on topics: {self.get_topics_consume()}")
        self.kafka_consumer.clear_stale_messages()

        try:
            while self.running:
                msg = self.kafka_consumer.consume_message(timeout=1.0)
                if msg is None:
                    continue

                # Parse the raw Kafka message
                topic, data, truck_id = self.kafka_consumer.parse_message(msg)
                if data is None:
                    continue

                # Deserialize into a typed Message
                try:
                    typed_message = deserialize_message(data)
                except ValueError as e:
                    self.logger.warning(f"Could not deserialize message from topic '{topic}': {e}")
                    continue

                # Let the subclass pre-process / transform the message
                processed = self.process_message(typed_message)
                if processed is None:
                    self.logger.debug("Message dropped by process_message()")
                    continue

                # Forward the processed message to all receiver gateways
                self._forward_to_recievers(processed, truck_id=truck_id) # type: ignore

        except Exception as e:
            self.logger.error(f"Consumer loop error: {e}")
        finally:
            self.logger.info("[Consumer thread] Stopped")

    # ──────────────────────────────────────────────
    #  Lifecycle: start / stop
    # ──────────────────────────────────────────────

    def start(self):
        """
        Start the gateway:
          1. Spawn the Kafka consumer loop in a daemon thread
          2. Run the FastAPI server on the main thread (blocking)
        """
        self.running = True
        self.logger.info(f"Starting gateway '{self.gateway_name}' on port {self.gateway_port}")

        # Thread 1 – Kafka consumer (daemon: dies when main thread exits)
        self._consumer_thread = threading.Thread(
            target=self._consumer_loop,
            name=f"{self.gateway_name}-consumer",
            daemon=True,
        )
        self._consumer_thread.start()

        # Thread 2 (main) – FastAPI / uvicorn
        try:
            uvicorn.run(self.app, host="0.0.0.0", port=self.gateway_port)
        except KeyboardInterrupt:
            self.logger.info("Interrupted by user")
        finally:
            self.stop()

    def stop(self):
        """Gracefully stop the gateway."""
        self.logger.info("Stopping gateway...")
        self.running = False
        
        if self._consumer_thread and self._consumer_thread.is_alive():
            self._consumer_thread.join(timeout=5)
        
        self.kafka_consumer.close()
        self.kafka_producer.flush()
        self.logger.info("Gateway stopped.")
    
    