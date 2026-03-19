"""
Command handlers for worker mutations.
Writes to PostgreSQL via UoW + Outbox (Guardrails 2, 3, 6).
Write-through to MongoDB workers_read after commit.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from domain.events import EventEnvelope
from domain.interfaces import IUnitOfWork
from utils.hashing_pass import hash_password, verify_password

logger = logging.getLogger(__name__)


def _write_through_worker(worker_dict: dict[str, Any]) -> None:
    """Best-effort write-through to MongoDB (outside SQL transaction)."""
    try:
        from infrastructure.persistence.mongo import workers_read_collection

        doc = {k: v for k, v in worker_dict.items() if k != "password_hash"}
        if doc.get("created_at") and not isinstance(doc["created_at"], str):
            doc["created_at"] = doc["created_at"].isoformat()
        workers_read_collection.update_one(
            {"num_worker": doc["num_worker"]},
            {"$set": doc},
            upsert=True,
        )
    except Exception as exc:
        logger.warning("workers_read write-through failed: %s", exc)


def _append_outbox(uow: IUnitOfWork, worker_dict: dict[str, Any], event_type: str) -> None:
    payload = {k: v for k, v in worker_dict.items() if k != "password_hash"}
    envelope = EventEnvelope(
        event_id=str(uuid4()),
        correlation_id=str(uuid4()),
        causation_id=None,
        aggregate_type="worker",
        aggregate_id=worker_dict["num_worker"],
        event_type=event_type,
        event_version=1,
        occurred_at=datetime.now(timezone.utc),
        producer="data-module",
        partition_key=worker_dict["num_worker"],
        payload=payload,
    )
    uow.outbox.append(envelope, topic="worker.changed", key=envelope.partition_key)


# ── Auth ─────────────────────────────────────────────────────────


def authenticate_worker(
    uow_factory,
    *,
    email: str,
    password: str,
) -> Optional[dict[str, Any]]:
    """Returns worker dict or None."""
    with uow_factory() as uow:
        w = uow.workers.get_by_email_active(email)
        if not w:
            return None
        if not verify_password(password, w["password_hash"]):
            return None
        # Generate simple token (MVP)
        w["token"] = secrets.token_hex(32)
        return w


# ── Admin writes ─────────────────────────────────────────────────


def create_worker(
    uow_factory,
    *,
    num_worker: str,
    name: str,
    email: str,
    password: str,
    role: str,
    access_level: Optional[str] = None,
    phone: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    with uow_factory() as uow:
        if uow.workers.email_exists(email):
            return None
        if uow.workers.num_worker_exists(num_worker):
            return None

        w = uow.workers.add_worker(
            num_worker=num_worker,
            name=name,
            email=email,
            password_hash=hash_password(password),
            phone=phone,
        )
        uow.workers.add_role(num_worker, role, access_level)
        w["role"] = role
        _append_outbox(uow, w, "WorkerCreated")
        uow.commit()

    _write_through_worker(w)
    return w


def update_worker_password(
    uow_factory,
    *,
    num_worker: str,
    current_password: str,
    new_password: str,
) -> tuple[bool, str]:
    """Returns (success, error_message)."""
    with uow_factory() as uow:
        w = uow.workers.get_by_num_worker(num_worker)
        if not w:
            return False, "Worker not found"
        if not verify_password(current_password, w["password_hash"]):
            return False, "Current password incorrect"
        uow.workers.update_fields(num_worker, password_hash=hash_password(new_password))
        _append_outbox(uow, w, "WorkerPasswordChanged")
        uow.commit()
    return True, ""


def update_worker_email(
    uow_factory,
    *,
    num_worker: str,
    new_email: str,
) -> tuple[bool, str]:
    with uow_factory() as uow:
        if uow.workers.email_exists(new_email, exclude_num_worker=num_worker):
            return False, "Email already in use"
        ok = uow.workers.update_fields(num_worker, email=new_email)
        if not ok:
            return False, "Worker not found"
        w = uow.workers.get_by_num_worker(num_worker)
        _append_outbox(uow, w, "WorkerEmailChanged")
        uow.commit()

    if w:
        _write_through_worker(w)
    return True, ""


def deactivate_worker(
    uow_factory,
    *,
    num_worker: str,
) -> Optional[dict[str, Any]]:
    with uow_factory() as uow:
        w = uow.workers.get_by_num_worker(num_worker)
        if not w:
            return None
        uow.workers.update_fields(num_worker, active=False)
        w["active"] = False
        _append_outbox(uow, w, "WorkerDeactivated")
        uow.commit()

    _write_through_worker(w)
    return w


def promote_to_manager(
    uow_factory,
    *,
    num_worker: str,
    access_level: str = "basic",
) -> Optional[dict[str, Any]]:
    with uow_factory() as uow:
        w = uow.workers.get_by_num_worker(num_worker)
        if not w:
            return None
        if uow.workers.has_role(num_worker, "manager"):
            return None
        uow.workers.remove_role(num_worker, "operator")
        uow.workers.add_role(num_worker, "manager", access_level)
        w["role"] = "manager"
        w["access_level"] = access_level
        _append_outbox(uow, w, "WorkerPromoted")
        uow.commit()

    _write_through_worker(w)
    return w
