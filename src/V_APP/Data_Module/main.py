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


async def update_delayed_appointments():
    """
    Background task:
    1. Updates in_transit appointments to delayed if past scheduled time + 15 min.
    2. At midnight (day change), marks ALL remaining in_transit from the previous
       day as delayed so they are never lost across day boundaries.

    Uses UoW + Outbox so that status changes propagate to MongoDB/Redis
    read models via the outbox worker (Guardrails 2, 3).
    """
    from application.use_cases.appointment_commands import cmd_update_status
    from infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork

    def _uow_factory():
        return SqlAlchemyUnitOfWork(SessionLocal)

    current_day = datetime.now(timezone.utc).date()

    while True:
        try:
            db = SessionLocal()
            try:
                now = datetime.now(timezone.utc)
                today = now.date()

                # --- Day boundary: mark all previous-day in_transit as delayed ---
                if today != current_day:
                    yesterday_start = datetime.combine(current_day, datetime.min.time().replace(tzinfo=timezone.utc))
                    yesterday_end = datetime.combine(current_day, datetime.max.time().replace(tzinfo=timezone.utc))

                    stale = db.query(Appointment).filter(
                        Appointment.status == 'in_transit',
                        Appointment.scheduled_start_time != None,
                        Appointment.scheduled_start_time.between(yesterday_start, yesterday_end)
                    ).all()

                    for appt in stale:
                        cmd_update_status(_uow_factory, appt.id, new_status="delayed")

                    if stale:
                        logger.info(f"Midnight rollover: marked {len(stale)} in_transit from {current_day} as delayed (via Outbox)")

                    current_day = today

                # --- Normal: 15 min tolerance for today's appointments ---
                cutoff = now - timedelta(minutes=15)

                overdue = db.query(Appointment).filter(
                    Appointment.status == 'in_transit',
                    Appointment.scheduled_start_time != None,
                    Appointment.scheduled_start_time < cutoff
                ).all()

                for appt in overdue:
                    cmd_update_status(_uow_factory, appt.id, new_status="delayed")

                if overdue:
                    logger.info(f"Scheduler: Updated {len(overdue)} appointments to 'delayed' (via Outbox)")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Scheduler error updating delayed appointments: {e}")

        # Run every 5 minutes
        await asyncio.sleep(300)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    global _scheduler_task
    
    # ===== STARTUP =====
    # 1) Postgres: create tables
    try:
        Base.metadata.create_all(bind=engine)
        _ready["postgres"] = True
        logger.info("Postgres: schemas verified / created.")
    except Exception as e:
        _ready["postgres"] = False
        logger.exception("Postgres: failed to verify/create schemas: %s", e)

    # 2) MongoDB: ping
    try:
        mongo_client.admin.command("ping")
        _ready["mongo"] = True
        logger.info("MongoDB: ping OK.")
    except Exception as e:
        _ready["mongo"] = False
        logger.exception("MongoDB: ping failed: %s", e)

    # 3) Redis: ping
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

    # 4) Start background scheduler for delayed appointments
    if _ready["postgres"]:
        _scheduler_task = asyncio.create_task(update_delayed_appointments())
        logger.info("Background scheduler started for delayed appointments.")
    
    # 5) Start Kafka decision consumer
    try:
        app.state.decision_consumer = KafkaDecisionConsumer()
        await app.state.decision_consumer.start()
        logger.info("Kafka decision consumer started.")
    except Exception as e:
        logger.exception("Failed to start Kafka decision consumer: %s", e)

    yield  # Application runs

    # ===== SHUTDOWN =====
    # Stop Kafka consumer
    try:
        consumer = getattr(app.state, "decision_consumer", None)
        if consumer:
            await consumer.stop()
        logger.info("Kafka decision consumer stopped.")
    except asyncio.CancelledError:
        logger.info("Kafka decision consumer cancelled during shutdown.")
    except Exception:
        logger.exception("Error stopping Kafka decision consumer.")
    
    # Stop scheduler
    if _scheduler_task:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            logger.info("Background scheduler stopped.")

    # Close clients
    try:
        mongo_client.close()
        logger.info("MongoDB client closed.")
    except Exception:
        logger.exception("Error closing MongoDB client.")

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

resource = Resource.create({"service.name": "data-module"})
trace.set_tracer_provider(TracerProvider(resource=resource))

otlp_exporter = OTLPSpanExporter(endpoint=OTEL_EXPORTER_OTLP_ENDPOINT, insecure=True)
span_processor = BatchSpanProcessor(otlp_exporter)
trace.get_tracer_provider().add_span_processor(span_processor)

# Instrument FastAPI
FastAPIInstrumentor.instrument_app(app)

# Prometheus metrics at /metrics
Instrumentator().instrument(app).expose(app)
