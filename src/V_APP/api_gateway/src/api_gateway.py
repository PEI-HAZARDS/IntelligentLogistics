import json
import logging
import threading
import asyncio
import httpx
from web_socket_manager import WebSocketManager
from shared.src.kafka_wrapper import KafkaConsumerWrapper, KafkaProducerWrapper
from shared.src.kafka_protocol import Message, deserialize_message, KafkaTopicFactory
from fastapi import FastAPI # type: ignore
import uvicorn # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
from prometheus_fastapi_instrumentator import Instrumentator # type: ignore
from pydantic_settings import BaseSettings  # type: ignore
from pydantic import Field, field_validator  # type: ignore

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
    realtime,   # WebSockets for real-time updates
    workers,    # Operators and Managers
    statistics, # Statistics proxy for manager dashboard
)

logger = logging.getLogger("APIGateway")


class APIGatewayConfig(BaseSettings):
    """Configuration for the API Gateway, loaded from environment variables."""
    kafka_bootstrap: str = Field(default="localhost:9092")
    gate_ids: str = Field(default='["1"]')            # Master list
    decision_gate_ids: str = Field(default='["1"]')   # Inbound/Entry gates
    infraction_gate_ids: str = Field(default='["1"]') # Highway/Approach gates
    gateway_port: int = Field(default=8000)
    data_module_url: str = Field(default="http://data-module:8000")
    stream_base_url: str = Field(default="http://mediamtx:8888")
    stream_webrtc_base_url: str = Field(default="http://mediamtx:8889")
    api_prefix: str = Field(default="/api")
    env: str = Field(default="dev")
    cors_allow_origins: list[str] = Field(default=["*"])
    cors_allow_credentials: bool = Field(default=True)
    cors_allow_methods: list[str] = Field(default=["*"])
    cors_allow_headers: list[str] = Field(default=["*"])
    
    @field_validator("gate_ids", "decision_gate_ids", "infraction_gate_ids", mode="before")
    @classmethod
    def _parse_gate_ids(cls, v: str) -> str:
        """Validate that the field is a valid JSON array string."""
        try:
            parsed = json.loads(v) if isinstance(v, str) else v
            if not isinstance(parsed, list) or len(parsed) == 0:
                raise ValueError("Gate ID fields must be non-empty JSON arrays")
        except json.JSONDecodeError:
            raise ValueError(f"Value is not valid JSON: {v}")
        return v

    def _to_list(self, json_str: str) -> list[str]:
        return [str(gid) for gid in json.loads(json_str)]

    @property
    def gate_id_list(self) -> list[str]:
        return self._to_list(self.gate_ids)

    @property
    def decision_gate_id_list(self) -> list[str]:
        return self._to_list(self.decision_gate_ids)

    @property
    def infraction_gate_id_list(self) -> list[str]:
        return self._to_list(self.infraction_gate_ids)


