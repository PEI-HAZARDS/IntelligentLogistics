from app.repositories.base import BaseRepository
from app.repositories.truck import TruckRepository
from app.repositories.appointment import AppointmentRepository
from app.repositories.gate_visit import GateVisitRepository
from app.repositories.ai_recognition import AIRecognitionRepository
from app.repositories.worker import WorkerRepository

__all__ = [
    "BaseRepository",
    "TruckRepository",
    "AppointmentRepository",
    "GateVisitRepository",
    "AIRecognitionRepository",
    "WorkerRepository",
]
