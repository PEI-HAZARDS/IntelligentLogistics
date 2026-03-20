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

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Path

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
from config import settings
from utils.auth_token import generate_internal_jwt

router = APIRouter(prefix="/drivers", tags=["Drivers"])

_uow_factory = SqlAlchemyUnitOfWork


# ==================== AUTH ENDPOINTS (Mobile App) ====================

@router.post("/login", response_model=DriverLoginResponse)
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

    return DriverLoginResponse(
        token=token,
        drivers_license=driver["drivers_license"],
        name=driver["name"],
        company_nif=driver["company_nif"],
        company_name=driver.get("company_name", "No company"),
    )


@router.post("/claim", response_model=ClaimAppointmentResponse)
def claim_arrival(
    claim_data: ClaimAppointmentRequest,
    drivers_license: str = Query(..., description="Driver's license (from login)"),
    debug: bool = Query(False, description="Debug mode - bypass sequential check"),
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
        dock_bay_number=None,
        dock_location=None,
        license_plate=appointment.get("truck_license_plate"),
        cargo_description=appointment.get("cargo_description"),
        navigation_url=appointment.get("navigation_url"),
    )


@router.get("/me/active", response_model=Optional[Appointment])
def get_my_active_arrival(
    drivers_license: str = Query(..., description="Driver's license"),
):
    """
    Gets driver's active appointment (first in queue).

    Future: Will use Bearer token when OAuth 2.0 is implemented.
    """
    return get_driver_active_appointment(drivers_license)


@router.get("/me/today", response_model=List[Appointment])
def get_my_today_arrivals(
    drivers_license: str = Query(..., description="Driver's license"),
):
    """
    Gets today's appointments for the driver.

    Future: Will use Bearer token when OAuth 2.0 is implemented.
    """
    return get_driver_today_appointments(drivers_license)


@router.get("/me/history", response_model=List[Appointment])
def get_my_history(
    drivers_license: str = Query(..., description="Driver's license"),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Gets driver's delivery history.

    Future: Will use Bearer token when OAuth 2.0 is implemented.
    """
    return get_driver_appointments(drivers_license, limit=limit)


# ==================== QUERY ENDPOINTS (Backoffice) ====================

@router.get("", response_model=List[Driver])
def list_all_drivers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    only_active: bool = Query(True),
):
    """Lists all drivers (backoffice)."""
    return get_drivers(skip=skip, limit=limit, only_active=only_active)


@router.get("/{drivers_license}", response_model=Driver)
def get_driver(
    drivers_license: str = Path(...),
):
    """Gets driver details (backoffice)."""
    driver = get_driver_by_license(drivers_license)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    return driver


@router.get("/{drivers_license}/arrivals", response_model=List[Appointment])
def get_arrivals_for_driver(
    drivers_license: str = Path(...),
    limit: int = Query(50, ge=1, le=200),
):
    """Gets appointment history for driver (backoffice)."""
    return get_driver_appointments(drivers_license, limit=limit)
