"""
Worker Service - Worker management (operators and managers).
Used by: Backoffice frontend, authentication.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, date
from sqlalchemy.orm import Session
from sqlalchemy import func
from utils.hashing_pass import hash_password, verify_password

from models.sql_models import Worker, Manager, Operator, Shift, Gate, Appointment, Visit, Alert, ShiftType


# ==================== AUTHENTICATION ====================

def authenticate_worker(db: Session, email: str, password: str) -> Optional[Worker]:
    """
    Authenticates worker (operator or manager).
    Returns worker if credentials valid, None otherwise.
    """
    worker = db.query(Worker).filter(
        Worker.email == email,
        Worker.active == True
    ).first()
    
    if not worker:
        return None
    
    if not verify_password(password, worker.password_hash):
        return None
    
    return worker


def get_worker_by_email(db: Session, email: str) -> Optional[Worker]:
    """Gets worker by email."""
    return db.query(Worker).filter(Worker.email == email).first()


def get_worker_by_num_worker(db: Session, num_worker: str) -> Optional[Worker]:
    """Gets worker by num_worker."""
    return db.query(Worker).filter(Worker.num_worker == num_worker).first()


def get_worker_role(db: Session, num_worker: str) -> Optional[str]:
    """Gets worker role (manager or operator)."""
    if db.query(Manager).filter(Manager.num_worker == num_worker).first():
        return "manager"
    if db.query(Operator).filter(Operator.num_worker == num_worker).first():
        return "operator"
    return None


# ==================== WORKER QUERIES ====================

def get_all_workers(db: Session, skip: int = 0, limit: int = 100, only_active: bool = True) -> List[Worker]:
    """Gets list of workers."""
    query = db.query(Worker)
    
    if only_active:
        query = query.filter(Worker.active == True)
    
    return query.offset(skip).limit(limit).all()


def get_operators(db: Session, skip: int = 0, limit: int = 100) -> List[Operator]:
    """Gets list of operators."""
    return db.query(Operator).offset(skip).limit(limit).all()


def get_managers(db: Session, skip: int = 0, limit: int = 100) -> List[Manager]:
    """Gets list of managers."""
    return db.query(Manager).offset(skip).limit(limit).all()


# ==================== OPERATOR FUNCTIONS ====================

def get_operator_info(db: Session, num_worker: str) -> Optional[Dict[str, Any]]:
    """Gets complete operator information."""
    operator = db.query(Operator).filter(Operator.num_worker == num_worker).first()
    
    if not operator:
        return None
    
    worker = operator.worker
    
    return {
        "num_worker": worker.num_worker,
        "name": worker.name,
        "email": worker.email,
        "phone": worker.phone,
        "role": "operator",
        "active": worker.active,
        "created_at": worker.created_at
    }


def get_operator_current_shift(db: Session, num_worker: str, gate_id: int) -> Optional[Shift]:
    """
    Gets operator's current shift.
    Filters by today's date and gate.
    """
    today = date.today()
    
    shift = db.query(Shift).filter(
        Shift.operator_num_worker == num_worker,
        Shift.gate_id == gate_id,
        Shift.date == today
    ).first()
    
    return shift


def get_operator_shifts(db: Session, num_worker: str, gate_id: Optional[int] = None) -> List[Shift]:
    """
    Gets operator's shifts.
    Filters by gate if provided.
    """
    query = db.query(Shift).filter(Shift.operator_num_worker == num_worker)
    
    if gate_id:
        query = query.filter(Shift.gate_id == gate_id)
    
    return query.order_by(Shift.date.desc()).all()


def get_operator_gate_dashboard(db: Session, num_worker: str, gate_id: int) -> Dict[str, Any]:
    """
    Gets operator dashboard data for a gate.
    Includes: upcoming arrivals, statistics.
    """
    today = date.today()
    
    # Upcoming appointments (using new status values)
    upcoming = db.query(Appointment).filter(
        Appointment.gate_in_id == gate_id,
        func.date(Appointment.scheduled_start_time) == today,
        Appointment.status.in_(['in_transit', 'delayed'])
    ).order_by(Appointment.scheduled_start_time.asc()).limit(10).all()
    
    # Statistics by status
    stats = db.query(
        Appointment.status,
        func.count(Appointment.id)
    ).filter(
        Appointment.gate_in_id == gate_id,
        func.date(Appointment.scheduled_start_time) == today
    ).group_by(Appointment.status).all()
    
    stats_dict = {status: count for status, count in stats}
    
    return {
        "operator_num_worker": num_worker,
        "gate_id": gate_id,
        "date": today.isoformat(),
        "upcoming_arrivals": [
            {
                "appointment_id": a.id,
                "license_plate": a.truck_license_plate,
                "scheduled_time": a.scheduled_start_time.isoformat() if a.scheduled_start_time else None,
                "terminal_id": a.terminal_id,
                "status": a.status
            }
            for a in upcoming
        ],
        "stats": {
            "in_transit": stats_dict.get("in_transit", 0),
            "delayed": stats_dict.get("delayed", 0),
            "completed": stats_dict.get("completed", 0),
            "canceled": stats_dict.get("canceled", 0)
        }
    }


# ==================== MANAGER FUNCTIONS ====================

def get_manager_info(db: Session, num_worker: str) -> Optional[Dict[str, Any]]:
    """Gets complete manager information."""
    manager = db.query(Manager).filter(Manager.num_worker == num_worker).first()
    
    if not manager:
        return None
    
    worker = manager.worker
    
    return {
        "num_worker": worker.num_worker,
        "name": worker.name,
        "email": worker.email,
        "phone": worker.phone,
        "role": "manager",
        "access_level": manager.access_level,
        "active": worker.active,
        "created_at": worker.created_at
    }


def get_manager_shifts(db: Session, num_worker: str) -> List[Shift]:
    """Gets shifts managed by a manager."""
    return db.query(Shift).filter(
        Shift.manager_num_worker == num_worker
    ).order_by(Shift.date.desc()).all()


def get_manager_overview(db: Session, num_worker: str) -> Dict[str, Any]:
    """
    Gets manager overview: gates, shifts, alerts, performance.
    """
    today = date.today()
    
    # All gates
    all_gates = db.query(Gate).all()
    
    # Today's shifts
    today_shifts = db.query(Shift).filter(
        Shift.manager_num_worker == num_worker,
        Shift.date == today
    ).all()
    
    # Recent alerts
    recent_alerts = db.query(Alert).order_by(Alert.timestamp.desc()).limit(20).all()
    
    # Appointments by status (today)
    stats = db.query(
        Appointment.status,
        func.count(Appointment.id)
    ).filter(
        func.date(Appointment.scheduled_start_time) == today
    ).group_by(Appointment.status).all()
    
    return {
        "manager_num_worker": num_worker,
        "date": today.isoformat(),
        "active_gates": len(all_gates),
        "shifts_today": len(today_shifts),
        "recent_alerts": len(recent_alerts),
        "statistics": {
            status: count
            for status, count in stats
        }
    }


# ==================== ADMIN FUNCTIONS ====================

def create_worker(
    db: Session,
    num_worker: str,
    name: str,
    email: str,
    password: str,
    role: str,  # "operator" or "manager"
    access_level: Optional[str] = None,
    phone: Optional[str] = None
) -> Optional[Worker]:
    """
    Creates new worker (operator or manager).
    """
    # Check if email already exists
    if db.query(Worker).filter(Worker.email == email).first():
        return None
    
    # Check if num_worker already exists
    if db.query(Worker).filter(Worker.num_worker == num_worker).first():
        return None
    
    worker = Worker(
        num_worker=num_worker,
        name=name,
        email=email,
        phone=phone,
        password_hash=hash_password(password),
        active=True,
        created_at=datetime.now(timezone.utc)
    )
    db.add(worker)
    db.commit()
    db.refresh(worker)
    
    # If manager, create Manager record
    if role == "manager":
        manager = Manager(
            num_worker=num_worker,
            access_level=access_level or "basic"
        )
        db.add(manager)
        db.commit()
    
    # If operator, create Operator record
    elif role == "operator":
        operator = Operator(num_worker=num_worker)
        db.add(operator)
        db.commit()
    
    return worker


def update_worker_password(db: Session, num_worker: str, new_password: str) -> Optional[Worker]:
    """Updates a worker's password."""
    worker = get_worker_by_num_worker(db, num_worker)
    if not worker:
        return None
    
    worker.password_hash = hash_password(new_password)
    db.commit()
    db.refresh(worker)
    return worker


