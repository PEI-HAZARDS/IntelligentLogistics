"""
Driver Service - Driver management and mobile authentication.
Used by: Driver mobile app.
"""

from typing import List, Optional
from datetime import datetime, date
from sqlalchemy.orm import Session
from utils.hashing_pass import hash_password, verify_password

from models.sql_models import Driver, Appointment, Visit, Company


# ==================== AUTH FUNCTIONS ====================

def authenticate_driver(db: Session, drivers_license: str, password: str) -> Optional[Driver]:
    """
    Authenticates driver for mobile app login.
    Returns driver if credentials valid, None otherwise.
    """
    driver = db.query(Driver).filter(
        Driver.drivers_license == drivers_license,
        Driver.active == True
    ).first()
    
    if not driver:
        return None
    
    if not verify_password(password, driver.password_hash):
        return None
    
    return driver


def get_driver_by_license(db: Session, drivers_license: str) -> Optional[Driver]:
    """Gets driver by license number."""
    return db.query(Driver).filter(Driver.drivers_license == drivers_license).first()


# ==================== PIN/CLAIM FUNCTIONS ====================

def claim_appointment_by_pin(db: Session, drivers_license: str, arrival_id: str) -> Optional[Appointment]:
    """
    Driver uses PIN/arrival_id to claim an appointment.
    Validates that the driver is associated with the appointment.
    
    Returns the appointment if valid, None otherwise.
    """
    # Find appointment by arrival_id (PIN)
    appointment = db.query(Appointment).filter(
        Appointment.arrival_id == arrival_id
    ).first()
    
    if not appointment:
        return None
    
    # Check if status allows claiming (can't claim completed appointment)
    if appointment.status in ['completed', 'canceled']:
        return None
    
    # Verify driver is authorized for this appointment
    if appointment.driver_license != drivers_license:
        return None
    
    return appointment


def get_driver_active_appointment(db: Session, drivers_license: str) -> Optional[Appointment]:
    """
    Gets the active appointment for a driver.
    An active appointment is one that:
    - Has the driver assigned
    - Status is 'pending' or 'approved'
    - Scheduled for today
    """
    # Find appointment assigned to this driver
    appointment = db.query(Appointment).filter(
        Appointment.driver_license == drivers_license,
        Appointment.status.in_(['in_transit', 'delayed']),
    ).order_by(Appointment.scheduled_start_time.asc()).first()
    
    return appointment


# ==================== QUERY FUNCTIONS ====================

def get_drivers(db: Session, skip: int = 0, limit: int = 100, only_active: bool = True) -> List[Driver]:
    """
    Returns drivers with pagination.
    """
    query = db.query(Driver)
    
    if only_active:
        query = query.filter(Driver.active == True)
    
    return query.offset(skip).limit(limit).all()


def get_driver_appointments(db: Session, drivers_license: str, limit: int = 50) -> List[Appointment]:
    """
    Returns appointments for a driver.
    """
    return db.query(Appointment).filter(
        Appointment.driver_license == drivers_license
    ).order_by(Appointment.scheduled_start_time.desc()).limit(limit).all()


def get_driver_today_appointments(db: Session, drivers_license: str) -> List[Appointment]:
    """
    Returns today's appointments for a driver.
    Used in mobile app to show daily deliveries.
    """
    from sqlalchemy import func
    
    return db.query(Appointment).filter(
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
