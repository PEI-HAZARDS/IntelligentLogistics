"""
SQLAlchemy ORM models for the Inbox and Outbox tables.

These tables are created alongside the existing domain tables using the
same ``Base`` declarative base so that ``Base.metadata.create_all()``
picks them up automatically in development mode.

Guardrail 1 — ``InboxEvent.event_id`` has a UNIQUE constraint for
idempotent deduplication.
Guardrail 3 — ``OutboxEvent`` stores side-effects atomically with the
command transaction.
Guardrail 4 — ``InboxEvent.status`` follows the state machine
RECEIVED → PROCESSING → PROCESSED | FAILED | DEAD_LETTER.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

from infrastructure.persistence.sql_models import Base


# =========================================================
# Inbox
# =========================================================


class InboxEvent(Base):  # type: ignore[misc]
    """
    Idempotent inbox for consumed Kafka events.

    ``event_id`` is globally unique (UUIDv7) and enforced via UNIQUE
    constraint — a duplicate INSERT will raise ``IntegrityError``.
    """

    __tablename__ = "inbox_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(64), unique=True, nullable=False, index=True)

    # Kafka record metadata
    topic = Column(String(255), nullable=False)
    partition = Column(Integer, nullable=False)
    offset = Column(Integer, nullable=False)

    # Envelope metadata
    aggregate_type = Column(String(128), nullable=False)
    aggregate_id = Column(String(128), nullable=False)
    event_type = Column(String(128), nullable=False)
    event_version = Column(Integer, nullable=False)

    # State machine: RECEIVED → PROCESSING → PROCESSED | FAILED | DEAD_LETTER
    status = Column(
        String(20),
        nullable=False,
        default="RECEIVED",
        server_default="RECEIVED",
    )
    retry_count = Column(Integer, nullable=False, default=0, server_default="0")
    last_error = Column(Text, nullable=True)

    payload_hash = Column(String(64), nullable=True)
    payload = Column(JSONB, nullable=True)

    # Timestamps
    received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)


# =========================================================
# Outbox
# =========================================================


class OutboxEvent(Base):  # type: ignore[misc]
    """
    Transactional outbox — domain side-effects persisted in the same
    PostgreSQL transaction as the aggregate mutation.

    A relay worker polls ``status = 'PENDING'`` rows and publishes them
    to Kafka, marking them ``PUBLISHED`` only after broker ACK.
    """

    __tablename__ = "outbox_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(64), unique=True, nullable=False, index=True)

    # Routing
    topic = Column(String(255), nullable=False)
    partition_key = Column(String(255), nullable=False)

    # Envelope
    aggregate_type = Column(String(128), nullable=False)
    aggregate_id = Column(String(128), nullable=False)
    event_type = Column(String(128), nullable=False)
    event_version = Column(Integer, nullable=False)

    # Payload
    payload = Column(JSONB, nullable=False)

    # State machine: PENDING → PUBLISHED | FAILED | DEAD_LETTER
    status = Column(
        String(20),
        nullable=False,
        default="PENDING",
        server_default="PENDING",
    )
    retry_count = Column(Integer, nullable=False, default=0, server_default="0")
    last_error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