def update_worker_email(db: Session, num_worker: str, new_email: str) -> Optional[Worker]:
    """Updates a worker's email."""
    worker = get_worker_by_num_worker(db, num_worker)
    if not worker:
        return None
    
    # Check if new email already exists
    if db.query(Worker).filter(
        Worker.email == new_email,
        Worker.num_worker != num_worker
    ).first():
        return None
    
    worker.email = new_email
    db.commit()
    db.refresh(worker)
    return worker


def deactivate_worker(db: Session, num_worker: str) -> Optional[Worker]:
    """Deactivates a worker (soft delete)."""
    worker = get_worker_by_num_worker(db, num_worker)
    if not worker:
        return None
    
    worker.active = False
    db.commit()
    db.refresh(worker)
    return worker


def promote_to_manager(db: Session, num_worker: str, access_level: str = "basic") -> Optional[Manager]:
    """Promotes an operator to manager."""
    worker = get_worker_by_num_worker(db, num_worker)
    if not worker:
        return None
    
    # Check if already a manager
    if db.query(Manager).filter(Manager.num_worker == num_worker).first():
        return None
    
    # Check if is an operator
    operator = db.query(Operator).filter(Operator.num_worker == num_worker).first()
    if operator:
        db.delete(operator)
    
    # Create manager record
    manager = Manager(
        num_worker=num_worker,
        access_level=access_level
    )
    db.add(manager)
    db.commit()
    db.refresh(manager)
    
    return manager
