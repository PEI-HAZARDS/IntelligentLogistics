"""
Driver Service - Driver management and mobile authentication.
Used by: Driver mobile app.

Authentication Flow (Current - Simplified):
- Driver logs in with credentials (license + password) to validate identity
- Driver accesses deliveries using PIN (arrival_id)
- Simple flow without persistent session tokens

Future: OAuth 2.0 + JWT
- Will implement proper token-based authentication with JWT
- Endpoints will require Bearer tokens
- Session fields in Driver model are reserved for this purpose
"""

from typing import List, Optional, Tuple
from datetime import datetime, date
from sqlalchemy.orm import Session, joinedload
from utils.hashing_pass import hash_password, verify_password

from models.sql_models import Driver, Appointment, Visit, Company, Booking
from config import settings


# ==================== AUTH FUNCTIONS ====================

def authenticate_driver(db: Session, drivers_license: str, password: str) -> Optional[Driver]:
    """
    Authenticates driver for mobile app login.
    Validates credentials and returns driver info if valid.
    
    Current: Simple credential validation, no persistent session.
    Future: Will generate JWT token when OAuth 2.0 is implemented.
    """
    driver = db.query(Driver).filter(
        Driver.drivers_license == drivers_license
    ).first()
    
    if not driver:
        return None
    
    if not driver.active:
        return None
    
    if not verify_password(password, driver.password_hash):
        return None
    
    return driver


def get_driver_by_license(db: Session, drivers_license: str) -> Optional[Driver]:
    """Gets driver by license number."""
    return db.query(Driver).filter(Driver.drivers_license == drivers_license).first()


# ==================== PIN/CLAIM FUNCTIONS ====================

def get_next_appointment_in_queue(db: Session, drivers_license: str) -> Optional[Appointment]:
    """
    Returns the next appointment in the sequential queue for the driver.
    This is the earliest active appointment by scheduled_start_time.
    """
    return db.query(Appointment).filter(
        Appointment.driver_license == drivers_license,
        Appointment.status.in_(['in_transit', 'delayed', 'in_process']),
    ).order_by(Appointment.scheduled_start_time.asc()).first()


def claim_appointment_by_pin(
    db: Session, 
    drivers_license: str, 
    arrival_id: str,
    debug_mode: bool = False
) -> Tuple[Optional[Appointment], str]:
    """
    Driver uses PIN/arrival_id to claim an appointment.
    
    In production mode: validates that this is the next appointment in sequence.
    In debug mode: allows claiming any of the driver's appointments.
    
    Returns: (appointment, error_message)
    """
    # Find appointment by arrival_id (PIN)
    appointment = db.query(Appointment).options(
        joinedload(Appointment.booking).joinedload(Booking.cargos),
        joinedload(Appointment.terminal),
        joinedload(Appointment.gate_in),
        joinedload(Appointment.truck)
    ).filter(
        Appointment.arrival_id == arrival_id
    ).first()
    
    if not appointment:
        return None, "Invalid PIN or appointment not found"
    
    # Verify driver is authorized for this appointment
    if appointment.driver_license != drivers_license:
        return None, "Not authorized for this appointment"
    
    # Check if appointment is in a claimable state
    if appointment.status not in ['in_transit', 'delayed', 'in_process']:
        return None, f"Appointment cannot be claimed (status: {appointment.status})"
    
    # In production mode, validate sequential access
    use_debug = debug_mode or settings.debug_mode
    if not use_debug:
        next_in_queue = get_next_appointment_in_queue(db, drivers_license)
        if next_in_queue and next_in_queue.id != appointment.id:
            return None, f"Must complete delivery {next_in_queue.arrival_id} first"
    
    return appointment, ""


def get_driver_active_appointment(db: Session, drivers_license: str) -> Optional[Appointment]:
    """
    Gets the active appointment for a driver.
    Returns the earliest active appointment by scheduled_start_time.
    """
    appointment = db.query(Appointment).options(
        joinedload(Appointment.booking).joinedload(Booking.cargos),
        joinedload(Appointment.terminal),
        joinedload(Appointment.gate_in),
        joinedload(Appointment.driver),
        joinedload(Appointment.truck)
    ).filter(
        Appointment.driver_license == drivers_license,
        Appointment.status.in_(['in_transit', 'delayed', 'in_process']),
    ).order_by(Appointment.scheduled_start_time.asc()).first()
    
    return appointment


# ==================== QUERY FUNCTIONS ====================

def get_drivers(db: Session, skip: int = 0, limit: int = 100, only_active: bool = True) -> List[Driver]:
    """Returns drivers with pagination."""
    query = db.query(Driver)
    
    if only_active:
        query = query.filter(Driver.active == True)
    
    return query.offset(skip).limit(limit).all()


def get_driver_appointments(db: Session, drivers_license: str, limit: int = 50) -> List[Appointment]:
    """Returns appointments for a driver."""
    return db.query(Appointment).filter(
        Appointment.driver_license == drivers_license
    ).order_by(Appointment.scheduled_start_time.desc()).limit(limit).all()


def get_driver_today_appointments(db: Session, drivers_license: str) -> List[Appointment]:
    """Returns today's appointments for a driver."""
    from sqlalchemy import func
    
    return db.query(Appointment).options(
        joinedload(Appointment.booking).joinedload(Booking.cargos),
        joinedload(Appointment.terminal),
        joinedload(Appointment.gate_in),
        joinedload(Appointment.truck)
    ).filter(
        Appointment.driver_license == drivers_license,
        func.date(Appointment.scheduled_start_time) == date.today()
    ).order_by(Appointment.scheduled_start_time.asc()).all()


# ==================== ADMIN FUNCTIONS ====================

def create_driver(
    db: Session,
    drivers_license: str,
    name: str,
    password: str,
    company_nif: Optional[str] = None
) -> Driver:
    """Creates a new driver."""
    driver = Driver(
        drivers_license=drivers_license,
        name=name,
        password_hash=hash_password(password),
        company_nif=company_nif,
        active=True
    )
    db.add(driver)
    db.commit()
    db.refresh(driver)
    return driver


def update_driver_password(db: Session, drivers_license: str, new_password: str) -> Optional[Driver]:
    """Updates a driver's password."""
    driver = db.query(Driver).filter(Driver.drivers_license == drivers_license).first()
    if not driver:
        return None
    
    driver.password_hash = hash_password(new_password)
    db.commit()
    db.refresh(driver)
    return driver


def deactivate_driver(db: Session, drivers_license: str) -> Optional[Driver]:
    """Deactivates a driver (soft delete)."""
    driver = db.query(Driver).filter(Driver.drivers_license == drivers_license).first()
    if not driver:
        return None
    
    driver.active = False
    db.commit()
    db.refresh(driver)
    return driver
