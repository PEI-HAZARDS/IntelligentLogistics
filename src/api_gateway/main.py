from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings

# Routers 
from .routers import (
    arrivals,
    decisions,
    manual_review,
    alerts,
    drivers,
    events,
    auth,
    stream,
)


def create_app() -> FastAPI:
    """
    Factory para criar a aplicação FastAPI do API Gateway.
    """
    app = FastAPI(
        title="API Gateway - Intelligent Logistics",
        version="1.0.0",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOW_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
    )

    # Include routers
    # Cada router já terá o seu prefixo interno (ex: /arrivals),
    # aqui aplicamos apenas o prefixo global /api.
    app.include_router(arrivals.router, prefix=settings.API_PREFIX)
    app.include_router(decisions.router, prefix=settings.API_PREFIX)
    app.include_router(manual_review.router, prefix=settings.API_PREFIX)
    app.include_router(alerts.router, prefix=settings.API_PREFIX)
    app.include_router(drivers.router, prefix=settings.API_PREFIX)
    app.include_router(events.router, prefix=settings.API_PREFIX)

    # Routers mais "especiais"
    app.include_router(auth.router, prefix=settings.API_PREFIX)
    app.include_router(stream.router, prefix=settings.API_PREFIX)

    @app.get("/health", tags=["health"])
    def health():
        """
        Health-check simples do API Gateway.
        """
        return {"status": "ok", "env": settings.ENV}

    return app


app = create_app()
