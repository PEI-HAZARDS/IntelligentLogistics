import enum
from datetime import datetime, timedelta, timezone
from sqlalchemy import func
from sqlalchemy import Column, Integer, String, Date, Time, TIMESTAMP, DECIMAL, Boolean, ForeignKey, ForeignKeyConstraint, Text, Enum as SEnum, SmallInteger, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base, relationship

from utils.crypto_utils import EncryptedString, SearchableEncryptedString

Base = declarative_base()

# Delay tolerance in minutes (appointment is delayed after this time past scheduled)
DELAY_TOLERANCE_MINUTES = 1

# ==========================
# ENUMS
# ==========================

delivery_status_enum = SEnum('not_started', 'unloading', 'completed', name='delivery_status')
physical_state_enum = SEnum('liquid', 'solid', 'gaseous', 'hybrid', name='physical_state')
access_level_enum = SEnum('admin', 'basic', name='access_level')
operational_status_enum = SEnum('maintenance', 'operational', 'closed', name='operational_status')
# 'unloading' and 'delayed' kept for backward compat with existing rows — never written by app code.
# Primary flow states: scheduled → in_transit → in_process → completed | canceled
# Sub-states: delayed (computed from time), unloading (derived from Visit.state)
appointment_status_enum = SEnum('scheduled', 'in_transit', 'in_process', 'unloading', 'canceled', 'delayed', 'completed', name='appointment_status')
type_alert_enum = SEnum('generic', 'safety', 'problem', 'operational', name='type_alert')
direction_enum = SEnum('inbound', 'outbound', name='direction')

class ShiftType(enum.Enum):
    MORNING = "MORNING"
    AFTERNOON = "AFTERNOON"
    NIGHT = "NIGHT"

    def get_hours(self):
        """Return (start_time, end_time) for this shift."""
        _hours = {
            "MORNING": ("06:00", "14:00"),
            "AFTERNOON": ("14:00", "22:00"),
            "NIGHT": ("22:00", "06:00"),
        }
        start_str, end_str = _hours[self.value]
        start_time = datetime.strptime(start_str, "%H:%M").time()
        end_time = datetime.strptime(end_str, "%H:%M").time()
        return start_time, end_time


# ==========================
# INFRASTRUCTURE: Terminal, Dock, Gate
# ==========================

class Terminal(Base):
    __tablename__ = "terminal"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(200))
    latitude = Column(DECIMAL(10, 8))
    longitude = Column(DECIMAL(11, 8))
    hazmat_approved = Column(Boolean, default=False)
    
    # Relationships
    docks = relationship("Dock", back_populates="terminal")
    appointments = relationship("Appointment", back_populates="terminal")


class Dock(Base):
    __tablename__ = "dock"

    # primary key composta da terminal_id e bay_number
    terminal_id = Column(Integer, ForeignKey('terminal.id'), primary_key=True)
    bay_number = Column(String(50), primary_key=True)
    latitude = Column(DECIMAL(10, 8))
    longitude = Column(DECIMAL(11, 8))
    current_usage = Column(operational_status_enum, default='operational')
    estado = Column(String(10), nullable=False, default='Ativo')  # BR-13

    __table_args__ = (
        CheckConstraint("estado IN ('Ativo', 'Inativo')", name='chk_dock_estado'),
    )

    # Relationships
    terminal = relationship("Terminal", back_populates="docks")


class Gate(Base):
    __tablename__ = "gate"

    id = Column(Integer, primary_key=True)
    label = Column(String(100), nullable=False)
    latitude = Column(DECIMAL(10, 8))
    longitude = Column(DECIMAL(11, 8))
    estado = Column(String(10), nullable=False, default='Ativo')  # BR-14

    __table_args__ = (
        CheckConstraint("estado IN ('Ativo', 'Inativo')", name='chk_gate_estado'),
    )

    # Relationships
    shifts = relationship("Shift", back_populates="gate")
    appointments_in = relationship(
        "Appointment",
        foreign_keys="Appointment.gate_in_id",
        back_populates="gate_in"
    )
    appointments_out = relationship(
        "Appointment",
        foreign_keys="Appointment.gate_out_id",
        back_populates="gate_out"
    )


# ==========================
# EXTERNAL: Company, Driver, Truck
# ==========================

