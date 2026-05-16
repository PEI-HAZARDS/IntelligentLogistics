from abc import ABC, abstractmethod
import logging
import logging.config
import os
import time
import threading
from typing import Optional
import httpx # type: ignore
import uvicorn # type: ignore
from fastapi import FastAPI, Request  # type: ignore
from fastapi.responses import JSONResponse # type: ignore
from prometheus_client import Counter, Histogram, Gauge
from prometheus_fastapi_instrumentator import Instrumentator # type: ignore
from shared.src.kafka_wrapper import KafkaConsumerWrapper, KafkaProducerWrapper
from shared.src.kafka_protocol import Message, deserialize_message
from pydantic_settings import BaseSettings # type: ignore
from pydantic import Field # type: ignore

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False

# Kafka consumer metrics shared across all gateway instances
_kafka_messages_consumed = Counter(
    "gateway_kafka_messages_consumed_total",
    "Total Kafka messages consumed by gateway",
    ["gateway", "topic", "status"],
)
_kafka_processing_seconds = Histogram(
    "gateway_kafka_processing_seconds",
    "Kafka message processing duration in seconds",
    ["gateway", "topic"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)
_kafka_consumer_lag = Gauge(
    "gateway_kafka_consumer_lag",
    "Estimated Kafka consumer lag (messages behind)",
    ["gateway", "topic"],
)


# Shared log format applied to every logger in the process,
# including uvicorn, uvicorn.access, uvicorn.error and fastapi.
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s – %(message)s"

LOG_CONFIG: dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": _LOG_FORMAT},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "stream": "ext://sys.stdout",
        },
    },
    # Root logger – catches everything not explicitly listed below
    "root": {
        "level": "INFO",
        "handlers": ["console"],
    },
    # Override uvicorn's own loggers so they inherit the same format (suppress to WARNING to avoid noise)
    "loggers": {
        "uvicorn": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "fastapi": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "httpx": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}


class _NullContext:
    """No-op context manager used when OTel tracing is disabled."""
    def __enter__(self):
        return self
    def __exit__(self, *_):
        pass


