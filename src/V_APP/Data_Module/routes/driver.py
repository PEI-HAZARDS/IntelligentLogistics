"""
Driver Routes - Endpoints for drivers and mobile authentication.
Consumed by: Driver mobile app, backoffice.

Authentication Flow (Current - Simplified):
- POST /drivers/login: Validates credentials, returns driver info
- POST /drivers/claim: Uses PIN (arrival_id) to access delivery
- No token required for now - will be implemented with OAuth 2.0

Future: OAuth 2.0 + JWT
- All /me/* endpoints will require Bearer token
- Proper session management with refresh tokens

CQRS: GET endpoints read from MongoDB. POST (auth/claim) use UoW.
"""

from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Path

from application.schemas import (
    Driver, Appointment,
    DriverLoginRequest, DriverLoginResponse,
    ClaimAppointmentRequest, ClaimAppointmentResponse,
)
from application.use_cases.driver_handlers import (
    authenticate_driver,
    claim_appointment_by_pin,
)
from application.queries.driver_queries import (
    get_drivers,
    get_driver_by_license,
    get_driver_active_appointment,
    get_driver_today_appointments,
    get_driver_appointments,
)
from infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from infrastructure.persistence.postgres import SessionLocal
from infrastructure.persistence.redis import set_session, delete_session
from config import settings
from utils.auth_token import generate_internal_jwt, require_role

router = APIRouter(prefix="/drivers", tags=["Drivers"])

_uow_factory = lambda: SqlAlchemyUnitOfWork(SessionLocal)


# ==================== AUTH ENDPOINTS (Mobile App) ====================

@router.post("/login", response_model=DriverLoginResponse, responses={401: {"description": "Invalid credentials or account deactivated"}})
def login(credentials: DriverLoginRequest):
    """
    Driver login for mobile app.
    Validates credentials and returns driver info.

    Future: Will return JWT token when OAuth 2.0 is implemented.
    """
    driver = authenticate_driver(
        _uow_factory,
        drivers_license=credentials.drivers_license,
        password=credentials.password,
    )

    if not driver:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials or account deactivated",
        )

    # KEYCLOAK: this token will be issued by Keycloak once integrated.
    # For now, return a signed internal JWT so the flow is functional end-to-end.
    token = generate_internal_jwt(sub=driver["drivers_license"], role="driver")

    # Store session in Redis (TTL 3600s) so the token can be revoked server-side.
    set_session("driver", driver["drivers_license"], {
        "sub": driver["drivers_license"],
        "role": "driver",
        "name": driver["name"],
    })

    return DriverLoginResponse(
        token=token,
        drivers_license=driver["drivers_license"],
        name=driver["name"],
        company_nif=driver["company_nif"],
        company_name=driver.get("company_name", "No company"),
    )


@router.post("/claim", response_model=ClaimAppointmentResponse, responses={400: {"description": "Invalid PIN or appointment not available"}})
def claim_arrival(
    claim_data: ClaimAppointmentRequest,
    drivers_license: Annotated[str, Query(description="Driver's license (from login)")],
    debug: Annotated[bool, Query(description="Debug mode - bypass sequential check")] = False,
):
    """
    Driver uses PIN (arrival_id) to claim an appointment.
    Returns delivery details for navigation.

    In production: validates sequential order.
    In debug mode (DEBUG_MODE=true): allows claiming any appointment.

    Future: Will require Bearer token when OAuth 2.0 is implemented.
    """
    use_debug = debug and settings.debug_mode

    appointment, error = claim_appointment_by_pin(
        _uow_factory,
        drivers_license=drivers_license,
        arrival_id=claim_data.arrival_id,
        debug_mode=use_debug,
    )

    if not appointment:
        raise HTTPException(
            status_code=400,
            detail=error or "Invalid PIN or appointment not available",
        )

    return ClaimAppointmentResponse(
        appointment_id=appointment["id"],
        dock_bay_number=appointment.get("dock_bay_number"),
        dock_location=appointment.get("dock_location"),
        license_plate=appointment.get("truck_license_plate"),
        cargo_description=appointment.get("cargo_description"),
        navigation_url=appointment.get("navigation_url"),
    )


_driver_claims = require_role("driver")


@router.get("/me/active", response_model=Optional[Appointment])
def get_my_active_arrival(
    claims: Annotated[dict, Depends(_driver_claims)],
):
    """Gets driver's active appointment. Requires driver JWT."""
    return get_driver_active_appointment(claims["sub"])


@router.get("/me/today", response_model=List[Appointment])
def get_my_today_arrivals(
    claims: Annotated[dict, Depends(_driver_claims)],
):
    """Gets today's appointments for the authenticated driver."""
    return get_driver_today_appointments(claims["sub"])


@router.get("/me/history", response_model=List[Appointment])
def get_my_history(
    claims: Annotated[dict, Depends(_driver_claims)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """Gets driver's delivery history."""
    return get_driver_appointments(claims["sub"], limit=limit)


# ==================== QUERY ENDPOINTS (Backoffice) ====================

@router.get("", response_model=List[Driver])
def list_all_drivers(
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    only_active: Annotated[bool, Query()] = True,
):
    """Lists all drivers (backoffice)."""
    return get_drivers(skip=skip, limit=limit, only_active=only_active)


@router.get("/{drivers_license}", response_model=Driver, responses={404: {"description": "Driver not found"}})
def get_driver(
    drivers_license: Annotated[str, Path()],
):
    """Gets driver details (backoffice)."""
    driver = get_driver_by_license(drivers_license)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    return driver


@router.get("/{drivers_license}/arrivals", response_model=List[Appointment])
def get_arrivals_for_driver(
    drivers_license: Annotated[str, Path()],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """Gets appointment history for driver (backoffice)."""
    return get_driver_appointments(drivers_license, limit=limit)