class Company(Base):
    __tablename__ = "company"
    
    nif = Column(String(20), primary_key=True)
    name = Column(String(200), nullable=False)
    contact = Column(String(50))
    
    # Relationships
    drivers = relationship("Driver", back_populates="company")
    trucks = relationship("Truck", back_populates="company")


class Driver(Base):
    __tablename__ = "driver"

    drivers_license = Column(String(50), primary_key=True)
    company_nif = Column(String(20), ForeignKey('company.nif'))
    name = Column(String(100), nullable=False)
    password_hash = Column(Text)
    mobile_device_token = Column(EncryptedString)  # RGPD: AES-256-GCM encrypted at rest
    active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    
    current_appointment_id = Column(Integer)  # Current active delivery (for sequential access)
    
    # Relationships
    company = relationship("Company", back_populates="drivers")
    appointments = relationship("Appointment", back_populates="driver")


class Truck(Base):
    __tablename__ = "truck"
    
    license_plate = Column(String(20), primary_key=True)
    company_nif = Column(String(20), ForeignKey('company.nif'))
    brand = Column(String(100))
    
    # Relationships
    company = relationship("Company", back_populates="trucks")
    appointments = relationship("Appointment", back_populates="truck")


# ==========================
# STAFF: Worker, Manager, Operator
# ==========================

class Worker(Base):
    __tablename__ = "worker"

    num_worker = Column(String(20), primary_key=True)
    name = Column(String(200), nullable=False)
    phone = Column(EncryptedString)                          # RGPD: random-nonce AES-256-GCM (non-searchable)
    email = Column(SearchableEncryptedString, unique=True)  # RGPD: deterministic-nonce AES-256-GCM (searchable, login key)
    password_hash = Column(Text)
    active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    
    # Relationships (disjoint specialization)
    manager = relationship("Manager", back_populates="worker", uselist=False)
    operator = relationship("Operator", back_populates="worker", uselist=False)


class Manager(Base):
    __tablename__ = "manager"
    
    num_worker = Column(String(20), ForeignKey('worker.num_worker'), primary_key=True)
    access_level = Column(access_level_enum, default='basic')
    
    # Relationships
    worker = relationship("Worker", back_populates="manager")
    shifts = relationship("Shift", back_populates="manager")


class Operator(Base):
    __tablename__ = "operator"
    
    num_worker = Column(String(20), ForeignKey('worker.num_worker'), primary_key=True)
    
    # Relationships
    worker = relationship("Worker", back_populates="operator")
    shifts = relationship("Shift", back_populates="operator")


class Shift(Base):
    __tablename__ = "shift"
    
    # Composite primary key
    gate_id = Column(Integer, ForeignKey('gate.id'), nullable=False, primary_key=True)
    shift_type = Column(SEnum(ShiftType), nullable=False, primary_key=True)
    date = Column(Date, nullable=False, primary_key=True)
    
    operator_num_worker = Column(String(20), ForeignKey('operator.num_worker'))
    manager_num_worker = Column(String(20), ForeignKey('manager.num_worker'))

    # Relationships
    operator = relationship("Operator", back_populates="shifts")
    manager = relationship("Manager", back_populates="shifts")
    gate = relationship("Gate", back_populates="shifts")
    visits = relationship("Visit", back_populates="shift")
    history = relationship("ShiftAlertHistory", back_populates="shift")
    
    @property
    def start_time(self):
        """Gets start time from enum."""
        return self.shift_type.get_hours()[0]
    
    @property
    def end_time(self):
        """Gets end time from enum."""
        return self.shift_type.get_hours()[1]


# ==========================
# BOOKING & CARGO
# ==========================

class Booking(Base):
    __tablename__ = "booking"
    
    reference = Column(String(50), primary_key=True)  # e.g.: "BOOK-0001"
    direction = Column(direction_enum)  # 'inbound' or 'outbound'
    created_at = Column(TIMESTAMP, server_default=func.now())
    
    # Relationships
    cargos = relationship("Cargo", back_populates="booking")
    appointments = relationship("Appointment", back_populates="booking")


class Cargo(Base):
    __tablename__ = "cargo"
    
    id = Column(Integer, primary_key=True)
    booking_reference = Column(String(50), ForeignKey('booking.reference'), nullable=False)
    quantity = Column(DECIMAL(10, 2), nullable=False)
    state = Column(physical_state_enum, nullable=False)
    description = Column(Text)
    
    # Relationships
    booking = relationship("Booking", back_populates="cargos")


