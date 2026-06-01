"""
Unit tests for the driver claim write-path (persisting ownership).

Covers the fix where `claim_appointment_by_pin` must persist the assignment
(driver_license + current_appointment_id) and commit, instead of only reading:

  (a) claiming a free booking assigns the driver and commits;
  (b) re-claiming a booking already owned by the same driver is idempotent
      (no PIN required from the Delivery tab);
  (c) a booking grabbed by another driver between read and assign is rejected
      explicitly (no silent double-claim), and is NOT committed.

All tests use in-memory fakes — no running services required.

Run:
    PYTHONPATH=. pytest tests/test_driver_claim_uow.py -v
"""

from application.use_cases.driver_handlers import claim_appointment_by_pin


class _StatefulDrivers:
    """Mimics SqlAlchemyDriverRepository claim semantics over an in-memory appointment."""

    def __init__(self, appt: dict):
        self._appt = appt
        self.current_appointment_id = None  # stand-in for Driver.current_appointment_id

    def get_appointment_for_claim(self, booking_reference, arrival_id, drivers_license):
        a = self._appt
        if a["booking_reference"] != booking_reference or a["status"] != "scheduled":
            return None
        owned = a["driver_license"] == drivers_license
        unclaimed = a["driver_license"] is None
        pin_ok = arrival_id == "1234" or a.get("arrival_id") == arrival_id
        if owned or (unclaimed and pin_ok):
            return dict(a)
        return None

    def assign_driver_to_appointment(self, appointment_id, drivers_license):
        a = self._appt
        if a["driver_license"] is None:
            a["driver_license"] = drivers_license
            a["version"] = a.get("version", 1) + 1
            self.current_appointment_id = appointment_id
            return True
        if a["driver_license"] == drivers_license:
            return True
        return False

    def get_next_active_appointment_id(self, drivers_license):
        return None


class _RaceDrivers:
    """get() sees an unclaimed appt, but assign() loses the race (owned by another)."""

    def get_appointment_for_claim(self, booking_reference, arrival_id, drivers_license):
        return {"id": 7, "booking_reference": booking_reference, "arrival_id": arrival_id}

    def assign_driver_to_appointment(self, appointment_id, drivers_license):
        return False

    def get_next_active_appointment_id(self, drivers_license):
        return None


class _FakeUoW:
    def __init__(self, drivers):
        self.drivers = drivers
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def commit(self):
        self.committed = True


def _factory(uow):
    return lambda: uow


def test_claim_free_booking_persists_and_commits():
    appt = {"id": 10, "booking_reference": "BR-10", "arrival_id": "PIN-10",
            "driver_license": None, "status": "scheduled"}
    uow = _FakeUoW(_StatefulDrivers(appt))

    result, err = claim_appointment_by_pin(
        _factory(uow), driver_sub="LIC-A", booking_reference="BR-10", arrival_id="PIN-10",
    )

    assert err == ""
    assert result is not None and result["id"] == 10
    assert appt["driver_license"] == "LIC-A"            # ownership persisted
    assert uow.drivers.current_appointment_id == 10      # driver pointer set
    assert uow.committed is True


def test_owned_reclaim_without_pin_is_idempotent():
    appt = {"id": 20, "booking_reference": "BR-20", "arrival_id": "PIN-20",
            "driver_license": "LIC-B", "status": "scheduled"}
    uow = _FakeUoW(_StatefulDrivers(appt))

    # Delivery-tab "Start Trip" sends an empty PIN for an already-owned booking.
    result, err = claim_appointment_by_pin(
        _factory(uow), driver_sub="LIC-B", booking_reference="BR-20", arrival_id="",
    )

    assert err == ""
    assert result is not None and result["id"] == 20
    assert appt["driver_license"] == "LIC-B"
    assert uow.committed is True


def test_claim_lost_race_is_rejected_and_not_committed():
    uow = _FakeUoW(_RaceDrivers())

    result, err = claim_appointment_by_pin(
        _factory(uow), driver_sub="LIC-C", booking_reference="BR-7", arrival_id="PIN-7",
    )

    assert result is None
    assert "another driver" in err.lower()
    assert uow.committed is False
