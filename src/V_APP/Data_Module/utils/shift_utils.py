from datetime import time

from infrastructure.persistence.sql_models import ShiftType


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
        "Invalid shift_type. Must be MORNING, AFTERNOON, NIGHT or 06:00-14:00, 14:00-22:00, 22:00-06:00"
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
