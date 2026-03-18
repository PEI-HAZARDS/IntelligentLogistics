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
