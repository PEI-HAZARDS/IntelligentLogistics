import json
import logging
import threading
import asyncio
from web_socket_manager import WebSocketManager
from shared.src.kafka_wrapper import KafkaConsumerWrapper, KafkaProducerWrapper
from shared.src.kafka_protocol import Message, deserialize_message, KafkaTopicFactory
from fastapi import FastAPI # type: ignore
import uvicorn # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
from prometheus_fastapi_instrumentator import Instrumentator # type: ignore
from pydantic_settings import BaseSettings # type: ignore
from pydantic import Field # type: ignore

# OpenTelemetry for distributed tracing
from opentelemetry import trace # type: ignore
from opentelemetry.sdk.trace import TracerProvider # type: ignore
from opentelemetry.sdk.trace.export import BatchSpanProcessor # type: ignore
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter # type: ignore
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor # type: ignore
from opentelemetry.sdk.resources import Resource # type: ignore

from routers import (
    arrivals,
    manual_review,
    alerts,
    drivers,
    stream,
    realtime,   # WebSockets para decisões em tempo real
    workers,    # Operators and Managers
    statistics, # Statistics proxy for manager dashboard
)

logger = logging.getLogger("APIGateway")


class APIGatewayConfig(BaseSettings):
    """Configuration for the API Gateway, loaded from environment variables."""
    kafka_bootstrap: str = Field(default="localhost:9092")
    gate_id: str = Field(default="1")
    gateway_port: int = Field(default=8000)
    data_module_url: str = Field(default="http://data-module:8000")
    stream_base_url: str = Field(default="http://nginx-rtmp:8080")
    api_prefix: str = Field(default="/api")
    env: str = Field(default="dev")
    cors_allow_origins: list[str] = Field(default=["*"])
    cors_allow_credentials: bool = Field(default=True)
    cors_allow_methods: list[str] = Field(default=["*"])
    cors_allow_headers: list[str] = Field(default=["*"])


class APIGateway:
    def __init__(
        self,
        config: APIGatewayConfig | None = None,
        kafka_producer: KafkaProducerWrapper | None = None,
        kafka_consumer: KafkaConsumerWrapper | None = None,
        WSManager: WebSocketManager | None = None,
    ) -> None:
        self.config = config or APIGatewayConfig()

        # Topic names via factory — single source of truth
        self.consume_topic = [KafkaTopicFactory.agent_decision(self.config.gate_id)]
        self.produce_topic = KafkaTopicFactory.operator_decision(self.config.gate_id)

        self.kafka_producer = kafka_producer or KafkaProducerWrapper(self.config.kafka_bootstrap)
        self.kafka_consumer = kafka_consumer or KafkaConsumerWrapper(
            self.config.kafka_bootstrap, "api-gateway-group", self.consume_topic
        )
        self.ws_manager = WSManager or WebSocketManager()
        self.app = self._create_app()
        self.running = False

    def _consumer_loop(self):
        """Consume from Kafka, process, and send via WebSockets"""
        logger.info(f"[Consumer thread] Listening on topics: {self.consume_topic}")
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
                    logger.warning(f"Could not deserialize message from topic '{topic}': {e}")
                    continue
                
                payload = typed_message.to_dict()
                payload["truck_id"] = truck_id  # ensure truck_id is always present
            
            
                # Forward the processed message to all receiver gateways
                # Must schedule on the main event loop (where WebSockets live)
                future = asyncio.run_coroutine_threadsafe(
                    self.ws_manager.broadcast_to_gate(self.config.gate_id, payload),
                    self._loop,
                )
                future.result(timeout=5)  # wait up to 5s for the broadcast
                
        except Exception as e:
            logger.error(f"Consumer loop error: {e}")
        finally:
            logger.info("[Consumer thread] Stopped")
    
    def _create_app(self) -> FastAPI:
        """
        Factory para criar a aplicação FastAPI do API Gateway.
        """
        app = FastAPI(
            title="API Gateway - Intelligent Logistics",
            version="1.0.0",
        )

        # ----------------------
        # Expose shared resources to routers via app.state
        # ----------------------
        app.state.kafka_producer = self.kafka_producer
        app.state.produce_topic = self.produce_topic
        app.state.ws_manager = self.ws_manager
        app.state.data_module_url = self.config.data_module_url
        app.state.stream_base_url = self.config.stream_base_url
        app.state.gate_id = self.config.gate_id

        # ----------------------
        # CORS
        # ----------------------
        app.add_middleware(
            CORSMiddleware,
            allow_origins=self.config.cors_allow_origins,
            allow_credentials=self.config.cors_allow_credentials,
            allow_methods=self.config.cors_allow_methods,
            allow_headers=self.config.cors_allow_headers,
        )

        # ----------------------
        # Routers HTTP
        # ----------------------
        app.include_router(arrivals.router, prefix=self.config.api_prefix)
        app.include_router(manual_review.router, prefix=self.config.api_prefix)
        app.include_router(alerts.router, prefix=self.config.api_prefix)
        app.include_router(drivers.router, prefix=self.config.api_prefix)
        app.include_router(stream.router, prefix=self.config.api_prefix)
        app.include_router(workers.router, prefix=self.config.api_prefix)
        app.include_router(statistics.router, prefix=self.config.api_prefix)

        # ----------------------
        # Router WebSocket
        # ----------------------
        app.include_router(realtime.router, prefix=self.config.api_prefix)

        # ----------------------
        # Healthcheck
        # ----------------------
        @app.get("/health", tags=["health"])
        def health():
            return {"status": "ok", "env": self.config.env}

        return app
    
    def start(self):
        """
        Start the gateway:
          1. Spawn the Kafka consumer loop in a daemon thread
          2. Run the FastAPI server on the main thread (blocking)
        """
        self.running = True
        logger.info(f"Starting api gateway on port {self.config.gateway_port}")

        # Capture the main event loop so the consumer thread can schedule coroutines on it
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        # Thread 1 – Kafka consumer (daemon: dies when main thread exits)
        self._consumer_thread = threading.Thread(
            target=self._consumer_loop,
            name=f"api-gateway-consumer",
            daemon=True,
        )
        self._consumer_thread.start()

        # Thread 2 (main) – FastAPI / uvicorn (uses the event loop above)
        try:
            config = uvicorn.Config(self.app, host="0.0.0.0", port=self.config.gateway_port, loop="asyncio")
            server = uvicorn.Server(config)
            self._loop.run_until_complete(server.serve())
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            self.stop()

    def stop(self):
        """Gracefully stop the gateway."""
        logger.info("Stopping gateway...")
        self.running = False
        
        if self._consumer_thread and self._consumer_thread.is_alive():
            self._consumer_thread.join(timeout=5)
        
        self.kafka_consumer.close()
        self.kafka_producer.flush()
        logger.info("Gateway stopped.")