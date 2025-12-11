from app.schemas.base import BaseSchema, PaginationParams, PaginatedResponse, MessageResponse
from app.schemas.truck import TruckCreate, TruckUpdate, TruckResponse
from app.schemas.driver import DriverCreate, DriverUpdate, DriverResponse
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentUpdate,
    AppointmentConfirm,
    AppointmentResponse,
    AppointmentWindowCheck,
)
from app.schemas.gate import GateResponse, GateCheckIn, GateCheckOut
from app.schemas.visit import VisitEventCreate, VisitEventResponse, VisitResponse, VisitUpdateStage
from app.schemas.ai_recognition import (
    AIEventCreate,
    AIEventResponse,
    AICorrectionCreate,
    AICorrectionResponse,
)
from app.schemas.worker import (
    WorkerCreate,
    WorkerUpdate,
    WorkerResponse,
    LoginRequest,
    TokenResponse,
    CurrentUser,
)
from app.schemas.telemetry import ResourceMetricCreate, ResourceMetricResponse
from app.schemas.decision import (
    QueryArrivalsRequest,
    QueryArrivalsResponse,
    AppointmentCandidate,
    DecisionCreate,
    DecisionResponse,
    ManualReviewRequest,
    DecisionListFilters,
)

__all__ = [
    # Base
    "BaseSchema",
    "PaginationParams",
    "PaginatedResponse",
    "MessageResponse",
    # Truck
    "TruckCreate",
    "TruckUpdate",
    "TruckResponse",
    # Driver
    "DriverCreate",
    "DriverUpdate",
    "DriverResponse",
    # Appointment
    "AppointmentCreate",
    "AppointmentUpdate",
    "AppointmentConfirm",
    "AppointmentResponse",
    "AppointmentWindowCheck",
    # Gate
    "GateResponse",
    "GateCheckIn",
    "GateCheckOut",
    # Visit
    "VisitEventCreate",
    "VisitEventResponse",
    "VisitResponse",
    "VisitUpdateStage",
    # AI
    "AIEventCreate",
    "AIEventResponse",
    "AICorrectionCreate",
    "AICorrectionResponse",
    # Worker
    "WorkerCreate",
    "WorkerUpdate",
    "WorkerResponse",
    "LoginRequest",
    "TokenResponse",
    "CurrentUser",
    # Telemetry
    "ResourceMetricCreate",
    "ResourceMetricResponse",
    # Decision
    "QueryArrivalsRequest",
    "QueryArrivalsResponse",
    "AppointmentCandidate",
    "DecisionCreate",
    "DecisionResponse",
    "ManualReviewRequest",
    "DecisionListFilters",
]
