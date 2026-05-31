from datetime import time, date, datetime, timedelta

from infrastructure.persistence.sql_models import ShiftType


_SHIFT_ORDER = {"MORNING": 0, "AFTERNOON": 1, "NIGHT": 2}


_ALIAS_MAP = {
    "MORNING": ShiftType.MORNING,
    "AFTERNOON": ShiftType.AFTERNOON,
    "NIGHT": ShiftType.NIGHT,
}


def parse_shift_type(value: str) -> ShiftType:
    if value is None:
        raise ValueError("shift_type is required")

    normalized = value.strip().upper()
    if normalized in _ALIAS_MAP:
        return _ALIAS_MAP[normalized]

    for shift_type in ShiftType:
        if shift_type.value == value:
            return shift_type

    raise ValueError(
        "Invalid shift_type. Must be MORNING, AFTERNOON, or NIGHT"
    )


def current_shift_type(now_time: time | None = None) -> ShiftType:
    """Return the ShiftType that covers the given time (defaults to now)."""
    from datetime import datetime as _dt

    t = now_time or _dt.now().time()
    # MORNING  06:00–14:00
    # AFTERNOON 14:00–22:00
    # NIGHT    22:00–06:00
    if time(6, 0) <= t < time(14, 0):
        return ShiftType.MORNING
    if time(14, 0) <= t < time(22, 0):
        return ShiftType.AFTERNOON
    return ShiftType.NIGHT


def active_shift_window(now: datetime | None = None) -> tuple[date, ShiftType]:
    """Return the ``(date, ShiftType)`` of the shift actually running at ``now``.

    The NIGHT shift spans midnight (22:00–06:00), so between 00:00 and 06:00 the
    running night shift belongs to the *previous* calendar date — the row was
    created for the day it started on. Callers that ask "what is running now?"
    must use this instead of ``date.today() + current_shift_type()``.
    """
    now = now or datetime.now()
    st = current_shift_type(now.time())
    d = now.date()
    if st == ShiftType.NIGHT and now.time() < time(6, 0):
        d = d - timedelta(days=1)
    return d, st


def shift_order_key(d: date, st: ShiftType) -> tuple[date, int]:
    """Sortable key placing shifts in chronological order within/across days."""
    return (d, _SHIFT_ORDER.get(st.name, 0))
