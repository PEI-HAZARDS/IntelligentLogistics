"""
Abstract interfaces (ports) for the Data Module.

Business use-cases depend ONLY on these abstractions — never on
SQLAlchemy sessions or engines directly (Guardrail 6).

All side-effects that should propagate MUST go through the Outbox
(Guardrail 3), and every consumed event MUST pass through the Inbox
idempotency gate (Guardrail 1).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from domain.events import ConsumeContext, EventEnvelope


# =========================================================
# Domain repositories
# =========================================================


class IAppointmentStateRepository(ABC):
    """Repository for appointment aggregate state transitions (lock + write)."""

    @abstractmethod
    def get_for_update(self, appointment_id: int) -> Optional[dict[str, Any]]:
        """Return appointment dict with a ``SELECT … FOR UPDATE`` lock.

        Returns *None* if the appointment does not exist.
        """
        ...

    @abstractmethod
    def save_state_transition(
        self, appointment_id: int, new_state: str, metadata: dict[str, Any]
    ) -> None:
        ...


class IAppointmentRepository(ABC):
    """Repository for appointment lookup and optimistic-concurrency updates."""

    @abstractmethod
    def get_by_arrival_id(self, arrival_id: str) -> Optional[dict[str, Any]]:
        ...

    @abstractmethod
    def update_status(self, appointment_id: int, status: str, *, version: int) -> int:
        """Returns affected rows; 0 means optimistic concurrency conflict."""
        ...


# =========================================================
# Inbox / Outbox repositories
# =========================================================


class IInboxRepository(ABC):
    """Idempotent inbox gate (Guardrail 1, 4)."""

    @abstractmethod
    def try_insert_received(self, event: EventEnvelope, ctx: ConsumeContext) -> bool:
        """Insert a RECEIVED row. Return *False* on duplicate ``event_id``."""
        ...

    @abstractmethod
    def mark_processing(self, event_id: str) -> None:
        ...

    @abstractmethod
    def mark_processed(self, event_id: str) -> None:
        ...

    @abstractmethod
    def mark_failed(self, event_id: str, error: str, retryable: bool) -> None:
        ...


class IOutboxRepository(ABC):
    """Transactional outbox (Guardrail 3)."""

    @abstractmethod
    def append(self, event: EventEnvelope, *, topic: str, key: str) -> None:
        ...

    @abstractmethod
    def fetch_batch(self, batch_size: int) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def mark_published(self, outbox_id: str) -> None:
        ...

    @abstractmethod
    def mark_publish_failed(self, outbox_id: str, error: str) -> None:
        ...


# =========================================================
# Unit of Work
# =========================================================


class IAlertRepository(ABC):
    """Repository for alert writes within UoW."""

    @abstractmethod
    def add(
        self,
        *,
        visit_id: Optional[int],
        alert_type: str,
        description: str,
        image_url: Optional[str] = None,
        appointment_id: Optional[int] = None,
    ) -> dict[str, Any]:
        ...

    @abstractmethod
    def get_appointment_visit_id(self, appointment_id: int) -> Optional[int]:
        """Return the visit_id linked to an appointment, or None."""
        ...


class IDriverRepository(ABC):
    """Repository for driver reads/writes within UoW."""

    @abstractmethod
    def get_by_license(self, drivers_license: str) -> Optional[dict[str, Any]]:
        ...

    @abstractmethod
    def get_appointment_for_claim(self, arrival_id: str) -> Optional[dict[str, Any]]:
        """Return appointment dict with eager-loaded relations for claim flow."""
        ...

    @abstractmethod
    def get_next_active_appointment_id(self, drivers_license: str) -> Optional[int]:
        """Return the id of the next active appointment in the sequential queue."""
        ...


class IWorkerRepository(ABC):
    """Repository for worker reads/writes within UoW."""

    @abstractmethod
    def get_by_email_active(self, email: str) -> Optional[dict[str, Any]]:
        ...

    @abstractmethod
    def get_by_num_worker(self, num_worker: str) -> Optional[dict[str, Any]]:
        ...

    @abstractmethod
    def add_worker(
        self,
        *,
        num_worker: str,
        name: str,
        email: str,
        password_hash: str,
        phone: Optional[str] = None,
    ) -> dict[str, Any]:
        ...

    @abstractmethod
    def add_role(self, num_worker: str, role: str, access_level: Optional[str] = None) -> None:
        ...

    @abstractmethod
    def remove_role(self, num_worker: str, role: str) -> bool:
        ...

    @abstractmethod
    def update_fields(self, num_worker: str, **fields: Any) -> bool:
        ...

    @abstractmethod
    def email_exists(self, email: str, *, exclude_num_worker: Optional[str] = None) -> bool:
        ...

    @abstractmethod
    def num_worker_exists(self, num_worker: str) -> bool:
        ...

    @abstractmethod
    def has_role(self, num_worker: str, role: str) -> bool:
        ...


class IVisitRepository(ABC):
    """Repository for visit lifecycle within UoW."""

    @abstractmethod
    def create(
        self,
        appointment_id: int,
        shift_gate_id: int,
        shift_type: str,
        shift_date: Any,
        entry_time: Any = None,
    ) -> Optional[dict[str, Any]]:
        """Create a visit row. Returns None if appointment doesn't exist.
        Returns existing visit dict if one already exists (idempotent).
        """
        ...

    @abstractmethod
    def update_state(
        self,
        appointment_id: int,
        new_state: str,
        out_time: Any = None,
    ) -> Optional[dict[str, Any]]:
        """Update visit state. Returns None if visit not found."""
        ...

    @abstractmethod
    def get_by_appointment(self, appointment_id: int) -> Optional[dict[str, Any]]:
        ...


class IPendingReviewRepository(ABC):
    """Repository for the durable operator review queue (PD-01)."""

    @abstractmethod
    def create(
        self,
        *,
        event_id: str,
        truck_id: str,
        gate_id: int,
        license_plate: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        ...

    @abstractmethod
    def get_for_update(self, event_id: str) -> Optional[dict[str, Any]]:
        """Return row with SELECT … FOR UPDATE, or None."""
        ...

    @abstractmethod
    def update_status(
        self,
        event_id: str,
        status: str,
        resolved_by: Optional[str] = None,
    ) -> bool:
        """Set status + resolved_at + resolved_by. Returns False if not found."""
        ...


class IUnitOfWork(ABC):
    """
    Transactional boundary that groups Inbox + Outbox + domain
    repository mutations in a single PostgreSQL transaction.

    Guardrail 6 — all persistence access goes through this abstraction.
    """

    appointment_state: IAppointmentStateRepository
    appointments: IAppointmentRepository
    alerts: IAlertRepository
    drivers: IDriverRepository
    workers: IWorkerRepository
    visits: IVisitRepository
    inbox: IInboxRepository
    outbox: IOutboxRepository
    pending_reviews: IPendingReviewRepository

    @abstractmethod
    def __enter__(self) -> IUnitOfWork:
        ...

    @abstractmethod
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        ...

    @abstractmethod
    def commit(self) -> None:
        ...

    @abstractmethod
    def rollback(self) -> None:
        ...