class APIGateway:
    def __init__(
        self,
        config: APIGatewayConfig | None = None,
        kafka_producer: KafkaProducerWrapper | None = None,
        kafka_consumer: KafkaConsumerWrapper | None = None,
        WSManager: WebSocketManager | None = None,
    ) -> None:
        self.config = config or APIGatewayConfig()
        
        self.consume_topics = []
        self.consume_topics.append(KafkaTopicFactory.scale_down())
        self.consume_topics.append(KafkaTopicFactory.scale_up())

        for infraction_gate_id in self.config.infraction_gate_id_list:
            logger.info(f"Subscribing to infraction decisions for gate {infraction_gate_id}")
            self.consume_topics.append(KafkaTopicFactory.infraction_decision(infraction_gate_id))
        
        for decision_gate_id in self.config.decision_gate_id_list:
            logger.info(f"Subscribing to operator decisions for gate {decision_gate_id}")
            self.consume_topics.append(KafkaTopicFactory.agent_decision(decision_gate_id))

        self.kafka_producer = kafka_producer or KafkaProducerWrapper(self.config.kafka_bootstrap)
        self.kafka_consumer = kafka_consumer or KafkaConsumerWrapper(
            self.config.kafka_bootstrap, "api-gateway-group", self.consume_topics
        )
        
        # Unified WebSocket manager for all events (Decisions, Scale, Infractions)
        self.ws_manager = WSManager or WebSocketManager()

        self.app = self._create_app()
        self.running = False

    def _consumer_loop(self):
        """Consume from Kafka, process, and send via a unified WebSocket channel."""
        logger.info(f"[Consumer thread] Listening on topics: {self.consume_topics}")
        self.kafka_consumer.clear_stale_messages()

        try:
            while self.running:
                msg = self.kafka_consumer.consume_message(timeout=1.0)
                if msg is None:
                    continue

                topic, data, truck_id = self.kafka_consumer.parse_message(msg)
                if data is None:
                    continue

                try:
                    typed_message = deserialize_message(data)
                except ValueError as e:
                    logger.warning(f"Could not deserialize message from topic '{topic}': {e}")
                    continue
                
                payload = typed_message.to_dict()
                if truck_id:
                    payload["truck_id"] = truck_id

                # 1. Filter out internal logic messages (SKIPPED decisions)
                if payload.get("decision") == "SKIPPED":
                    continue
                
                # 2. Determine the target gate for broadcasting:
                #    a) From the payload (scale_network messages carry gate_id)
                #    b) From the topic name (e.g. infraction-decision-2 → gate "2")
                target_gate = payload.get("gate_id")
                if not target_gate and topic:
                    # Extract gate ID from topic if it follows the pattern "something-gateid"
                    parts = topic.rsplit("-", 1)
                    if len(parts) == 2 and parts[1].strip():
                        target_gate = parts[1].strip()

                message_type = payload.get("message_type")

                # 3. Infractions: full payload to source gate (warning sign),
                #    lightweight status_changed to operational gates (operator UI refetch)
                if message_type == "infraction_decision":
                    if not target_gate:
                        logger.warning(
                            f"Could not determine target gate for infraction topic '{topic}', skipping broadcast"
                        )
                        continue

                    # Full payload to the source gate (e.g. gate 2 warning sign)
                    logger.info(
                        f"Broadcasting infraction decision to source gate {target_gate}"
                    )
                    self._broadcast_async(payload, str(target_gate))

                    # Notify operational gates with a lightweight status_changed
                    for op_gate in self.config.decision_gate_id_list:
                        if str(op_gate) != str(target_gate):
                            logger.info(
                                f"Sending status_changed to operational gate {op_gate}"
                            )
                            self._broadcast_async(
                                {"message_type": "status_changed", "reason": "infraction_decision"},
                                str(op_gate),
                            )

                    # Notify driver of infraction via driver-scoped WS
                    if payload.get("infraction") is True:
                        license_plate = payload.get("license_plate")
                        if license_plate and license_plate != "N/A":
                            self._notify_driver_of_infraction(license_plate, target_gate)
                    continue

                # 4. Other messages: broadcast only to their target gate
                if not target_gate:
                    logger.warning(f"Could not determine gate ID for topic '{topic}', skipping broadcast")
                    continue

                logger.info(f"Broadcasting {message_type} for gate {target_gate}")
                self._broadcast_async(payload, str(target_gate))

                # 5. ACCEPTED decisions: also notify the driver via driver-scoped WS
                if message_type == "decision_results" and payload.get("decision") == "ACCEPTED":
                    license_plate = payload.get("license_plate")
                    if license_plate and license_plate != "N/A":
                        self._notify_driver_of_acceptance(license_plate, target_gate)
                
        except Exception as e:
            logger.error(f"Consumer loop error: {e}")
        finally:
            logger.info("[Consumer thread] Stopped")

    def _broadcast_async(self, message: dict, target_gates: str | list[str]):
        """Helper to safely schedule a broadcast (single or multi-gate) from the consumer thread."""
        asyncio.run_coroutine_threadsafe(
            self.ws_manager.broadcast(target_gates, message),
            self._loop,
        )

    def _notify_driver_of_infraction(self, license_plate: str, gate_id: str):
        """Resolve driver_license from license plate and broadcast infraction_warning to the driver WS."""
        asyncio.run_coroutine_threadsafe(
            self._resolve_and_notify_driver_infraction(license_plate, gate_id),
            self._loop,
        )

    async def _resolve_and_notify_driver_infraction(self, license_plate: str, gate_id: str):
        """Look up the appointment by license plate, then broadcast infraction warning to the driver WS."""
        try:
            url = f"{self.config.data_module_url}/api/v1/arrivals/query/license-plate/{license_plate}"
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning(f"Driver lookup failed for plate {license_plate} (infraction): HTTP {resp.status_code}")
                return

            appointments = resp.json()
            if not appointments:
                logger.warning(f"No appointments found for plate {license_plate} (infraction)")
                return

            appointment = appointments[0]
            driver_license = appointment.get("driver_license")

            if not driver_license:
                logger.warning(f"No driver_license on appointment for plate {license_plate} (infraction)")
                return

            ws_payload = {
                "message_type": "infraction_warning",
                "license_plate": license_plate,
                "gate_id": gate_id,
            }
            await self.ws_manager.broadcast_to_driver(driver_license, ws_payload)
            logger.info(
                f"Broadcast infraction_warning for plate {license_plate} → driver {driver_license}"
            )
        except Exception as e:
            logger.error(f"Failed to notify driver of infraction for plate {license_plate}: {e}")

    def _notify_driver_of_acceptance(self, license_plate: str, gate_id: str):
        """Resolve driver_license from license plate and broadcast status_changed to the driver WS."""
        asyncio.run_coroutine_threadsafe(
            self._resolve_and_notify_driver(license_plate, gate_id),
            self._loop,
        )

    async def _resolve_and_notify_driver(self, license_plate: str, gate_id: str):
        """Look up the appointment by license plate, then broadcast to the driver WS."""
        try:
            url = f"{self.config.data_module_url}/api/v1/arrivals/query/license-plate/{license_plate}"
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning(f"Driver lookup failed for plate {license_plate}: HTTP {resp.status_code}")
                return

            appointments = resp.json()
            if not appointments:
                logger.warning(f"No appointments found for plate {license_plate}")
                return

            # Pick the first active appointment
            appointment = appointments[0]
            driver_license = appointment.get("driver_license")
            appointment_id = appointment.get("id")

            if not driver_license:
                logger.warning(f"No driver_license on appointment for plate {license_plate}")
                return

            ws_payload = {
                "message_type": "status_changed",
                "appointment_id": appointment_id,
                "new_status": "in_process",
            }
            await self.ws_manager.broadcast_to_driver(driver_license, ws_payload)
            logger.info(
                f"Broadcast status_changed (ACCEPTED) for plate {license_plate} → driver {driver_license}"
            )
        except Exception as e:
            logger.error(f"Failed to notify driver for plate {license_plate}: {e}")
    
    def _create_app(self) -> FastAPI:
        """Factory for the FastAPI application."""
        app = FastAPI(
            title="API Gateway - Intelligent Logistics",
            version="1.0.0",
        )

        # Unified state
        app.state.kafka_producer = self.kafka_producer
        app.state.ws_manager = self.ws_manager
        app.state.data_module_url = self.config.data_module_url
        app.state.stream_base_url = self.config.stream_base_url
        app.state.stream_webrtc_base_url = self.config.stream_webrtc_base_url

        app.add_middleware(
            CORSMiddleware,
            allow_origins=self.config.cors_allow_origins,
            allow_credentials=self.config.cors_allow_credentials,
            allow_methods=self.config.cors_allow_methods,
            allow_headers=self.config.cors_allow_headers,
        )

        # Routers
        app.include_router(arrivals.router, prefix=self.config.api_prefix)
        app.include_router(manual_review.router, prefix=self.config.api_prefix)
        app.include_router(alerts.router, prefix=self.config.api_prefix)
        app.include_router(drivers.router, prefix=self.config.api_prefix)
        app.include_router(stream.router, prefix=self.config.api_prefix)
        app.include_router(workers.router, prefix=self.config.api_prefix)
        app.include_router(statistics.router, prefix=self.config.api_prefix)
        app.include_router(realtime.router, prefix=self.config.api_prefix)

        @app.get("/health", tags=["health"])
        def health():
            return {"status": "ok", "env": self.config.env}
        
        Instrumentator().instrument(app).expose(app)
        return app
    
    def start(self):
        self.running = True
        logger.info(f"Starting api gateway on port {self.config.gateway_port}")

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        self._consumer_thread = threading.Thread(
            target=self._consumer_loop,
            name="api-gateway-consumer",
            daemon=True,
        )
        self._consumer_thread.start()

        try:
            config = uvicorn.Config(self.app, host="0.0.0.0", port=self.config.gateway_port, loop="asyncio")
            server = uvicorn.Server(config)
            self._loop.run_until_complete(server.serve())
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            self.stop()

    def stop(self):
        logger.info("Stopping gateway...")
        self.running = False
        if self._consumer_thread and self._consumer_thread.is_alive():
            self._consumer_thread.join(timeout=5)
        self.kafka_consumer.close()
        self.kafka_producer.flush()
        logger.info("Gateway stopped.")
