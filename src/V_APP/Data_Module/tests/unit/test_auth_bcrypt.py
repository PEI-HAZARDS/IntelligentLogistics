"""
Unit tests for auth behaviour (BR-39, BR-40, BR-41).

BR-39 — Worker auth: email + bcrypt verify; wrong password returns None.
BR-40 — Driver auth: licence + password; claim PIN == arrival_id;
         driver must own the appointment.
BR-41 — DEBUG_MODE=true bypasses sequential-delivery check.

All tests use fake UoWs — no running services required.

Run:
    PYTHONPATH=. pytest tests/unit/test_auth_bcrypt.py -v
"""

import pytest
from utils.hashing_pass import hash_password, verify_password
from application.use_cases.worker_handlers import authenticate_worker
from application.use_cases.driver_handlers import authenticate_driver, claim_appointment_by_pin


# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------

class _FakeDrivers:
    def __init__(self, driver=None, next_active_id=None):
        self._driver = driver
        self._next_active_id = next_active_id

    def get_by_license(self, lic):
        if self._driver and self._driver.get("drivers_license") == lic:
            return self._driver
        return None

    def get_appointment_for_claim(self, booking_reference, arrival_id):
        appt = (self._driver or {}).get("_appointment") or {}
        if appt.get("arrival_id") == arrival_id and appt.get("booking_reference", booking_reference) == booking_reference:
            return appt or None
        return None

    def get_next_active_appointment_id(self, lic):
        return self._next_active_id


class _FakeWorkers:
    def __init__(self, worker=None):
        self._worker = worker

    def get_by_email_active(self, email):
        if self._worker and self._worker.get("email") == email:
            return dict(self._worker)
        return None


class _FakeOutbox:
    def append(self, event, *, topic, key):
        pass


class _FakeUoW:
    def __init__(self, *, driver=None, next_active_id=None, worker=None):
        self.drivers = _FakeDrivers(driver, next_active_id)
        self.workers = _FakeWorkers(worker)
        self.outbox = _FakeOutbox()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def commit(self):
        pass


def _uow_factory(**kwargs):
    uow = _FakeUoW(**kwargs)
    return lambda: uow


# ---------------------------------------------------------------------------
# Bcrypt correctness
# ---------------------------------------------------------------------------

def test_hash_and_verify_roundtrip():
    """hash_password + verify_password must form a valid bcrypt roundtrip."""
    plain = "S3cur3P@ss!"
    hashed = hash_password(plain)
    assert hashed != plain, "Hash must not be the plain text"
    assert verify_password(plain, hashed) is True


def test_wrong_password_not_verified():
    """verify_password returns False for an incorrect password."""
    hashed = hash_password("correct_password")
    assert verify_password("wrong_password", hashed) is False


def test_empty_password_not_verified():
    """verify_password returns False for an empty string against a real hash."""
    hashed = hash_password("any_password")
    assert verify_password("", hashed) is False


def test_invalid_hash_returns_false():
    """verify_password returns False (not raises) for a malformed hash."""
    assert verify_password("password", "not-a-valid-bcrypt-hash") is False


# ---------------------------------------------------------------------------
# BR-39 — Worker auth
# ---------------------------------------------------------------------------

def test_worker_auth_correct_credentials_returns_worker():
    """BR-39: correct email + password returns the worker dict."""
    pw = "worker_pass"
    worker = {
        "num_worker": "W001",
        "email": "alice@port.pt",
        "password_hash": hash_password(pw),
        "active": True,
    }
    result = authenticate_worker(_uow_factory(worker=worker), email="alice@port.pt", password=pw)
    assert result is not None
    assert result["num_worker"] == "W001"
    assert "token" in result  # auth token generated


def test_worker_auth_wrong_password_returns_none():
    """BR-39: wrong password must return None."""
    worker = {
        "num_worker": "W002",
        "email": "bob@port.pt",
        "password_hash": hash_password("correct"),
        "active": True,
    }
    result = authenticate_worker(_uow_factory(worker=worker), email="bob@port.pt", password="wrong")
    assert result is None


def test_worker_auth_unknown_email_returns_none():
    """BR-39: unknown email returns None."""
    result = authenticate_worker(_uow_factory(), email="nobody@port.pt", password="pass")
    assert result is None


# ---------------------------------------------------------------------------
# BR-40 — Driver auth + PIN claim
# ---------------------------------------------------------------------------

def test_driver_auth_correct_credentials_returns_driver():
    """BR-40: correct licence + password returns the driver dict."""
    pw = "driver_pass"
    driver = {
        "drivers_license": "LIC-001",
        "name": "Carlos",
        "password_hash": hash_password(pw),
        "active": True,
    }
    result = authenticate_driver(
        _uow_factory(driver=driver),
        drivers_license="LIC-001",
        password=pw,
    )
    assert result is not None
    assert result["drivers_license"] == "LIC-001"


