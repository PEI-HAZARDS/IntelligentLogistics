import json
import logging
import os
import threading
import asyncio
from web_socket_manager import WebSocketManager
from shared.src.kafka_wrapper import KafkaConsumerWrapper, KafkaProducerWrapper
from shared.src.kafka_protocol import Message, deserialize_message
from fastapi import FastAPI # type: ignore
import uvicorn # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
from prometheus_fastapi_instrumentator import Instrumentator # type: ignore

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
)

logger = logging.getLogger("APIGateway")

class APIGateway:
    def __init__(self, kafka_producer: KafkaProducerWrapper | None, kafka_consumer: KafkaConsumerWrapper | None, WSManager: WebSocketManager | None) -> None:
        self._load_config()
        self.kafka_producer = kafka_producer or KafkaProducerWrapper(self.kafka_bootstrap)
        self.kafka_consumer = kafka_consumer or KafkaConsumerWrapper(self.kafka_bootstrap, "api-gateway-group", self.consume_topic)
        self.ws_manager = WSManager or WebSocketManager()
        self.app = self._create_app()
        self.running = False
    
    def _load_config(self):
        self.gate_ids = os.getenv("GATE_ID", "gate_1")
        self.gateway_port = int(os.getenv("GATEWAY_PORT", "8000"))
        self.kafka_bootstrap = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
        self.consume_topic = ["agent-decision-1"]  #TODO: remove hardcoded value
        self.produce_topic = "operator-decision-1"
        self.API_PREFIX: str = os.getenv("GW_API_PREFIX", "/api")

        # URL base do Data Module (Internal API)
        self.DATA_MODULE_URL: str = os.getenv("DATA_MODULE_URL", "http://data-module:8000")

        # URL base do servidor de streams (Nginx-RTMP com HLS)
        self.STREAM_BASE_URL: str = os.getenv("STREAM_BASE_URL", "http://nginx-rtmp:8080")

        # Kafka – para consumir decisões em tempo real
        self.KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")

        # Tópico REAL com os resultados das decisões
        self.KAFKA_DECISION_TOPIC: str = os.getenv("KAFKA_DECISION_TOPIC", "decision_results")

        # Consumer group do gateway
        self.KAFKA_CONSUMER_GROUP: str = os.getenv("KAFKA_CONSUMER_GROUP", "api-gateway-decisions")

        # Ambiente
        self.ENV: str = os.getenv("GW_ENV", "dev")

        # CORS
        self.CORS_ALLOW_ORIGINS: list[str] = json.loads(
            os.getenv("CORS_ALLOW_ORIGINS", '["*"]')
        )
        self.CORS_ALLOW_CREDENTIALS: bool = (
            os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() == "true"
        )
        self.CORS_ALLOW_METHODS: list[str] = json.loads(
            os.getenv("CORS_ALLOW_METHODS", '["*"]')
        )
        self.CORS_ALLOW_HEADERS: list[str] = json.loads(
            os.getenv("CORS_ALLOW_HEADERS", '["*"]')
        )
    
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
                    self.ws_manager.broadcast_to_gate(self.gate_ids, payload),
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
        app.state.data_module_url = self.DATA_MODULE_URL
        app.state.stream_base_url = self.STREAM_BASE_URL
        app.state.gate_id = self.gate_ids

        # ----------------------
        # CORS
        # ----------------------
        app.add_middleware(
            CORSMiddleware,
            allow_origins=self.CORS_ALLOW_ORIGINS,
            allow_credentials=self.CORS_ALLOW_CREDENTIALS,
            allow_methods=self.CORS_ALLOW_METHODS,
            allow_headers=self.CORS_ALLOW_HEADERS,
        )

        # ----------------------
        # Routers HTTP
        # ----------------------
        app.include_router(arrivals.router, prefix=self.API_PREFIX)
        app.include_router(manual_review.router, prefix=self.API_PREFIX)
        app.include_router(alerts.router, prefix=self.API_PREFIX)
        app.include_router(drivers.router, prefix=self.API_PREFIX)
        app.include_router(stream.router, prefix=self.API_PREFIX)
        app.include_router(workers.router, prefix=self.API_PREFIX)

        # ----------------------
        # Router WebSocket
        # ----------------------
        app.include_router(realtime.router, prefix=self.API_PREFIX)

        # ----------------------
        # Healthcheck
        # ----------------------
        @app.get("/health", tags=["health"])
        def health():
            return {"status": "ok", "env": self.ENV}

        return app
    
    def start(self):
        """
        Start the gateway:
          1. Spawn the Kafka consumer loop in a daemon thread
          2. Run the FastAPI server on the main thread (blocking)
        """
        self.running = True
        logger.info(f"Starting api gateway on port {self.gateway_port}")

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
            config = uvicorn.Config(self.app, host="0.0.0.0", port=self.gateway_port, loop="asyncio")
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