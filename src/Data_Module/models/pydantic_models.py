from datetime import date, time, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from enum import Enum


# ==========================
# ENUMS
# ==========================

class DeliveryStatusEnum(str, Enum):
    in_transit = "in_transit"
    delayed = "delayed"
    unloading = "unloading"
    completed = "completed"


class PhysicalStateEnum(str, Enum):
    liquid = "liquid"
    solid = "solid"
    gaseous = "gaseous"
    hybrid = "hybrid"


class AccessLevelEnum(str, Enum):
    admin = "admin"
    basic = "basic"


class OperationalStatusEnum(str, Enum):
    maintenance = "maintenance"
    operational = "operational"
    closed = "closed"


class AppointmentStatusEnum(str, Enum):
    pending = "pending"
    approved = "approved"
    canceled = "canceled"
    completed = "completed"


# ==========================
# TERMINAL
# ==========================

class TerminalBase(BaseModel):
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None


class TerminalCreate(TerminalBase):
    pass


class Terminal(TerminalBase):
    id: int

    model_config = {"from_attributes": True}


# ==========================
# DOCK
# ==========================

class DockBase(BaseModel):
    terminal_id: int
    bay_number: Optional[str] = None
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    current_usage: OperationalStatusEnum = OperationalStatusEnum.operational


class DockCreate(DockBase):
    pass


class Dock(DockBase):
    id: int
    terminal: Optional[Terminal] = None

    model_config = {"from_attributes": True}


# ==========================
# GATE
# ==========================

class GateBase(BaseModel):
    label: str
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None


class GateCreate(GateBase):
    pass


class Gate(GateBase):
    id: int

    model_config = {"from_attributes": True}


# ==========================
# COMPANY
# ==========================

class CompanyBase(BaseModel):
    name: str
    contact: Optional[str] = None


class CompanyCreate(CompanyBase):
    nif: str


class Company(CompanyBase):
    nif: str

    model_config = {"from_attributes": True}


# ==========================
# DRIVER
# ==========================

class DriverBase(BaseModel):
    name: str
    company_nif: Optional[str] = None


class DriverCreate(DriverBase):
    drivers_license: str
    password: str


class Driver(DriverBase):
    drivers_license: str
    active: bool = True
    company: Optional[Company] = None

    model_config = {"from_attributes": True}


# ==========================
# TRUCK
# ==========================

class TruckBase(BaseModel):
    company_nif: Optional[str] = None
    brand: Optional[str] = None


class TruckCreate(TruckBase):
    license_plate: str


class Truck(TruckBase):
    license_plate: str
    company: Optional[Company] = None

    model_config = {"from_attributes": True}


# ==========================
# WORKER
# ==========================

