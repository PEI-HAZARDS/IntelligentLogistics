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


class IContainerRepository(ABC):
    """Repository for container/appointment aggregate state transitions."""

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


class IUnitOfWork(ABC):
    """
    Transactional boundary that groups Inbox + Outbox + domain
    repository mutations in a single PostgreSQL transaction.

    Guardrail 6 — all persistence access goes through this abstraction.
    """

    containers: IContainerRepository
    appointments: IAppointmentRepository
    inbox: IInboxRepository
    outbox: IOutboxRepository

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
