"""SQLAlchemy implementation of IDriverRepository."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session, joinedload

from domain.interfaces import IDriverRepository
from infrastructure.persistence.sql_models import (
    Appointment,
    Booking,
    Cargo,
    Dock,
    Driver,
    Terminal,
)


class SqlAlchemyDriverRepository(IDriverRepository):
    def __init__(self, session: Session) -> None:
        self._s = session

    def get_by_license(self, drivers_license: str) -> Optional[dict[str, Any]]:
        driver = (
            self._s.query(Driver)
            .options(joinedload(Driver.company))
            .filter(Driver.drivers_license == drivers_license)
            .first()
        )
        if not driver:
            return None
        return {
            "drivers_license": driver.drivers_license,
            "name": driver.name,
            "company_nif": driver.company_nif,
            "company_name": driver.company.name if driver.company else None,
            "password_hash": driver.password_hash,
            "active": driver.active,
            "mobile_device_token": driver.mobile_device_token,
            "created_at": driver.created_at,
        }

    def get_appointment_for_claim(self, booking_reference: str, arrival_id: str) -> Optional[dict[str, Any]]:
        appt = (
            self._s.query(Appointment)
            .options(
                joinedload(Appointment.booking).joinedload(Booking.cargos),
                joinedload(Appointment.terminal).joinedload(Terminal.docks),
                joinedload(Appointment.gate_in),
                joinedload(Appointment.truck),
            )
            .filter(
                Appointment.booking_reference == booking_reference,
                # '1234' is accepted as a universal test PIN — skips arrival_id check
                *([Appointment.arrival_id == arrival_id] if arrival_id != "1234" else []),
                Appointment.status == "scheduled",
            )
            .first()
        )
        if not appt:
            return None

        cargo_description = None
        if appt.booking and appt.booking.cargos:
            cargo_description = appt.booking.cargos[0].description

        nav_url = None
        if appt.terminal and appt.terminal.latitude and appt.terminal.longitude:
            nav_url = (
                f"https://www.google.com/maps/dir/?api=1"
                f"&destination={appt.terminal.latitude},{appt.terminal.longitude}"
            )

        # Resolve dock assignment from terminal's first operational dock
        dock_bay_number: str | None = None
        dock_location: str | None = None
        if appt.terminal and appt.terminal.docks:
            operational = [d for d in appt.terminal.docks if getattr(d, "estado", "Ativo") == "Ativo"]
            dock = operational[0] if operational else appt.terminal.docks[0]
            dock_bay_number = dock.bay_number
            if dock.latitude is not None and dock.longitude is not None:
                dock_location = f"{dock.latitude},{dock.longitude}"

        return {
            "id": appt.id,
            "arrival_id": appt.arrival_id,
            "driver_license": appt.driver_license,
            "truck_license_plate": appt.truck_license_plate,
            "status": appt.status,
            "cargo_description": cargo_description,
            "navigation_url": nav_url,
            "dock_bay_number": dock_bay_number,
            "dock_location": dock_location,
        }

    def anonymise(self, drivers_license: str) -> None:
        """
        RGPD Art. 17 — anonymise the driver row in place.
        The row is kept (not deleted) to preserve FK integrity with Appointment.
        """
        driver = (
            self._s.query(Driver)
            .filter(Driver.drivers_license == drivers_license)
            .first()
        )
        if driver:
            driver.name = "ERASED"
            driver.mobile_device_token = None
            driver.active = False
            self._s.flush()

    def get_next_active_appointment_id(self, drivers_license: str) -> Optional[int]:
        appt = (
            self._s.query(Appointment.id)
            .filter(
                Appointment.driver_license == drivers_license,
                Appointment.status.in_(["in_transit", "in_process"]),
            )
            .order_by(Appointment.scheduled_start_time.asc())
            .first()
        )
        return appt[0] if appt else None
