"""
Command handlers for driver mutations.
Writes to PostgreSQL via UoW + Outbox (Guardrails 2, 3, 6).
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

from domain.interfaces import IUnitOfWork
from utils.hashing_pass import verify_password

logger = logging.getLogger(__name__)


def authenticate_driver(
    uow_factory,
    *,
    drivers_license: str,
    password: str,
) -> Optional[dict[str, Any]]:
    """
    Validates driver credentials.
    Returns driver dict (with company info) or None.
    """
    with uow_factory() as uow:
        driver = uow.drivers.get_by_license(drivers_license)
        if not driver:
            return None
        if not driver["active"]:
            return None
        if not verify_password(password, driver["password_hash"]):
            return None
        return driver


def claim_appointment_by_pin(
    uow_factory,
    *,
    booking_reference: str,
    arrival_id: str,
    driver_sub: str,
    debug_mode: bool = False,
) -> Tuple[Optional[dict[str, Any]], str]:
    """
    Driver selects a booking in the UI and confirms with PIN (arrival_id).
    booking_reference identifies which scheduled appointment to claim;
    arrival_id (PIN) is the confirmation code.
    Returns (appointment_dict, error_message).
    """
    with uow_factory() as uow:
        appt = uow.drivers.get_appointment_for_claim(booking_reference, arrival_id)
        if not appt:
            return None, "Invalid PIN or appointment not found"

        if not debug_mode:
            next_id = uow.drivers.get_next_active_appointment_id(driver_sub)
            if next_id and next_id != appt["id"]:
                return None, "Must complete earlier delivery first"

        return appt, ""
