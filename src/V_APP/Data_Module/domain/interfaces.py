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
    Transactional boundary that groups Inbox + Outbox (and future
    domain repository) mutations in a single PostgreSQL transaction.

    Guardrail 6 — all persistence access goes through this abstraction.
    """

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
