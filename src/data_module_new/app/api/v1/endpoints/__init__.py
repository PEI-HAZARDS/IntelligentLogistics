from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.trucks import router as trucks_router
from app.api.v1.endpoints.drivers import router as drivers_router
from app.api.v1.endpoints.appointments import router as appointments_router
from app.api.v1.endpoints.gates import router as gates_router
from app.api.v1.endpoints.visits import router as visits_router
from app.api.v1.endpoints.ai_recognition import router as ai_recognition_router
from app.api.v1.endpoints.telemetry import router as telemetry_router
from app.api.v1.endpoints.decisions import router as decisions_router

__all__ = [
    "auth_router",
    "trucks_router",
    "drivers_router",
    "appointments_router",
    "gates_router",
    "visits_router",
    "ai_recognition_router",
    "telemetry_router",
    "decisions_router",
]
