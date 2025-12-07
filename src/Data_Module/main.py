from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from routes.arrivals import router as arrivals_router
from routes.events import router as events_router
from routes.decisions import router as decisions_router
from Data_Module.routes.driver import router as drivers_router
from routes.alerts import router as alerts_router

# DB / infra imports used for startup checks
from db.postgres import engine
from models.sql_models import Base
from db.mongo import client as mongo_client  # MongoClient instance
from db.redis import redis_client
from config import settings

app = FastAPI(title="Data Module API", version="1.0.0")

# CORS para frontend (ajustar origins em produção)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(arrivals_router, prefix="/api/v1")
app.include_router(events_router, prefix="/api/v1")
app.include_router(decisions_router, prefix="/api/v1")
app.include_router(drivers_router, prefix="/api/v1")
app.include_router(alerts_router, prefix="/api/v1")

# readiness flags set at startup
_ready = {"postgres": False, "mongo": False, "redis": False}

logger = logging.getLogger("data_module")
logging.basicConfig(level=logging.INFO)


@app.on_event("startup")
def on_startup():
    """
    Startup tasks:
    - ensure SQLAlchemy models are created (create_all)
    - check connectivity to MongoDB and Redis
    - set readiness flags (used by /health)
    """
    # 1) Postgres: create tables (safe to call multiple times)
    try:
        Base.metadata.create_all(bind=engine)
        _ready["postgres"] = True
        logger.info("Postgres: schemas verified / created.")
    except Exception as e:
        _ready["postgres"] = False
        logger.exception("Postgres: failed to verify/create schemas: %s", e)

    # 2) MongoDB: ping
    try:
        # client is a pymongo.MongoClient
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


@app.on_event("shutdown")
def on_shutdown():
    """
    Graceful shutdown: close external clients where applicable.
    """
    try:
        # Close Mongo client
        try:
            mongo_client.close()
            logger.info("MongoDB client closed.")
        except Exception:
            logger.exception("Error closing MongoDB client.")

        # Close redis client connection pool (redis-py)
        try:
            # close() exists on Redis client in recent versions
            if hasattr(redis_client, "close"):
                redis_client.close()
            logger.info("Redis client closed.")
        except Exception:
            logger.exception("Error closing Redis client.")
    except Exception:
        logger.exception("Error during shutdown cleanup.")


@app.get("/health")
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
