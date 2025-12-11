from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    VARCHAR,
    Text,
    DateTime,
    Date,
    Time,
    Boolean,
    ForeignKey,
    DECIMAL,
    Float,
    JSON,
    func,
    Index,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry

Base = declarative_base()

# ---------- Enums (Postgres) ----------
zone_type_enum = PGEnum('YARD', 'WAREHOUSE', 'GATE_COMPLEX', 'INSPECTION', name='zone_type', create_type=False)

gate_direction_enum = PGEnum('INBOUND', 'OUTBOUND', name='gate_direction', create_type=False)
gate_operational_status_enum = PGEnum('OPEN', 'CLOSED', 'MAINTENANCE', name='gate_operational_status', create_type=False)

location_usage_status_enum = PGEnum('EMPTY', 'OCCUPIED', 'RESERVED', name='location_usage_status', create_type=False)

chassis_type_enum = PGEnum('FLATBED', 'SKELETAL', 'BOX', name='chassis_type', create_type=False)
emission_standard_enum = PGEnum('EURO5', 'EURO6', 'EV', name='emission_standard', create_type=False)

appointment_direction_enum = PGEnum('IMPORT', 'EXPORT', name='appointment_direction', create_type=False)
appointment_status_enum = PGEnum('CREATED', 'CONFIRMED', 'COMPLETED', 'MISSED', 'CANCELLED', name='appointment_status', create_type=False)

visit_stage_enum = PGEnum('AT_GATE', 'ROUTED', 'IN_YARD', 'SERVICING', 'EXIT_QUEUE', 'COMPLETE', name='visit_stage', create_type=False)

event_type_enum = PGEnum('GATE_CHECK_IN', 'ARRIVED_AT_STACK', 'LIFT_ON_START', 'LIFT_ON_END', 'GATE_OUT', name='event_type', create_type=False)

ai_object_class_enum = PGEnum(name='ai_object_class', *['TRUCK', 'CONTAINER', 'HAZMAT_SIGN'], create_type=False)
ai_reason_code_enum = PGEnum('OCR_ERROR', 'MISCLASSIFICATION', 'GLARE', 'OCCLUSION', name='ai_reason_code', create_type=False)

shift_type_enum = PGEnum('MORNING', 'AFTERNOON', 'NIGHT', name='shift_type', create_type=False)

# ---------- Tables ----------
class InfrastructureZone(Base):
    __tablename__ = 'infrastructure_zones'

    zone_id = Column(Integer, primary_key=True)
    zone_code = Column(String(10), unique=True, nullable=False)
    zone_name = Column(String(100), nullable=False)
    zone_type = Column(zone_type_enum, nullable=False)
    is_hazmat_approved = Column(Boolean, default=False, nullable=False)
    geo_polygon = Column(Geometry('POLYGON'))
    max_capacity_teu = Column(Integer)

    gates = relationship('Gate', back_populates='zone')
    internal_locations = relationship('InternalLocation', back_populates='zone')


class Gate(Base):
    __tablename__ = 'gates'

    gate_id = Column(Integer, primary_key=True)
    zone_id = Column(Integer, ForeignKey('infrastructure_zones.zone_id'), nullable=False)
    gate_label = Column(String(50), nullable=False)
    direction = Column(gate_direction_enum, nullable=False)
    camera_rtsp_url = Column(String(255))
    barrier_device_id = Column(String(50))
    operational_status = Column(gate_operational_status_enum, nullable=False, server_default='OPEN')

    zone = relationship('InfrastructureZone', back_populates='gates')
    visits_entered = relationship('GateVisit', foreign_keys='GateVisit.entry_gate_id', back_populates='entry_gate')
    visits_exited = relationship('GateVisit', foreign_keys='GateVisit.exit_gate_id', back_populates='exit_gate')
    ai_recognitions = relationship('AIRecognitionEvent', back_populates='gate')


class InternalLocation(Base):
    __tablename__ = 'internal_locations'

    location_id = Column(BigInteger, primary_key=True)
    zone_id = Column(Integer, ForeignKey('infrastructure_zones.zone_id'), nullable=False)
    aisle_number = Column(String(5))
    bay_number = Column(String(5))
    tier_height = Column(Integer)
    current_usage_status = Column(location_usage_status_enum, nullable=False, server_default='EMPTY')

    zone = relationship('InfrastructureZone', back_populates='internal_locations')


class HaulerCompany(Base):
    __tablename__ = 'hauler_companies'

    hauler_id = Column(Integer, primary_key=True)
    company_name = Column(String(150), nullable=False)
    tax_id = Column(String(50))
    api_key = Column(String(256))
    safety_rating = Column(DECIMAL(3,2))

    trucks = relationship('Truck', back_populates='hauler')
    drivers = relationship('Driver', back_populates='hauler')
    appointments = relationship('Appointment', back_populates='hauler')


