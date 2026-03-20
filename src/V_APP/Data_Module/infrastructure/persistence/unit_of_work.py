"""
SQLAlchemy Unit of Work — manages a single PostgreSQL transaction
that groups Inbox + Outbox (and future domain repository) writes.

Guardrail 6 — business use-cases never touch sessions directly; they
call ``uow.commit()`` / ``uow.rollback()`` through the IUnitOfWork
abstraction.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from domain.interfaces import (
    IAlertRepository,
    IAppointmentRepository,
    IAppointmentStateRepository,
    IDriverRepository,
    IInboxRepository,
    IOutboxRepository,
    IUnitOfWork,
    IWorkerRepository,
)
from infrastructure.persistence.alert_repository import SqlAlchemyAlertRepository
from infrastructure.persistence.appointment_repository import SqlAlchemyAppointmentRepository
from infrastructure.persistence.appointment_state_repository import SqlAlchemyAppointmentStateRepository
from infrastructure.persistence.driver_repository import SqlAlchemyDriverRepository
from infrastructure.persistence.inbox_repository import SqlAlchemyInboxRepository
from infrastructure.persistence.outbox_repository import SqlAlchemyOutboxRepository
from infrastructure.persistence.worker_repository import SqlAlchemyWorkerRepository


class SqlAlchemyUnitOfWork(IUnitOfWork):
    """
    Concrete UoW backed by a SQLAlchemy ``Session``.

    Usage::

        with SqlAlchemyUnitOfWork(session_factory) as uow:
            if uow.inbox.try_insert_received(event, ctx):
                uow.inbox.mark_processing(event.event_id)
                # … business logic …
                uow.outbox.append(derived_event, topic=…, key=…)
                uow.inbox.mark_processed(event.event_id)
                uow.commit()
    """

    appointment_state: IAppointmentStateRepository
    appointments: IAppointmentRepository
    alerts: IAlertRepository
    drivers: IDriverRepository
    workers: IWorkerRepository
    inbox: IInboxRepository
    outbox: IOutboxRepository

    def __init__(self, session_factory: sessionmaker) -> None:  # type: ignore[type-arg]
        self._session_factory = session_factory
        self._session: Session | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        self._session = self._session_factory()
        self.appointment_state = SqlAlchemyAppointmentStateRepository(self._session)
        self.appointments = SqlAlchemyAppointmentRepository(self._session)
        self.alerts = SqlAlchemyAlertRepository(self._session)
        self.drivers = SqlAlchemyDriverRepository(self._session)
        self.workers = SqlAlchemyWorkerRepository(self._session)
        self.inbox = SqlAlchemyInboxRepository(self._session)
        self.outbox = SqlAlchemyOutboxRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        if exc_type is not None:
            self.rollback()
        if self._session is not None:
            self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Transaction control
    # ------------------------------------------------------------------

    def commit(self) -> None:
        assert self._session is not None, "UnitOfWork not entered"
        self._session.commit()

    def rollback(self) -> None:
        if self._session is not None:
            self._session.rollback()
