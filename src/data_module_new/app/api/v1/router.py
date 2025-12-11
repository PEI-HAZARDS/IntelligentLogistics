from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth_router,
    trucks_router,
    drivers_router,
    appointments_router,
    gates_router,
    visits_router,
    ai_recognition_router,
    telemetry_router,
    decisions_router,
)


api_router = APIRouter(prefix="/api/v1")

# Include all route modules
api_router.include_router(auth_router)
api_router.include_router(trucks_router)
api_router.include_router(drivers_router)
api_router.include_router(appointments_router)
api_router.include_router(gates_router)
api_router.include_router(visits_router)
api_router.include_router(ai_recognition_router)
api_router.include_router(telemetry_router)
api_router.include_router(decisions_router)