class Truck(Base):
    __tablename__ = 'trucks'

    truck_id = Column(BigInteger, primary_key=True)
    hauler_id = Column(Integer, ForeignKey('hauler_companies.hauler_id'))
    license_plate = Column(String(20), unique=True, nullable=False, index=True)
    country_of_registration = Column(String(3))
    chassis_type = Column(chassis_type_enum)
    emission_standard = Column(emission_standard_enum)
    last_seen_date = Column(DateTime)

    hauler = relationship('HaulerCompany', back_populates='trucks')
    visits = relationship('GateVisit', back_populates='truck')


class Driver(Base):
    __tablename__ = 'drivers'

    driver_id = Column(BigInteger, primary_key=True)
    hauler_id = Column(Integer, ForeignKey('hauler_companies.hauler_id'))
    license_number = Column(String(50), unique=True)
    full_name = Column(String(100), nullable=False)
    mobile_device_token = Column(String(255))
    is_banned = Column(Boolean, default=False)
    biometric_hash = Column(String(255))

    hauler = relationship('HaulerCompany', back_populates='drivers')
    visits = relationship('GateVisit', back_populates='driver')




class Cargo(Base):
    __tablename__ = 'cargos'

    cargo_id = Column(BigInteger, primary_key=True)
    iso_code = Column(String(11), unique=True, index=True)
    size_type = Column(String(4))
    tare_weight_kg = Column(Integer)
    max_payload_kg = Column(Integer)

    bookings = relationship('Booking', back_populates='cargo')


class Booking(Base):
    __tablename__ = 'bookings'

    booking_id = Column(BigInteger, primary_key=True)
    booking_ref = Column(String(50), unique=True, nullable=False)
    direction = Column(appointment_direction_enum, nullable=False)
    cargo_id = Column(BigInteger, ForeignKey('cargos.cargo_id'))

    cargo = relationship('Cargo', back_populates='bookings')
    appointments = relationship('Appointment', back_populates='booking')


class Appointment(Base):
    __tablename__ = 'appointments'

    appointment_id = Column(BigInteger, primary_key=True)
    booking_id = Column(BigInteger, ForeignKey('bookings.booking_id'))
    hauler_id = Column(Integer, ForeignKey('hauler_companies.hauler_id'))
    truck_id = Column(BigInteger, ForeignKey('trucks.truck_id'))
    driver_id = Column(BigInteger, ForeignKey('drivers.driver_id'))
    scheduled_start_time = Column(DateTime, nullable=False)
    scheduled_end_time = Column(DateTime, nullable=False)
    appointment_status = Column(appointment_status_enum, nullable=False, server_default='CREATED')

    booking = relationship('Booking', back_populates='appointments')
    hauler = relationship('HaulerCompany', back_populates='appointments')
    truck = relationship('Truck')
    driver = relationship('Driver')
    visits = relationship('GateVisit', back_populates='appointment')


class GateVisit(Base):
    __tablename__ = 'gate_visits'

    visit_id = Column(BigInteger, primary_key=True, autoincrement=True)
    appointment_id = Column(BigInteger, ForeignKey('appointments.appointment_id'))
    truck_id = Column(BigInteger, ForeignKey('trucks.truck_id'))
    driver_id = Column(BigInteger, ForeignKey('drivers.driver_id'))
    entry_gate_id = Column(Integer, ForeignKey('gates.gate_id'))
    exit_gate_id = Column(Integer, ForeignKey('gates.gate_id'), nullable=True)
    gate_in_time = Column(DateTime)
    gate_out_time = Column(DateTime)
    visit_stage = Column(visit_stage_enum, nullable=False, server_default='AT_GATE')

    appointment = relationship('Appointment', back_populates='visits')
    truck = relationship('Truck', back_populates='visits')
    driver = relationship('Driver', back_populates='visits')
    entry_gate = relationship('Gate', foreign_keys=[entry_gate_id], back_populates='visits_entered')
    exit_gate = relationship('Gate', foreign_keys=[exit_gate_id], back_populates='visits_exited')
    events = relationship('VisitEventLog', back_populates='visit')


class VisitEventLog(Base):
    __tablename__ = 'visit_event_log'

    log_id = Column(BigInteger, primary_key=True)
    visit_id = Column(BigInteger, ForeignKey('gate_visits.visit_id'), nullable=False)
    event_type = Column(event_type_enum, nullable=False)
    timestamp = Column(DateTime, nullable=False, server_default=func.now())
    location_id = Column(BigInteger, ForeignKey('internal_locations.location_id'))
    description = Column(Text)

    visit = relationship('GateVisit', back_populates='events')
    location = relationship('InternalLocation')


