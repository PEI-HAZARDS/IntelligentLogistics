import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings

# Routers (apenas os que são realmente usados)
from .routers import (
    arrivals,
    manual_review,
    alerts,
    drivers,
    stream,
    realtime,   # WebSockets para decisões em tempo real
)

# Kafka consumer para decisões
from .realtime.kafka_consumer import start_consumer


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

    # ----------------------
    # Healthcheck
    # ----------------------
    @app.get("/health", tags=["health"])
    def health():
        return {"status": "ok", "env": settings.ENV}

    return app


app = create_app()