class BaseGatewayConfig(BaseSettings):
    # Kafka
    kafka_bootstrap: str = Field(...)

    # Gates configuration
    gate_ids: list[str] = Field(default=["1"])
    
    # Gateway specific configuration
    gateway_port: int = Field(default=8000)
    gateway_host: str = Field(default="0.0.0.0")
    receivers: list[str] = Field(default=[""])  # List of receiver gateway addresses (ip:port)

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
        config: BaseGatewayConfig,
        kafka_producer: Optional[KafkaProducerWrapper] = None,
        kafka_consumer: Optional[KafkaConsumerWrapper] = None,
    ) -> None:
        
        self.config = config
        self.topics_consume = self.get_topics_consume()
        self.gateway_name = self.get_gateway_name()
        self.receivers = self.get_receivers()

        self.kafka_producer = kafka_producer or KafkaProducerWrapper(self.config.kafka_bootstrap)
        self.kafka_consumer = kafka_consumer or KafkaConsumerWrapper(
            self.config.kafka_bootstrap,
            f"{self.gateway_name.lower()}-group",
            self.topics_consume,
        )
        
        self.running = False
        self._consumer_thread: Optional[threading.Thread] = None
        self._http_client = httpx.Client(timeout=10.0)

        # Apply the shared log config before creating any logger so every
        # component in this process (uvicorn, fastapi, kafka wrapper, …)
        # uses the same format and level.
        logging.config.dictConfig(LOG_CONFIG)
        self.logger = logging.getLogger(self.gateway_name)

        # OTel tracing — enabled only if OTEL_EXPORTER_OTLP_ENDPOINT is set
        self._tracer = None
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        if _OTEL_AVAILABLE and otlp_endpoint:
            try:
                provider = TracerProvider()
                provider.add_span_processor(
                    BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True))
                )
                trace.set_tracer_provider(provider)
                self._tracer = trace.get_tracer(self.gateway_name)
                self.logger.info(f"OTel tracing enabled → {otlp_endpoint}")
            except Exception as e:
                self.logger.warning(f"OTel setup failed, tracing disabled: {e}")

        # Build FastAPI app with routes bound to this instance
        self.app = self._create_app()

    # ──────────────────────────────────────────────
    #  Abstract methods (subclasses must implement)
    # ──────────────────────────────────────────────

    @abstractmethod
    def get_topics_consume(self) -> list[str]:
        """Kafka topics this gateway consumes FROM (local broker)."""
        pass

    @abstractmethod
    def get_topics_produce(self) -> dict[str, str]:
        """
        Routing map used when this gateway receives an HTTP message from another gateway.
        Keys are SOURCE topics (as sent in the X-Source-Topic header by the forwarding gateway).
        Values are DESTINATION topics on this gateway's local Kafka broker.
        This allows unambiguous routing when multiple gates share the same message_type.
        """
        pass

    @abstractmethod
    def get_gateway_name(self) -> str:
        """Unique name of this gateway (used for logging & consumer group)."""
        pass

    @abstractmethod
    def get_receivers(self) -> list[str]:
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
            consumer_alive = (
                self._consumer_thread is not None
                and self._consumer_thread.is_alive()
            )
            return {
                "status": "ok" if consumer_alive else "degraded",
                "consumer_alive": consumer_alive,
            }

        @app.post("/receive_message")
        async def receive_message(request: Request):
            """
            Called by OTHER gateways.
            Receives a message via HTTP POST and produces it to the LOCAL Kafka broker.
            """
            try:
                payload = await request.json()
            except Exception:
                return JSONResponse(status_code=400, content={"status": "error", "detail": "Invalid JSON body"})
            
            self.logger.info(f"Received message from external gateway: {payload.get('message_type', 'unknown')}")

            # Extract truck_id from HTTP header (mirrors Kafka header convention)
            truck_id = request.headers.get("X-Truck-ID")

            try:
                message = deserialize_message(payload)
            except ValueError as e:
                self.logger.warning(f"Invalid message in payload: {e}")
                return JSONResponse(
                    status_code=400,
                    content={"status": "error", "detail": str(e)},
                )

            # Build Kafka headers with truck_id if present
            headers = {"truck_id": truck_id} if truck_id else None

            # Route to the correct local topic.
            # Primary key: X-Source-Topic header (unambiguous even with multiple gates).
            # Fallback: message_type field (for backward compatibility).
            topic_map = self.get_topics_produce()
            source_topic = request.headers.get("X-Source-Topic")
            msg_type = payload.get("message_type", "")

            topic = topic_map.get(source_topic) if source_topic else None
            if topic is None:
                topic = topic_map.get(msg_type)

            if topic is None:
                self.logger.warning(
                    f"No produce topic mapped for source_topic='{source_topic}' "
                    f"or message_type='{msg_type}'"
                )
                return JSONResponse(
                    status_code=400,
                    content={"status": "error", "detail": f"No topic for source_topic='{source_topic}' or message_type='{msg_type}'"},
                )

            self.kafka_producer.produce(topic, message.to_dict(), headers=headers)
            self.kafka_producer.flush()
            
            return {"status": "ok", "message": f"Message produced to '{topic}'"}

        # Prometheus metrics at /metrics
        Instrumentator().instrument(app).expose(app)

        # OTel FastAPI tracing (no-op if OTel not initialized)
        if _OTEL_AVAILABLE and self._tracer:
            FastAPIInstrumentor.instrument_app(app)

        return app

    # ──────────────────────────────────────────────
    #  Forwarding to receiver gateways (HTTP POST)
    # ──────────────────────────────────────────────

    def _forward_to_recievers(self, message: Message, truck_id: Optional[str] = None, source_topic: Optional[str] = None) -> None: 
        """POST a message to every receiver gateway's /receive_message endpoint."""
        payload = message.to_dict()

        # Pass truck_id and the originating Kafka topic as HTTP headers.
        # X-Source-Topic lets the receiver resolve the correct destination topic
        # even when multiple gates produce messages with the same message_type.
        http_headers = {}
        if truck_id:
            http_headers["X-Truck-ID"] = truck_id
        if source_topic:
            http_headers["X-Source-Topic"] = source_topic

        for receiver in self.receivers:
            receiver_url = receiver if receiver.startswith("http") else f"http://{receiver}"
            endpoint = f"{receiver_url}/receive_message"
            try:
                response = self._http_client.post(endpoint, json=payload, headers=http_headers)
                response.raise_for_status()
                self.logger.info(f"Forwarded \"{message.MESSAGE_TYPE}\" message to {receiver}.")
            
            except httpx.HTTPError as e:
                self.logger.error(f"HTTP error forwarding to {receiver}: {e}")
            
            except Exception as e:
                self.logger.error(f"Error forwarding to {receiver}: {e}")

    # ──────────────────────────────────────────────
    #  Kafka consumer loop (runs in daemon thread)
    # ──────────────────────────────────────────────

    def _consumer_loop(self):
        """Consume from local Kafka, process, and forward to receivers."""
        self.logger.info(f"Listening on topics: {self.topics_consume}")
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
                    _kafka_messages_consumed.labels(
                        gateway=self.gateway_name, topic=topic, status="error"
                    ).inc()
                    continue

                # Process with metrics + optional OTel span
                start = time.perf_counter()
                span_ctx = (
                    self._tracer.start_as_current_span(
                        f"kafka.consume:{topic}",
                        attributes={"messaging.destination": topic, "truck_id": truck_id or ""},
                    )
                    if self._tracer
                    else _NullContext()
                )
                try:
                    with span_ctx:
                        processed = self.process_message(typed_message)
                        if processed is None:
                            self.logger.debug("Message dropped by process_message()")
                            _kafka_messages_consumed.labels(
                                gateway=self.gateway_name, topic=topic, status="dropped"
                            ).inc()
                            continue
                        self._forward_to_recievers(processed, truck_id=truck_id, source_topic=topic)
                    _kafka_messages_consumed.labels(
                        gateway=self.gateway_name, topic=topic, status="success"
                    ).inc()
                except Exception as e:
                    _kafka_messages_consumed.labels(
                        gateway=self.gateway_name, topic=topic, status="error"
                    ).inc()
                    raise
                finally:
                    _kafka_processing_seconds.labels(
                        gateway=self.gateway_name, topic=topic
                    ).observe(time.perf_counter() - start)

        except Exception as e:
            self.logger.exception(f"Consumer loop crashed: {e}")
            self.running = False
            raise  # let the daemon thread surface the error
        finally:
            self.logger.info("Consumer thread stopped")

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
        self.logger.info(f"Starting gateway '{self.gateway_name}' on port {self.config.gateway_port}")

        # Thread 1 – Kafka consumer (daemon: dies when main thread exits)
        self._consumer_thread = threading.Thread(
            target=self._consumer_loop,
            name=f"{self.gateway_name}-consumer",
            daemon=True,
        )
        self._consumer_thread.start()

        # Thread 2 (main) – FastAPI / uvicorn
        try:
            uvicorn.run(
                self.app,
                host=self.config.gateway_host,
                port=self.config.gateway_port,
                log_config=LOG_CONFIG,
            )
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
        self._http_client.close()
        self.kafka_producer.close()
        self.logger.info("Gateway stopped.")
    
    