class WorkerBase(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None


class WorkerCreate(WorkerBase):
    nif: str
    password: str


class Worker(WorkerBase):
    nif: str
    active: bool = True
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ==========================
# MANAGER
# ==========================

class Manager(BaseModel):
    nif: str
    access_level: AccessLevelEnum = AccessLevelEnum.basic
    worker: Optional[Worker] = None

    model_config = {"from_attributes": True}


class ManagerInfo(BaseModel):
    nif: str
    name: str
    email: str
    access_level: str
    active: bool


# ==========================
# OPERATOR
# ==========================

class Operator(BaseModel):
    nif: str
    worker: Optional[Worker] = None

    model_config = {"from_attributes": True}


class OperatorInfo(BaseModel):
    nif: str
    name: str
    email: str
    active: bool


# ==========================
# SHIFT
# ==========================

class ShiftBase(BaseModel):
    operator_nif: Optional[str] = None
    manager_nif: Optional[str] = None
    gate_id: int
    date: date


class ShiftCreate(ShiftBase):
    shift_type: str  # "MORNING", "AFTERNOON", "NIGHT"


class Shift(ShiftBase):
    id: int
    shift_type: str
    gate: Optional[Gate] = None

    model_config = {"from_attributes": True}


# ==========================
# BOOKING
# ==========================

class BookingBase(BaseModel):
    reference: Optional[str] = None
    direction: Optional[str] = None  # 'inbound' or 'outbound'


class BookingCreate(BookingBase):
    pass


class Booking(BookingBase):
    id: int
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ==========================
# CARGO
# ==========================

class CargoBase(BaseModel):
    booking_id: int
    quantity: Decimal
    state: PhysicalStateEnum
    description: Optional[str] = None


class CargoCreate(CargoBase):
    pass


class Cargo(CargoBase):
    id: int
    booking: Optional[Booking] = None

    model_config = {"from_attributes": True}


# ==========================
# APPOINTMENT
# ==========================

class AppointmentBase(BaseModel):
    booking_id: int
    driver_license: str
    truck_license_plate: str
    terminal_id: int
    gate_in_id: Optional[int] = None
    gate_out_id: Optional[int] = None
    scheduled_start_time: Optional[datetime] = None
    expected_duration: Optional[int] = None  # Duration in minutes
    status: AppointmentStatusEnum = AppointmentStatusEnum.pending
    notes: Optional[str] = None


class AppointmentCreate(AppointmentBase):
    arrival_id: Optional[str] = None


class Appointment(AppointmentBase):
    id: int
    arrival_id: str
    booking: Optional[Booking] = None
    driver: Optional[Driver] = None
    truck: Optional[Truck] = None
    terminal: Optional[Terminal] = None
    gate_in: Optional[Gate] = None
    gate_out: Optional[Gate] = None

    model_config = {"from_attributes": True}


# ==========================
# VISIT
# ==========================

class VisitBase(BaseModel):
    appointment_id: int
    shift_id: int
    entry_time: Optional[datetime] = None
    out_time: Optional[datetime] = None
    state: DeliveryStatusEnum = DeliveryStatusEnum.in_transit


class VisitCreate(VisitBase):
    pass


class Visit(VisitBase):
    appointment: Optional[Appointment] = None
    shift: Optional[Shift] = None

    model_config = {"from_attributes": True}


# ==========================
# ALERT
# ==========================

class AlertBase(BaseModel):
    cargo_id: Optional[int] = None
    type: str = "generic"
    severity: Optional[int] = None
    description: Optional[str] = None
    image_url: Optional[str] = None


class AlertCreate(AlertBase):
    pass


class Alert(AlertBase):
    id: int
    timestamp: datetime

    model_config = {"from_attributes": True}


# ==========================
# AUTH MODELS
# ==========================

class WorkerLoginRequest(BaseModel):
    email: str
    password: str


class WorkerLoginResponse(BaseModel):
    token: str
    nif: str
    name: str
    email: str
    active: bool


class DriverLoginRequest(BaseModel):
    drivers_license: str
    password: str


class DriverLoginResponse(BaseModel):
    token: str
    drivers_license: str
    name: str
    company_nif: Optional[str] = None
    company_name: Optional[str] = None


# ==========================
# VISIT/APPOINTMENT OPERATIONS
# ==========================

class ClaimAppointmentRequest(BaseModel):
    arrival_id: str


class ClaimAppointmentResponse(BaseModel):
    appointment_id: int
    dock_bay_number: Optional[str] = None
    dock_location: Optional[str] = None
    license_plate: str
    cargo_description: Optional[str] = None
    navigation_url: Optional[str] = None


class AppointmentStatusUpdate(BaseModel):
    status: AppointmentStatusEnum
    notes: Optional[str] = None


class VisitStatusUpdate(BaseModel):
    state: DeliveryStatusEnum
    entry_time: Optional[datetime] = None
    out_time: Optional[datetime] = None
    notes: Optional[str] = None


# ==========================
# DECISION ENGINE MODELS
# ==========================

class AlertPayload(BaseModel):
    type: str
    severity: int
    description: str


class DecisionCandidate(BaseModel):
    appointment_id: int
    license_plate: str
    gate_in_id: Optional[int] = None
    terminal_id: Optional[int] = None
    shift_id: Optional[int] = None
    scheduled_time: Optional[str] = None
    status: str
    cargo_description: Optional[str] = None


class DecisionRequest(BaseModel):
    license_plate: str
    gate_id: int
    timestamp: datetime
    confidence: Optional[float] = None


class DecisionResponse(BaseModel):
    found: bool
    candidates: List[DecisionCandidate]
    message: Optional[str] = None


class DecisionProcessRequest(BaseModel):
    license_plate: str
    gate_id: int
    appointment_id: int
    decision: str
    state: DeliveryStatusEnum
    notes: Optional[str] = None
    alerts: Optional[List[AlertPayload]] = None


class EventResponse(BaseModel):
    id: Optional[str] = None
    type: str
    timestamp: Optional[datetime] = None
    gate_id: Optional[int] = None
    license_plate: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