# ==========================
# PLANNING: Appointment
# ==========================

class Appointment(Base):
    __tablename__ = "appointment"
    
    id = Column(Integer, primary_key=True)
    # NOTE: unique=False for demo (all PINs forced to "1234").
    # Restore to unique=True when reverting fn_generate_arrival_id() to use the sequence.
    arrival_id = Column(String(50), unique=False, index=True)  # PIN e.g.: "1234"
    
    # Foreign Keys
    booking_reference = Column(String(50), ForeignKey('booking.reference'), nullable=False)
    driver_license = Column(String(50), ForeignKey('driver.drivers_license'), nullable=False)
    truck_license_plate = Column(String(20), ForeignKey('truck.license_plate'), nullable=False)
    terminal_id = Column(Integer, ForeignKey('terminal.id'), nullable=False)
    gate_in_id = Column(Integer, ForeignKey('gate.id'))
    gate_out_id = Column(Integer, ForeignKey('gate.id'))
    
    # Scheduling
    scheduled_start_time = Column(TIMESTAMP)
    expected_duration = Column(Integer)  # Expected duration in minutes
    
    # Status
    status = Column(appointment_status_enum, default='scheduled')
    version = Column(Integer, nullable=False, default=1, server_default="1")  # Optimistic concurrency control
    notes = Column(Text)
    highway_infraction = Column(Boolean, default=False, server_default="false")  # Hazmat truck on restricted highway route
    
    # Relationships
    booking = relationship("Booking", back_populates="appointments")
    driver = relationship("Driver", back_populates="appointments")
    truck = relationship("Truck", back_populates="appointments")
    terminal = relationship("Terminal", back_populates="appointments")
    gate_in = relationship(
        "Gate",
        foreign_keys=[gate_in_id],
        back_populates="appointments_in"
    )
    gate_out = relationship(
        "Gate",
        foreign_keys=[gate_out_id],
        back_populates="appointments_out"
    )
    visit = relationship("Visit", back_populates="appointment", uselist=False)

    @property
    def is_unloading(self) -> bool:
        """True when there is an active Visit in unloading state (out_time not yet set)."""
        if self.visit:
            return self.visit.state == 'unloading' and self.visit.out_time is None
        return False

    @property
    def computed_status(self) -> str:
        """
        Real-time display status derived from stored status + sub-state conditions.

        Primary flow stored in DB: scheduled → in_transit → in_process → completed | canceled
        Sub-states (never stored, always computed):
          - 'delayed'   — in_transit past scheduled_start_time + DELAY_TOLERANCE_MINUTES
          - 'unloading' — in_process with an active Visit in unloading state
        """
        if self.status in ('completed', 'canceled', 'scheduled'):
            return self.status

        if self.status == 'in_process':
            if self.is_unloading:
                return 'unloading'
            return 'in_process'

        # in_transit: check for delay
        if self.scheduled_start_time:
            delay_threshold = self.scheduled_start_time + timedelta(minutes=DELAY_TOLERANCE_MINUTES)
            if datetime.now(timezone.utc).replace(tzinfo=None) > delay_threshold:
                return 'delayed'

        return self.status

    @property
    def is_delayed(self) -> bool:
        """Quick check if appointment is currently delayed."""
        return self.computed_status == 'delayed'
    
    @property
    def delay_minutes(self) -> int:
        """Calculate how many minutes the appointment is delayed (0 if not delayed)."""
        if not self.scheduled_start_time or self.status in ('completed', 'canceled'):
            return 0
        
        diff = datetime.now(timezone.utc).replace(tzinfo=None) - self.scheduled_start_time
        minutes = int(diff.total_seconds() / 60)
        return max(0, minutes - DELAY_TOLERANCE_MINUTES)


# NOTE: arrival_id is auto-generated by the PostgreSQL trigger
# ``trg_generate_arrival_id`` (see scripts/triggers.sql) which uses
# the ``appointment_arrival_seq`` sequence.  This is concurrency-safe
# unlike the previous ORM before_insert listener that used max()+1.


# ==========================
# EXECUTION: Visit
# ==========================

