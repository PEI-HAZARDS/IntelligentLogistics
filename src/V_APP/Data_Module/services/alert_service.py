"""
Alert Service - Alert management (PostgreSQL).
Responsibilities:
- Create alerts (hazmat, delays, security)
- Associate alerts to visits
- List and filter alerts
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from db.postgres import SessionLocal
from models.sql_models import Alert, Visit, Appointment, Booking


# ==================== HAZMAT/ADR CODES ====================

# Common dangerous UN codes (simplified for MVP)
ADR_CODES = {
    "1203": {"description": "Gasoline", "class": "3", "hazard": "Flammable liquid"},
    "1202": {"description": "Diesel", "class": "3", "hazard": "Flammable liquid"},
    "1073": {"description": "Liquid oxygen", "class": "2.2", "hazard": "Non-flammable gas"},
    "1978": {"description": "Propane", "class": "2.1", "hazard": "Flammable gas"},
    "1789": {"description": "Hydrochloric acid", "class": "8", "hazard": "Corrosive"},
    "2031": {"description": "Nitric acid", "class": "8", "hazard": "Corrosive/Oxidizing"},
    "1830": {"description": "Sulfuric acid", "class": "8", "hazard": "Corrosive"},
    "1005": {"description": "Anhydrous ammonia", "class": "2.3", "hazard": "Toxic gas"},
    "1017": {"description": "Chlorine", "class": "2.3", "hazard": "Toxic gas"},
}

# Kemler codes (hazard numbers)
KEMLER_CODES = {
    "33": "Highly flammable liquid",
    "30": "Flammable liquid",
    "23": "Flammable gas",
    "22": "Refrigerated gas",
    "20": "Asphyxiant gas",
    "X80": "Corrosive - reacts with water",
    "80": "Corrosive",
    "60": "Toxic",
    "X66": "Very toxic - reacts with water",
}


# ==================== ALERT CREATION ====================

def create_alert(
    db: Session,
    visit_id: Optional[int],
    alert_type: str,
    description: str,
    image_url: Optional[str] = None
) -> Alert:
    """
    Creates an alert associated to a visit.
    """
    alert = Alert(
        visit_id=visit_id,
        type=alert_type,
        description=description,
        image_url=image_url,
        timestamp=datetime.now(timezone.utc)
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def create_alerts_for_visit(
    db: Session,
    visit: Visit,
    alerts_payload: List[Dict[str, Any]]
) -> List[Alert]:
    """
    Creates alerts for a visit.
    
    alerts_payload expected:
    [
        {"type": "safety", "description": "UN 1203 - Gasoline"},
        {"type": "operational", "description": "30 min delay"}
    ]
    """
    if not alerts_payload:
        return []
    
    # Create alerts
    created_alerts = []
    for alert_data in alerts_payload:
        alert = Alert(
            visit_id=visit.appointment_id,
            type=alert_data.get("type", "generic"),
            description=alert_data.get("description", "Alert without description"),
            image_url=alert_data.get("image_url"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(alert)
        created_alerts.append(alert)
    
    db.commit()
    
    # Refresh all alerts
    for a in created_alerts:
        db.refresh(a)
    
    return created_alerts


def create_alerts_for_appointment(
    db: Session,
    appointment: Appointment,
    alerts_payload: List[Dict[str, Any]]
) -> List[Alert]:
    """
    Creates alerts for an appointment.
    Associates alerts to the visit if it exists.
    
    alerts_payload expected:
    [
        {"type": "safety", "description": "UN 1203 - Gasoline"},
        {"type": "problem", "description": "Delay detected"}
    ]
    """
    if not alerts_payload:
        return []
    
    # Get visit_id from appointment
    visit_id = None
    if appointment.visit:
        visit_id = appointment.visit.appointment_id
    
    # Create alerts
    created_alerts = []
    for alert_data in alerts_payload:
        alert = Alert(
            visit_id=visit_id,
            type=alert_data.get("type", "generic"),
            description=alert_data.get("description", "Alert without description"),
            image_url=alert_data.get("image_url"),
            timestamp=datetime.now(timezone.utc)
        )
        db.add(alert)
        created_alerts.append(alert)
    
    db.commit()
    
    # Refresh all alerts
    for a in created_alerts:
        db.refresh(a)
    
    return created_alerts


def create_hazmat_alert(
    db: Session,
    appointment: Appointment,
    un_code: Optional[str] = None,
    kemler_code: Optional[str] = None,
    detected_hazmat: Optional[str] = None
) -> Optional[Alert]:
    """
    Creates hazmat/ADR specific alert.
    Used by Decision Engine when detecting hazardous cargo.
    """
    # Build description
    description_parts = ["Hazardous cargo detected"]
    
    if un_code and un_code in ADR_CODES:
        info = ADR_CODES[un_code]
        description_parts.append(f"UN {un_code} - {info['description']}")
        description_parts.append(f"Class: {info['class']}")
        description_parts.append(f"Hazard: {info['hazard']}")
    
    if kemler_code and kemler_code in KEMLER_CODES:
        description_parts.append(f"Kemler {kemler_code}: {KEMLER_CODES[kemler_code]}")
    
    if detected_hazmat:
        description_parts.append(f"Detection: {detected_hazmat}")
    
    # Get visit_id
    visit_id = None
    if appointment.visit:
        visit_id = appointment.visit.appointment_id
    
    # Determine alert type based on severity
    alert_type = "safety"
    if kemler_code and kemler_code.startswith('X'):
        alert_type = "safety"  # Critical safety alert
    
    # Create alert
    alert = Alert(
        visit_id=visit_id,
        type=alert_type,
        description=" | ".join(description_parts),
        timestamp=datetime.now(timezone.utc)
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    
    return alert


# ==================== QUERY FUNCTIONS ====================

def get_alerts(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    alert_type: Optional[str] = None,
    visit_id: Optional[int] = None
) -> List[Alert]:
    """Gets alerts with filters."""
    query = db.query(Alert)
    
    if alert_type:
        query = query.filter(Alert.type == alert_type)
    if visit_id:
        query = query.filter(Alert.visit_id == visit_id)
    
    return query.order_by(Alert.timestamp.desc()).offset(skip).limit(limit).all()


def get_alert_by_id(db: Session, alert_id: int) -> Optional[Alert]:
    """Gets alert by ID."""
    return db.query(Alert).filter(Alert.id == alert_id).first()


def get_active_alerts(db: Session, limit: int = 50) -> List[Alert]:
    """
    Gets recent alerts (last 24h).
    Used in operator panel.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    
    return db.query(Alert).filter(
        Alert.timestamp >= cutoff
    ).order_by(Alert.timestamp.desc()).limit(limit).all()


def get_alerts_count_by_type(db: Session) -> Dict[str, int]:
    """Counts alerts by type (last 24h)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    
    results = db.query(
        Alert.type,
        func.count(Alert.id)
    ).filter(
        Alert.timestamp >= cutoff
    ).group_by(Alert.type).all()
    
    return {alert_type: count for alert_type, count in results}


def get_alerts_for_visit(db: Session, visit_id: int) -> List[Alert]:
    """Gets all alerts for a specific visit."""
    return db.query(Alert).filter(
        Alert.visit_id == visit_id
    ).order_by(Alert.timestamp.desc()).all()