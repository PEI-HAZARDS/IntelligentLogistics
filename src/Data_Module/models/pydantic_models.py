from datetime import date, time, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from enum import Enum


# ==========================
# ENUMS (aligned with sql_models.py)
# ==========================

class DeliveryStatusEnum(str, Enum):
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
    in_transit = "in_transit"
    canceled = "canceled"
    delayed = "delayed"
    completed = "completed"


class TypeAlertEnum(str, Enum):
    generic = "generic"
    safety = "safety"
    problem = "problem"
    operational = "operational"


class DirectionEnum(str, Enum):
    inbound = "inbound"
    outbound = "outbound"


class ShiftTypeEnum(str, Enum):
    MORNING = "06:00-14:00"
    AFTERNOON = "14:00-22:00"
    NIGHT = "22:00-06:00"


# ==========================
# TERMINAL
# ==========================

class TerminalBase(BaseModel):
    name: Optional[str] = None
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    hazmat_approved: bool = False


class TerminalCreate(TerminalBase):
    pass


class Terminal(TerminalBase):
    id: int

    model_config = {"from_attributes": True}


# ==========================
# DOCK (Composite PK: terminal_id + bay_number)
# ==========================

class DockBase(BaseModel):
    terminal_id: int
    bay_number: str
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    current_usage: OperationalStatusEnum = OperationalStatusEnum.operational


class DockCreate(DockBase):
    pass


class Dock(DockBase):
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
    mobile_device_token: Optional[str] = None


class DriverCreate(DriverBase):
    drivers_license: str
    password: str


class Driver(DriverBase):
    drivers_license: str
    active: bool = True
    created_at: Optional[datetime] = None
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
    num_worker: str
    password: str


class Worker(WorkerBase):
    num_worker: str
    active: bool = True
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ==========================
# MANAGER
# ==========================

class Manager(BaseModel):
    num_worker: str
    access_level: AccessLevelEnum = AccessLevelEnum.basic
    worker: Optional[Worker] = None

    model_config = {"from_attributes": True}


class ManagerInfo(BaseModel):
    num_worker: str
    name: str
    email: str
    access_level: str
    active: bool


# ==========================
# OPERATOR
# ==========================

class Operator(BaseModel):
    num_worker: str
    worker: Optional[Worker] = None

    model_config = {"from_attributes": True}


class OperatorInfo(BaseModel):
    num_worker: str
    name: str
    email: str
    active: bool


# ==========================
# SHIFT (Composite PK: gate_id + shift_type + date)
# ==========================

class ShiftBase(BaseModel):
    gate_id: int
    shift_type: ShiftTypeEnum
    date: date
    operator_num_worker: Optional[str] = None
    manager_num_worker: Optional[str] = None


class ShiftCreate(ShiftBase):
    pass


class Shift(ShiftBase):
    gate: Optional[Gate] = None
    operator: Optional[Operator] = None
    manager: Optional[Manager] = None

    model_config = {"from_attributes": True}


# ==========================
# BOOKING (PK: reference)
# ==========================

class BookingBase(BaseModel):
    direction: Optional[DirectionEnum] = None


class BookingCreate(BookingBase):
    reference: str


class Booking(BookingBase):
    reference: str
    created_at: Optional[datetime] = None
    cargos: List["Cargo"] = []

    model_config = {"from_attributes": True}


# ==========================
# CARGO
# ==========================

class CargoBase(BaseModel):
    booking_reference: str
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
    booking_reference: str
    driver_license: str
    truck_license_plate: str
    terminal_id: int
    gate_in_id: Optional[int] = None
    gate_out_id: Optional[int] = None
    scheduled_start_time: Optional[datetime] = None
    expected_duration: Optional[int] = None  # Duration in minutes
    status: AppointmentStatusEnum = AppointmentStatusEnum.in_transit
    notes: Optional[str] = None


class AppointmentCreate(AppointmentBase):
    arrival_id: Optional[str] = None


class Appointment(AppointmentBase):
    id: int
    arrival_id: Optional[str] = None  # May be NULL if trigger hasn't run
    booking: Optional[Booking] = None
    driver: Optional[Driver] = None
    truck: Optional[Truck] = None
    terminal: Optional[Terminal] = None
    gate_in: Optional[Gate] = None
    gate_out: Optional[Gate] = None

    model_config = {"from_attributes": True}


# ==========================
# VISIT (PK: appointment_id, FK to Shift via composite key)
# ==========================

class VisitBase(BaseModel):
    appointment_id: int
    shift_gate_id: int
    shift_type: ShiftTypeEnum
    shift_date: date
    entry_time: Optional[datetime] = None
    out_time: Optional[datetime] = None
    state: DeliveryStatusEnum = DeliveryStatusEnum.unloading


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
    visit_id: Optional[int] = None
    type: TypeAlertEnum = TypeAlertEnum.generic
    description: Optional[str] = None
    image_url: Optional[str] = None


class AlertCreate(AlertBase):
    pass


class Alert(AlertBase):
    id: int
    timestamp: datetime

    model_config = {"from_attributes": True}


# ==========================
# SHIFT ALERT HISTORY
# ==========================

class ShiftAlertHistoryBase(BaseModel):
    shift_gate_id: int
    shift_type: ShiftTypeEnum
    shift_date: date
    alert_id: int


class ShiftAlertHistoryCreate(ShiftAlertHistoryBase):
    pass


class ShiftAlertHistory(ShiftAlertHistoryBase):
    id: int
    last_update: Optional[datetime] = None
    shift: Optional[Shift] = None
    alert: Optional[Alert] = None

    model_config = {"from_attributes": True}


# ==========================
# AUTH MODELS
# ==========================

class WorkerLoginRequest(BaseModel):
    email: str
    password: str


class WorkerLoginResponse(BaseModel):
    token: str
    num_worker: str
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
    shift_gate_id: Optional[int] = None
    shift_type: Optional[ShiftTypeEnum] = None
    shift_date: Optional[date] = None
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