class Visit(Base):
    __tablename__ = "visit"
    
    # PK = FK (1:1 relationship with Appointment)
    appointment_id = Column(Integer, ForeignKey('appointment.id'), primary_key=True)
    
    # Composite FK to Shift
    shift_gate_id = Column(Integer, nullable=False)
    shift_type = Column(SEnum(ShiftType), nullable=False)
    shift_date = Column(Date, nullable=False)
    
    __table_args__ = (
        ForeignKeyConstraint(['shift_gate_id', 'shift_type', 'shift_date'], 
                             ['shift.gate_id', 'shift.shift_type', 'shift.date']),
    )
    
    # Actual times
    entry_time = Column(TIMESTAMP)
    out_time = Column(TIMESTAMP)
    
    # Status
    state = Column(delivery_status_enum, default='unloading')
    
    # Relationships
    appointment = relationship("Appointment", back_populates="visit")
    shift = relationship("Shift", back_populates="visits")
    alerts = relationship("Alert", back_populates="visit")


# ==========================
# HISTORY
# ==========================

class ShiftAlertHistory(Base):
    __tablename__ = "shift_alert_history"
    
    id = Column(Integer, primary_key=True)
    
    # Composite FK to Shift
    shift_gate_id = Column(Integer, nullable=False)
    shift_type = Column(SEnum(ShiftType), nullable=False)
    shift_date = Column(Date, nullable=False)
    
    alert_id = Column(Integer, ForeignKey('alert.id'), nullable=False)
    last_update = Column(TIMESTAMP, server_default=func.now())
    
    __table_args__ = (
        ForeignKeyConstraint(['shift_gate_id', 'shift_type', 'shift_date'], 
                             ['shift.gate_id', 'shift.shift_type', 'shift.date']),
    )
    
    # Relationships
    shift = relationship("Shift", back_populates="history")
    alert = relationship("Alert", back_populates="history_entries")


# ==========================
# ALERTS
# ==========================

class Alert(Base):
    __tablename__ = "alert"

    id = Column(Integer, primary_key=True)
    visit_id = Column(Integer, ForeignKey('visit.appointment_id'))
    appointment_id = Column(Integer, ForeignKey('appointment.id'))  # Direct FK to appointment (alerts can pre-exist visits)
    timestamp = Column(TIMESTAMP, server_default=func.now())
    image_url = Column(Text)
    type = Column(type_alert_enum, default='generic')
    description = Column(Text)
    severity = Column(SmallInteger, nullable=False, default=3)  # BR-11: 1 (low) – 5 (critical)

    __table_args__ = (
        CheckConstraint('severity BETWEEN 1 AND 5', name='chk_alert_severity'),
    )

    # Relationships
    visit = relationship("Visit", back_populates="alerts")
    appointment = relationship("Appointment")
    history_entries = relationship("ShiftAlertHistory", back_populates="alert")


# ==========================
# DRIVER↔VEHICLE HISTORY (BR-52)
# ==========================

class DriverVehicle(Base):
    __tablename__ = "driver_vehicle"

    id = Column(Integer, primary_key=True)
    driver_license = Column(String(50), ForeignKey('driver.drivers_license', ondelete='RESTRICT'), nullable=False)
    truck_license_plate = Column(String(20), ForeignKey('truck.license_plate', ondelete='RESTRICT'), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)

    __table_args__ = (
        CheckConstraint('end_date IS NULL OR end_date >= start_date', name='chk_dv_dates'),
    )

    # Relationships
    driver = relationship("Driver")
    truck = relationship("Truck")


# ==========================
# PENDING REVIEWS (PD-01 — durable operator review queue)
# ==========================

pending_review_status_enum = SEnum('PENDING', 'APPROVED', 'REJECTED', name='pending_review_status')


class PendingReview(Base):
    __tablename__ = "pending_reviews"

    event_id = Column(UUID(as_uuid=True), primary_key=True)
    truck_id = Column(String(20), nullable=False)
    gate_id = Column(Integer, nullable=False)
    license_plate = Column(String(20), nullable=False)
    payload = Column(JSONB, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default='PENDING')
    created_at = Column(TIMESTAMP, server_default=func.now())
    resolved_at = Column(TIMESTAMP)
    resolved_by = Column(String(50))

    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED')", name='chk_pr_status'),
    )