from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from prometheus_fastapi_instrumentator import Instrumentator
import logging
import asyncio
import os
from datetime import datetime, timezone, timedelta

# OpenTelemetry for distributed tracing
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource

from routes.arrivals import router as arrivals_router
from routes.events import router as events_router
from routes.decisions import router as decisions_router
from routes.driver import router as drivers_router
from routes.alerts import router as alerts_router
from routes.worker import router as workers_router
from routes.notifications import router as notifications_router

# Kafka decision consumer
from infrastructure.messaging.kafka_decision_consumer import KafkaDecisionConsumer

# DB / infra imports used for startup checks
from infrastructure.persistence.postgres import engine, SessionLocal
from infrastructure.persistence.sql_models import Base, Appointment
from infrastructure.persistence.mongo import mongo_client  # MongoClient instance
from infrastructure.persistence.redis import redis_client
from config import settings

# readiness flags set at startup
_ready = {"postgres": False, "mongo": False, "redis": False}
_scheduler_task = None

logger = logging.getLogger("data_module")
logging.basicConfig(level=logging.INFO)



async def _startup_services(app: FastAPI) -> asyncio.Task | None:
    """Initialise all infrastructure services and return the scheduler task."""
    try:
        Base.metadata.create_all(bind=engine)
        _ready["postgres"] = True
        logger.info("Postgres: schemas verified / created.")
    except Exception as e:
        _ready["postgres"] = False
        logger.exception("Postgres: failed to verify/create schemas: %s", e)

    try:
        mongo_client.admin.command("ping")
        _ready["mongo"] = True
        logger.info("MongoDB: ping OK.")
    except Exception as e:
        _ready["mongo"] = False
        logger.exception("MongoDB: ping failed: %s", e)

    try:
        pong = redis_client.ping()
        if pong:
            _ready["redis"] = True
            logger.info("Redis: ping OK.")
        else:
            _ready["redis"] = False
            logger.warning("Redis: ping returned falsy value.")
    except Exception as e:
        _ready["redis"] = False
        logger.exception("Redis: ping failed: %s", e)

    scheduler: asyncio.Task | None = None

    try:
        app.state.decision_consumer = KafkaDecisionConsumer()
        await app.state.decision_consumer.start()
        logger.info("Kafka decision consumer started.")
    except Exception as e:
        logger.exception("Failed to start Kafka decision consumer: %s", e)

    return scheduler


async def _shutdown_services(app: FastAPI, scheduler_task: asyncio.Task | None) -> None:
    """Stop Kafka consumer, background scheduler, and close clients."""
    try:
        consumer = getattr(app.state, "decision_consumer", None)
        if consumer:
            await consumer.stop()
        logger.info("Kafka decision consumer stopped.")
    except asyncio.CancelledError:
        logger.info("Kafka decision consumer cancelled during shutdown.")
        raise
    except Exception:
        logger.exception("Error stopping Kafka decision consumer.")

    if scheduler_task:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            logger.info("Background scheduler stopped.")
            raise

    try:
        mongo_client.close()
        logger.info("MongoDB client closed.")
    except Exception:
        logger.exception("Error closing MongoDB client.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    global _scheduler_task
    _scheduler_task = await _startup_services(app)
    yield
    await _shutdown_services(app, _scheduler_task)

    try:
        if hasattr(redis_client, "close"):
            redis_client.close()
        logger.info("Redis client closed.")
    except Exception:
        logger.exception("Error closing Redis client.")


app = FastAPI(
    title="Data Module API",
    version="1.0.0",
    description="Intelligent Logistics - Data Module (Source of Truth)",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir routers - os prefixos já estão definidos nos routers
# arrivals: /arrivals
# decisions: /decisions  
# drivers: /drivers
# alerts: /alerts
# workers: /workers
# events: /events (legacy)
# statistics: /statistics (NEW - Phase 2)
from routes.statistics import router as statistics_router

app.include_router(arrivals_router, prefix="/api/v1")
app.include_router(events_router, prefix="/api/v1")
app.include_router(decisions_router, prefix="/api/v1")
app.include_router(drivers_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")
app.include_router(workers_router, prefix="/api/v1")
app.include_router(statistics_router, prefix="/api/v1")  # Phase 2
app.include_router(notifications_router, prefix="/api/v1")  # Phase 2


@app.get("/api/v1/health")
def health():
    """
    Health endpoint:
    - returns overall status and per-component readiness flags
    """
    overall = "ok" if all(_ready.values()) else "degraded"
    return {
        "status": overall,
        "components": _ready,
        "decision_engine_url": settings.decision_engine_url,
    }


# =============================================================================
# OpenTelemetry Tracing Setup
# =============================================================================
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://tempo:4317")
_otel_enabled = os.getenv("OTEL_ENABLED", "true").lower() != "false"

resource = Resource.create({"service.name": "data-module"})
trace.set_tracer_provider(TracerProvider(resource=resource))

if _otel_enabled:
    otlp_exporter = OTLPSpanExporter(endpoint=OTEL_EXPORTER_OTLP_ENDPOINT, insecure=True)
    span_processor = BatchSpanProcessor(
        otlp_exporter,
        export_timeout_millis=5_000,   # fail fast — default is 30 s
        schedule_delay_millis=3_000,
    )
    trace.get_tracer_provider().add_span_processor(span_processor)
    # One ERROR per failed batch is enough; suppress the per-retry WARNING flood
    logging.getLogger("opentelemetry.exporter.otlp.proto.grpc.exporter").setLevel(logging.ERROR)
    logger.info("OTel tracing enabled — endpoint=%s", OTEL_EXPORTER_OTLP_ENDPOINT)
else:
    logger.info("OTel tracing disabled (OTEL_ENABLED=false)")

# Instrument FastAPI
FastAPIInstrumentor.instrument_app(app)

# Prometheus metrics at /metrics
Instrumentator().instrument(app).expose(app)
