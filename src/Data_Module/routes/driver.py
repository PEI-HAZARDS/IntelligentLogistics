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
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session

from models.pydantic_models import (
    Driver, Appointment,
    DriverLoginRequest, DriverLoginResponse,
    ClaimAppointmentRequest, ClaimAppointmentResponse
)
from services.driver_service import (
    get_drivers,
    get_driver_appointments,
    get_driver_today_appointments,
    get_driver_by_license,
    authenticate_driver,
    claim_appointment_by_pin,
    get_driver_active_appointment,
)
from db.postgres import get_db
from config import settings

router = APIRouter(prefix="/drivers", tags=["Drivers"])


# ==================== AUTH ENDPOINTS (Mobile App) ====================

@router.post("/login", response_model=DriverLoginResponse)
def login(
    credentials: DriverLoginRequest,
    db: Session = Depends(get_db)
):
    """
    Driver login for mobile app.
    Validates credentials and returns driver info.
    
    Future: Will return JWT token when OAuth 2.0 is implemented.
    """
    driver = authenticate_driver(
        db,
        drivers_license=credentials.drivers_license,
        password=credentials.password
    )
    
    if not driver:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials or account deactivated"
        )
    
    return DriverLoginResponse(
        token="",  # Reserved for OAuth 2.0
        drivers_license=driver.drivers_license,
        name=driver.name,
        company_nif=driver.company_nif,
        company_name=driver.company.name if driver.company else "No company"
    )


@router.post("/claim", response_model=ClaimAppointmentResponse)
def claim_arrival(
    claim_data: ClaimAppointmentRequest,
    drivers_license: str = Query(..., description="Driver's license (from login)"),
    debug: bool = Query(False, description="Debug mode - bypass sequential check"),
    db: Session = Depends(get_db)
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
        db, drivers_license, claim_data.arrival_id, use_debug
    )
    
    if not appointment:
        raise HTTPException(
            status_code=400,
            detail=error or "Invalid PIN or appointment not available"
        )
    
    # Build navigation URL
    navigation_url = None
    if appointment.terminal and appointment.terminal.latitude and appointment.terminal.longitude:
        lat = appointment.terminal.latitude
        lon = appointment.terminal.longitude
        navigation_url = f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"
    
    # Get cargo description
    cargo_description = None
    if appointment.booking and appointment.booking.cargos:
        cargo = appointment.booking.cargos[0]
        cargo_description = cargo.description
    
    return ClaimAppointmentResponse(
        appointment_id=appointment.id,
        dock_bay_number=None,
        dock_location=None,
        license_plate=appointment.truck_license_plate,
        cargo_description=cargo_description,
        navigation_url=navigation_url
    )


@router.get("/me/active", response_model=Optional[Appointment])
def get_my_active_arrival(
    drivers_license: str = Query(..., description="Driver's license"),
    db: Session = Depends(get_db)
):
    """
    Gets driver's active appointment (first in queue).
    
    Future: Will use Bearer token when OAuth 2.0 is implemented.
    """
    appointment = get_driver_active_appointment(db, drivers_license)
    
    if not appointment:
        return None
    
    return Appointment.model_validate(appointment)


@router.get("/me/today", response_model=List[Appointment])
def get_my_today_arrivals(
    drivers_license: str = Query(..., description="Driver's license"),
    db: Session = Depends(get_db)
):
    """
    Gets today's appointments for the driver.
    
    Future: Will use Bearer token when OAuth 2.0 is implemented.
    """
    appointments = get_driver_today_appointments(db, drivers_license)
    return [Appointment.model_validate(a) for a in appointments]


@router.get("/me/history", response_model=List[Appointment])
def get_my_history(
    drivers_license: str = Query(..., description="Driver's license"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    Gets driver's delivery history.
    
    Future: Will use Bearer token when OAuth 2.0 is implemented.
    """
    appointments = get_driver_appointments(db, drivers_license, limit=limit)
    return [Appointment.model_validate(a) for a in appointments]


# ==================== QUERY ENDPOINTS (Backoffice) ====================

@router.get("", response_model=List[Driver])
def list_all_drivers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    only_active: bool = Query(True),
    db: Session = Depends(get_db)
):
    """Lists all drivers (backoffice)."""
    drivers = get_drivers(db, skip=skip, limit=limit, only_active=only_active)
    return [Driver.model_validate(d) for d in drivers]


@router.get("/{drivers_license}", response_model=Driver)
def get_driver(
    drivers_license: str = Path(...),
    db: Session = Depends(get_db)
):
    """Gets driver details (backoffice)."""
    driver = get_driver_by_license(db, drivers_license)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    return Driver.model_validate(driver)


@router.get("/{drivers_license}/arrivals", response_model=List[Appointment])
def get_arrivals_for_driver(
    drivers_license: str = Path(...),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Gets appointment history for driver (backoffice)."""
    appointments = get_driver_appointments(db, drivers_license, limit=limit)
    return [Appointment.model_validate(a) for a in appointments]
