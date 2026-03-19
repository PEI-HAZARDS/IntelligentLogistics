"""SQLAlchemy implementation of IWorkerRepository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from domain.interfaces import IWorkerRepository
from infrastructure.persistence.sql_models import Manager, Operator, Worker


class SqlAlchemyWorkerRepository(IWorkerRepository):
    def __init__(self, session: Session) -> None:
        self._s = session

    # ── reads ────────────────────────────────────────────────

    def get_by_email_active(self, email: str) -> Optional[dict[str, Any]]:
        w = (
            self._s.query(Worker)
            .filter(Worker.email == email, Worker.active == True)  # noqa: E712
            .first()
        )
        return self._to_dict(w) if w else None

    def get_by_num_worker(self, num_worker: str) -> Optional[dict[str, Any]]:
        w = self._s.query(Worker).filter(Worker.num_worker == num_worker).first()
        return self._to_dict(w) if w else None

    def email_exists(self, email: str, *, exclude_num_worker: Optional[str] = None) -> bool:
        q = self._s.query(Worker.num_worker).filter(Worker.email == email)
        if exclude_num_worker:
            q = q.filter(Worker.num_worker != exclude_num_worker)
        return q.first() is not None

    def num_worker_exists(self, num_worker: str) -> bool:
        return (
            self._s.query(Worker.num_worker)
            .filter(Worker.num_worker == num_worker)
            .first()
            is not None
        )

    def has_role(self, num_worker: str, role: str) -> bool:
        if role == "manager":
            return self._s.query(Manager).filter(Manager.num_worker == num_worker).first() is not None
        if role == "operator":
            return self._s.query(Operator).filter(Operator.num_worker == num_worker).first() is not None
        return False

    # ── writes ───────────────────────────────────────────────

    def add_worker(
        self,
        *,
        num_worker: str,
        name: str,
        email: str,
        password_hash: str,
        phone: Optional[str] = None,
    ) -> dict[str, Any]:
        w = Worker(
            num_worker=num_worker,
            name=name,
            email=email,
            phone=phone,
            password_hash=password_hash,
            active=True,
            created_at=datetime.now(timezone.utc),
        )
        self._s.add(w)
        self._s.flush()
        return self._to_dict(w)

    def add_role(self, num_worker: str, role: str, access_level: Optional[str] = None) -> None:
        if role == "manager":
            self._s.add(Manager(num_worker=num_worker, access_level=access_level or "basic"))
        elif role == "operator":
            self._s.add(Operator(num_worker=num_worker))
        self._s.flush()

    def remove_role(self, num_worker: str, role: str) -> bool:
        if role == "operator":
            obj = self._s.query(Operator).filter(Operator.num_worker == num_worker).first()
        elif role == "manager":
            obj = self._s.query(Manager).filter(Manager.num_worker == num_worker).first()
        else:
            return False
        if obj:
            self._s.delete(obj)
            self._s.flush()
            return True
        return False

    def update_fields(self, num_worker: str, **fields: Any) -> bool:
        w = self._s.query(Worker).filter(Worker.num_worker == num_worker).first()
        if not w:
            return False
        for k, v in fields.items():
            setattr(w, k, v)
        self._s.flush()
        return True

    # ── helpers ──────────────────────────────────────────────

    @staticmethod
    def _to_dict(w: Worker) -> dict[str, Any]:
        role = "unknown"
        if w.manager:
            role = "manager"
        elif w.operator:
            role = "operator"
        return {
            "num_worker": w.num_worker,
            "name": w.name,
            "email": w.email,
            "phone": w.phone,
            "password_hash": w.password_hash,
            "active": w.active,
            "created_at": w.created_at,
            "role": role,
            "access_level": w.manager.access_level if w.manager else None,
        }
