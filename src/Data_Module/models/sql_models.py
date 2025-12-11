import enum
from datetime import datetime
from sqlalchemy import func
from sqlalchemy import Column, Integer, String, Date, Time, TIMESTAMP, DECIMAL, Boolean, ForeignKey, Text, Enum as SEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

# ==========================
# ENUMS
# ==========================

delivery_status_enum = SEnum('in_transit', 'delayed', 'unloading', 'completed', name='delivery_status')
physical_state_enum = SEnum('liquid', 'solid', 'gaseous', 'hybrid', name='physical_state')
access_level_enum = SEnum('admin', 'basic', name='access_level')
operational_status_enum = SEnum('maintenance', 'operational', 'closed', name='operational_status')
appointment_status_enum = SEnum('pending', 'approved', 'canceled', 'completed', name='appointment_status')


class ShiftType(enum.Enum):
    MORNING = "06:00-14:00"
    AFTERNOON = "14:00-22:00"
    NIGHT = "22:00-06:00"

    def get_hours(self):
        """Converts enum strings to time objects."""
        start_str, end_str = self.value.split("-")
        start_time = datetime.strptime(start_str, "%H:%M").time()
        end_time = datetime.strptime(end_str, "%H:%M").time()
        return start_time, end_time


# ==========================
# INFRASTRUCTURE: Terminal, Dock, Gate
# ==========================

class Terminal(Base):
    __tablename__ = "terminal"
    
    id = Column(Integer, primary_key=True)
    latitude = Column(DECIMAL(10, 8))
    longitude = Column(DECIMAL(11, 8))
    
    # Relationships
    docks = relationship("Dock", back_populates="terminal")
    appointments = relationship("Appointment", back_populates="terminal")


class Dock(Base):
    __tablename__ = "dock"
    
    id = Column(Integer, primary_key=True)
    terminal_id = Column(Integer, ForeignKey('terminal.id'), nullable=False)
    bay_number = Column(String(50))
    latitude = Column(DECIMAL(10, 8))
    longitude = Column(DECIMAL(11, 8))
    current_usage = Column(operational_status_enum, default='operational')
    
    # Relationships
    terminal = relationship("Terminal", back_populates="docks")


class Gate(Base):
    __tablename__ = "gate"
    
    id = Column(Integer, primary_key=True)
    label = Column(String(100), nullable=False)
    latitude = Column(DECIMAL(10, 8))
    longitude = Column(DECIMAL(11, 8))
    
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
    mobile_device_token = Column(Text)
    active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    
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
    
    nif = Column(String(20), primary_key=True)
    name = Column(String(200), nullable=False)
    phone = Column(String(50))
    email = Column(String(200), unique=True)
    password_hash = Column(Text)
    active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    
    # Relationships (disjoint specialization)
    manager = relationship("Manager", back_populates="worker", uselist=False)
    operator = relationship("Operator", back_populates="worker", uselist=False)


class Manager(Base):
    __tablename__ = "manager"
    
    nif = Column(String(20), ForeignKey('worker.nif'), primary_key=True)
    access_level = Column(access_level_enum, default='basic')
    
    # Relationships
    worker = relationship("Worker", back_populates="manager")
    shifts = relationship("Shift", back_populates="manager")


class Operator(Base):
    __tablename__ = "operator"
    
    nif = Column(String(20), ForeignKey('worker.nif'), primary_key=True)
    
    # Relationships
    worker = relationship("Worker", back_populates="operator")
    shifts = relationship("Shift", back_populates="operator")


class Shift(Base):
    __tablename__ = "shift"
    
    id = Column(Integer, primary_key=True)
    operator_nif = Column(String(20), ForeignKey('operator.nif'))
    manager_nif = Column(String(20), ForeignKey('manager.nif'))
    gate_id = Column(Integer, ForeignKey('gate.id'), nullable=False)
    
    shift_type = Column(SEnum(ShiftType), nullable=False)
    date = Column(Date, nullable=False)
    
    # Relationships
    operator = relationship("Operator", back_populates="shifts")
    manager = relationship("Manager", back_populates="shifts")
    gate = relationship("Gate", back_populates="shifts")
    visits = relationship("Visit", back_populates="shift")
    
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
    
    id = Column(Integer, primary_key=True)
    reference = Column(String(50), unique=True)
    direction = Column(String(20))  # 'inbound' or 'outbound'
    created_at = Column(TIMESTAMP, server_default=func.now())
    
    # Relationships
    cargos = relationship("Cargo", back_populates="booking")
    appointments = relationship("Appointment", back_populates="booking")


class Cargo(Base):
    __tablename__ = "cargo"
    
    id = Column(Integer, primary_key=True)
    booking_id = Column(Integer, ForeignKey('booking.id'), nullable=False)
    quantity = Column(DECIMAL(10, 2), nullable=False)
    state = Column(physical_state_enum, nullable=False)
    description = Column(Text)
    
    # Relationships
    booking = relationship("Booking", back_populates="cargos")
    alerts = relationship("Alert", back_populates="cargo")


# ==========================
# PLANNING: Appointment
# ==========================

class Appointment(Base):
    __tablename__ = "appointment"
    
    id = Column(Integer, primary_key=True)
    arrival_id = Column(String(50), unique=True, index=True)  # PIN e.g.: "PRT-0001"
    
    # Foreign Keys
    booking_id = Column(Integer, ForeignKey('booking.id'), nullable=False)
    driver_license = Column(String(50), ForeignKey('driver.drivers_license'), nullable=False)
    truck_license_plate = Column(String(20), ForeignKey('truck.license_plate'), nullable=False)
    terminal_id = Column(Integer, ForeignKey('terminal.id'), nullable=False)
    gate_in_id = Column(Integer, ForeignKey('gate.id'))
    gate_out_id = Column(Integer, ForeignKey('gate.id'))
    
    # Scheduling
    scheduled_start_time = Column(TIMESTAMP)
    expected_duration = Column(Integer)  # Expected duration in minutes
    
    # Status
    status = Column(appointment_status_enum, default='pending')
    notes = Column(Text)
    
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


# ==========================
# EXECUTION: Visit
# ==========================

class Visit(Base):
    __tablename__ = "visit"
    
    # PK = FK (1:1 relationship with Appointment)
    appointment_id = Column(Integer, ForeignKey('appointment.id'), primary_key=True)
    shift_id = Column(Integer, ForeignKey('shift.id'), nullable=False)
    
    # Actual times
    entry_time = Column(TIMESTAMP)
    out_time = Column(TIMESTAMP)
    
    # Status
    state = Column(delivery_status_enum, default='in_transit')
    
    # Relationships
    appointment = relationship("Appointment", back_populates="visit")
    shift = relationship("Shift", back_populates="visits")


# ==========================
# ALERTS
# ==========================

class Alert(Base):
    __tablename__ = "alert"
    
    id = Column(Integer, primary_key=True)
    cargo_id = Column(Integer, ForeignKey('cargo.id'))
    timestamp = Column(TIMESTAMP, server_default=func.now())
    
    image_url = Column(Text)
    type = Column(String(50), default='generic')
    severity = Column(Integer)
    description = Column(Text)
    
    # Relationships
    cargo = relationship("Cargo", back_populates="alerts")
