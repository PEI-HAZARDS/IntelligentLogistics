import asyncio
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

# OpenTelemetry for distributed tracing
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource

from config import settings

# Routers (apenas os que são realmente usados)
from routers import (
    arrivals,
    manual_review,
    alerts,
    drivers,
    stream,
    realtime,   # WebSockets para decisões em tempo real
    workers,    # Operators and Managers
)

# Kafka consumer para decisões
from realtime.kafka_consumer import start_consumer
from realtime.kafka_producer import stop_producer


def create_app() -> FastAPI:
    """
    Factory para criar a aplicação FastAPI do API Gateway.
    """
    app = FastAPI(
        title="API Gateway - Intelligent Logistics",
        version="1.0.0",
    )

    # ----------------------
    # CORS
    # ----------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOW_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
    )

    # ----------------------
    # Routers HTTP
    # ----------------------
    app.include_router(arrivals.router, prefix=settings.API_PREFIX)
    app.include_router(manual_review.router, prefix=settings.API_PREFIX)
    app.include_router(alerts.router, prefix=settings.API_PREFIX)
    app.include_router(drivers.router, prefix=settings.API_PREFIX)
    app.include_router(stream.router, prefix=settings.API_PREFIX)
    app.include_router(workers.router, prefix=settings.API_PREFIX)

    # ----------------------
    # Router WebSocket
    # ----------------------
    app.include_router(realtime.router, prefix=settings.API_PREFIX)

    # ----------------------
    # Kafka consumer startup
    # ----------------------
    @app.on_event("startup")
    async def on_startup():
        loop = asyncio.get_event_loop()
        start_consumer(loop)

    @app.on_event("shutdown")
    async def on_shutdown():
        await stop_producer()

    # ----------------------
    # Healthcheck
    # ----------------------
    @app.get("/health", tags=["health"])
    def health():
        return {"status": "ok", "env": settings.ENV}

    return app


app = create_app()

# =============================================================================
# OpenTelemetry Tracing Setup
# =============================================================================
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://tempo:4317")

resource = Resource.create({"service.name": "api-gateway"})
trace.set_tracer_provider(TracerProvider(resource=resource))

otlp_exporter = OTLPSpanExporter(endpoint=OTEL_EXPORTER_OTLP_ENDPOINT, insecure=True)
span_processor = BatchSpanProcessor(otlp_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)

# Instrument FastAPI
FastAPIInstrumentor.instrument_app(app)

# Prometheus metrics at /metrics
Instrumentator().instrument(app).expose(app)