class AIRecognitionEvent(Base):
    __tablename__ = 'ai_recognition_events'

    recognition_id = Column(BigInteger, primary_key=True)
    gate_id = Column(Integer, ForeignKey('gates.gate_id'))
    timestamp = Column(DateTime, nullable=False, server_default=func.now())
    object_class = Column(String(50))
    detected_text = Column(String(50))
    confidence_score = Column(Float)
    bounding_box_json = Column(JSONB)
    image_storage_path = Column(String(255))
    processing_duration_ms = Column(Integer)

    gate = relationship('Gate', back_populates='ai_recognitions')
    corrections = relationship('AICorrection', back_populates='recognition')


class AICorrection(Base):
    __tablename__ = 'ai_corrections'

    correction_id = Column(BigInteger, primary_key=True)
    recognition_id = Column(BigInteger, ForeignKey('ai_recognition_events.recognition_id'), nullable=False)
    corrected_value = Column(String(50))
    operator_id = Column(Integer, ForeignKey('workers.worker_id'))
    reason_code = Column(ai_reason_code_enum)
    is_retrained = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

    recognition = relationship('AIRecognitionEvent', back_populates='corrections')
    operator = relationship('Worker', back_populates='ai_corrections')


class SystemResourceMetrics(Base):
    __tablename__ = 'system_resource_metrics'

    metric_id = Column(BigInteger, primary_key=True)
    timestamp = Column(DateTime, nullable=False, server_default=func.now())
    node_id = Column(String(50), nullable=False)
    cpu_usage_pct = Column(Float)
    gpu_usage_pct = Column(Float)
    power_consumption_watts = Column(Float)
    active_camera_streams = Column(Integer)
    traffic_volume_in_gate = Column(Integer)


# ---------- Shift (Worker scheduling) ----------
class Shift(Base):
    __tablename__ = 'shifts'

    shift_id = Column(Integer, primary_key=True)
    shift_type = Column(shift_type_enum, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    description = Column(String(100))

    workers = relationship('Worker', back_populates='shift')


# ---------- Worker (Gate operator who can manually review AI results) ----------
class Worker(Base):
    __tablename__ = 'workers'

    worker_id = Column(Integer, primary_key=True)
    full_name = Column(String(150), nullable=False)
    email = Column(String(255), unique=True)
    password_hash = Column(String(255))
    role = Column(String(50), nullable=False, server_default='operator')
    assigned_gate_id = Column(Integer, ForeignKey('gates.gate_id'))
    shift_id = Column(Integer, ForeignKey('shifts.shift_id'))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    assigned_gate = relationship('Gate')
    shift = relationship('Shift', back_populates='workers')
    ai_corrections = relationship('AICorrection', back_populates='operator')


# ---------- Access Decisions (from Decision Engine) ----------
decision_status_enum = PGEnum('APPROVED', 'REJECTED', 'MANUAL_REVIEW', 'OVERRIDDEN', name='decision_status', create_type=False)


class AccessDecision(Base):
    """Stores gate access decisions made by the Decision Engine."""
    __tablename__ = 'access_decisions'

    decision_id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(String(100), unique=True, nullable=False, index=True)
    gate_id = Column(Integer, ForeignKey('gates.gate_id'), nullable=False)
    decision = Column(decision_status_enum, nullable=False)
    reason = Column(Text)
    license_plate = Column(String(20), index=True)
    un_number = Column(String(10))
    kemler_code = Column(String(10))
    plate_image_url = Column(String(500))
    hazard_image_url = Column(String(500))
    route = Column(JSONB)
    alerts = Column(JSONB)
    lp_confidence = Column(Float)
    hz_confidence = Column(Float)
    reviewed_by = Column(Integer, ForeignKey('workers.worker_id'), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    original_decision = Column(String(20), nullable=True)  # Stored when overridden
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    gate = relationship('Gate')
    reviewer = relationship('Worker')


# ---------- Indexes / Additional constraints ----------
Index('ix_trucks_license_plate', Truck.license_plate)
Index('ix_cargos_iso_code', Cargo.iso_code)
Index('ix_access_decisions_gate_created', AccessDecision.gate_id, AccessDecision.created_at.desc())

# Note for migrations:
# - The PGEnum objects above were created with create_type=False to allow Alembic to manage type creation explicitly.
# - If you prefer the models to create types automatically on metadata.create_all(), set create_type=True on each PGEnum.
