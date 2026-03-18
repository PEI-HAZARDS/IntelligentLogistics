"""
Domain event contracts for the Data Module EDA architecture.

These dataclasses define the canonical event envelope and Kafka consume
context used across inbox/outbox boundaries.  They are pure value objects
with no infrastructure dependency.

Guardrail 1 — every consumed Kafka event MUST include the fields below.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass(frozen=True)
class EventEnvelope:
    """Immutable envelope that wraps every domain event on Kafka."""

    event_id: str  # UUIDv7 — globally unique, idempotency key
    correlation_id: str
    causation_id: Optional[str]
    aggregate_type: str  # e.g. "appointment"
    aggregate_id: str  # e.g. appointment_id or arrival_id
    event_type: str  # e.g. "ContainerMoved"
    event_version: int  # schema version for backward compat
    occurred_at: datetime  # UTC ISO-8601
    producer: str
    partition_key: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class ConsumeContext:
    """Kafka record metadata captured at poll time."""

    topic: str
    partition: int
    offset: int
    key: Optional[str]
    headers: dict[str, str]
