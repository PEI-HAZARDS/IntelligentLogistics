"""
Domain event contracts for the Data Module EDA architecture.

These dataclasses define the canonical event envelope and Kafka consume
context used across inbox/outbox boundaries.  They are pure value objects
with no infrastructure dependency.

Guardrail 1 — every consumed Kafka event MUST include the fields below.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, NewType, Optional

# ---------------------------------------------------------------------------
# UUIDv7 support
# ---------------------------------------------------------------------------

UUIDv7Str = NewType("UUIDv7Str", str)

_UUIDV7_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def is_valid_uuidv7(value: str) -> bool:
    """Return True if *value* is a well-formed UUIDv7 string."""
    return bool(_UUIDV7_RE.match(value))


def new_event_id() -> UUIDv7Str:
    """Generate a time-ordered UUIDv7 string (RFC 9562 §5.7)."""
    ts_ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF  # 48-bit ms timestamp
    rand = int.from_bytes(os.urandom(10), "big")
    rand_a = rand >> 62 & 0x0FFF          # 12 random bits (bits 75-64)
    rand_b = rand & 0x3FFFFFFFFFFFFFFF    # 62 random bits (bits 61-0)
    value = (
        (ts_ms << 80)
        | (0x7 << 76)          # version = 7
        | (rand_a << 64)
        | (0b10 << 62)         # variant = 10
        | rand_b
    )
    h = f"{value:032x}"
    return UUIDv7Str(f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}")


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
