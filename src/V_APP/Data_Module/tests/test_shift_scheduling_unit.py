"""
Unit tests for the shift scheduling logic (midnight-aware active window,
chronological ordering, and recurring-template weekday/validity coverage).

These are the bug-prone pure functions behind the dashboard "Active Shifts"
widget and the recurring-shift scheduler. No DB required.
"""

from datetime import date, datetime, timedelta

import pytest

from utils.shift_utils import active_shift_window, shift_order_key
from infrastructure.persistence.sql_models import ShiftType, ShiftTemplate


# ── active_shift_window — the NIGHT shift spans midnight ──────────────────────

@pytest.mark.parametrize("hour,minute,expected_type,day_delta", [
    (2, 0, ShiftType.NIGHT, -1),      # 02:00 → previous day's NIGHT (still running)
    (5, 59, ShiftType.NIGHT, -1),     # just before the morning handover
    (6, 0, ShiftType.MORNING, 0),     # morning starts
    (7, 0, ShiftType.MORNING, 0),
    (13, 59, ShiftType.MORNING, 0),
    (14, 0, ShiftType.AFTERNOON, 0),
    (15, 0, ShiftType.AFTERNOON, 0),
    (21, 59, ShiftType.AFTERNOON, 0),
    (22, 0, ShiftType.NIGHT, 0),      # night starts (same calendar day)
    (23, 30, ShiftType.NIGHT, 0),
])
def test_active_shift_window(hour, minute, expected_type, day_delta):
    now = datetime(2026, 5, 30, hour, minute)
    d, st = active_shift_window(now)
    assert st == expected_type
    assert d == now.date() + timedelta(days=day_delta)


def test_active_shift_window_defaults_to_now():
    # Smoke test: no argument must not raise and returns a valid pair.
    d, st = active_shift_window()
    assert isinstance(d, date)
    assert st in (ShiftType.MORNING, ShiftType.AFTERNOON, ShiftType.NIGHT)


# ── shift_order_key — chronological ordering, NIGHT last within a day ─────────

def test_shift_order_key_within_day():
    d = date(2026, 5, 30)
    assert shift_order_key(d, ShiftType.MORNING) < shift_order_key(d, ShiftType.AFTERNOON)
    assert shift_order_key(d, ShiftType.AFTERNOON) < shift_order_key(d, ShiftType.NIGHT)


def test_shift_order_key_across_days():
    d = date(2026, 5, 30)
    prev = d - timedelta(days=1)
    # Yesterday's NIGHT precedes today's MORNING.
    assert shift_order_key(prev, ShiftType.NIGHT) < shift_order_key(d, ShiftType.MORNING)


# ── ShiftTemplate.covers — weekday mask + validity window + active flag ───────

def _template(weekdays="1111100", valid_from=None, valid_until=None, active=True):
    """Transient ShiftTemplate (no DB) for exercising covers()."""
    return ShiftTemplate(
        gate_id=1,
        shift_type=ShiftType.MORNING,
        weekdays=weekdays,
        valid_from=valid_from or date(2026, 1, 1),
        valid_until=valid_until,
        active=active,
    )


def test_covers_weekday_mask():
    # Monday of an arbitrary week (weekday() == 0) … Sunday (== 6).
    base = date(2026, 6, 15)
    monday = base - timedelta(days=base.weekday())
    days = [monday + timedelta(days=i) for i in range(7)]

    mon_fri = _template(weekdays="1111100")
    assert [mon_fri.covers(d) for d in days] == [True, True, True, True, True, False, False]

    weekend = _template(weekdays="0000011")
    assert [weekend.covers(d) for d in days] == [False, False, False, False, False, True, True]


def test_covers_respects_active_flag():
    monday = date(2026, 6, 15) - timedelta(days=date(2026, 6, 15).weekday())
    assert _template(active=False).covers(monday) is False


def test_covers_respects_validity_window():
    base = date(2026, 6, 15)
    monday = base - timedelta(days=base.weekday())
    # Before valid_from.
    assert _template(valid_from=monday + timedelta(days=7)).covers(monday) is False
    # After valid_until.
    assert _template(valid_until=monday - timedelta(days=1)).covers(monday) is False
    # Inside the window (and a covered weekday).
    assert _template(valid_from=monday - timedelta(days=1),
                     valid_until=monday + timedelta(days=1)).covers(monday) is True