def test_driver_auth_wrong_password_returns_none():
    """BR-40: wrong password returns None."""
    driver = {
        "drivers_license": "LIC-002",
        "name": "Maria",
        "password_hash": hash_password("correct"),
        "active": True,
    }
    result = authenticate_driver(
        _uow_factory(driver=driver),
        drivers_license="LIC-002",
        password="wrong",
    )
    assert result is None


def test_driver_auth_inactive_returns_none():
    """BR-40: inactive driver cannot authenticate."""
    pw = "pass"
    driver = {
        "drivers_license": "LIC-003",
        "name": "João",
        "password_hash": hash_password(pw),
        "active": False,
    }
    result = authenticate_driver(
        _uow_factory(driver=driver),
        drivers_license="LIC-003",
        password=pw,
    )
    assert result is None


def _make_appointment(arrival_id: str, driver_license: str, appt_id: int = 1, booking_reference: str = "BR-DEFAULT"):
    return {
        "id": appt_id,
        "arrival_id": arrival_id,
        "booking_reference": booking_reference,
        "driver_license": driver_license,
        "status": "in_transit",
    }


def test_claim_valid_pin_returns_appointment():
    """BR-40: driver claims appointment with correct booking_reference + PIN."""
    appt = _make_appointment("PIN-001", "LIC-010", appt_id=10, booking_reference="BR-010")
    driver = {"drivers_license": "LIC-010", "_appointment": appt}

    result, err = claim_appointment_by_pin(
        _uow_factory(driver=driver, next_active_id=None),
        driver_sub="LIC-010",
        booking_reference="BR-010",
        arrival_id="PIN-001",
    )
    assert result is not None
    assert err == ""
    assert result["arrival_id"] == "PIN-001"


def test_claim_wrong_pin_returns_none():
    """BR-40: wrong PIN returns None with error."""
    driver = {"drivers_license": "LIC-011", "_appointment": None}
    result, err = claim_appointment_by_pin(
        _uow_factory(driver=driver),
        driver_sub="LIC-011",
        booking_reference="BR-011",
        arrival_id="WRONG-PIN",
    )
    assert result is None
    assert "not found" in err.lower() or "invalid" in err.lower()


def test_claim_pin_wrong_booking_reference_returns_not_found():
    """BR-40: wrong booking_reference → appointment not found."""
    appt = _make_appointment("PIN-002", "LIC-020", appt_id=20, booking_reference="BR-CORRECT")
    driver = {"drivers_license": "LIC-020", "_appointment": appt}

    result, err = claim_appointment_by_pin(
        _uow_factory(driver=driver),
        driver_sub="LIC-020",
        booking_reference="BR-WRONG",
        arrival_id="PIN-002",
    )
    assert result is None
    assert "not found" in err.lower() or "invalid" in err.lower()


# ---------------------------------------------------------------------------
# BR-41 — DEBUG_MODE bypasses sequential delivery check
# ---------------------------------------------------------------------------

def test_sequential_check_blocks_out_of_order_without_debug():
    """
    BR-41: without debug_mode, a driver with an earlier active appointment
    cannot claim a later one — sequential delivery is enforced.
    """
    appt = _make_appointment("PIN-003", "LIC-030", appt_id=30, booking_reference="BR-030")
    driver = {"drivers_license": "LIC-030", "_appointment": appt}

    # next_active_id=99 means there's an earlier unfinished delivery
    result, err = claim_appointment_by_pin(
        _uow_factory(driver=driver, next_active_id=99),
        driver_sub="LIC-030",
        booking_reference="BR-030",
        arrival_id="PIN-003",
        debug_mode=False,
    )
    assert result is None
    assert "earlier" in err.lower() or "complete" in err.lower()


def test_debug_mode_bypasses_sequential_check():
    """
    BR-41: debug_mode=True lets the driver claim an appointment even when
    a previous delivery is still active — sequential check is skipped.
    """
    appt = _make_appointment("PIN-004", "LIC-040", appt_id=40, booking_reference="BR-040")
    driver = {"drivers_license": "LIC-040", "_appointment": appt}

    result, err = claim_appointment_by_pin(
        _uow_factory(driver=driver, next_active_id=99),
        driver_sub="LIC-040",
        booking_reference="BR-040",
        arrival_id="PIN-004",
        debug_mode=True,
    )
    assert result is not None, f"debug_mode should bypass sequential check; got err={err!r}"
    assert err == ""
