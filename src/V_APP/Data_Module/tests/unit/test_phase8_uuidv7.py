"""
Phase 8 unit tests — UUIDv7 enforcement + hazmat alert inbox dedup.

- new_event_id() produces valid UUIDv7 strings
- is_valid_uuidv7() correctly classifies v4 vs v7
- All handler _append_outbox helpers use new_event_id (structural)
- Hazmat route carries event_id field + inbox check (structural)
"""
import pathlib
import re

import pytest

# ---------------------------------------------------------------------------
# UUIDv7 generator — live function tests (domain/events.py has no infra deps)
# ---------------------------------------------------------------------------

from domain.events import new_event_id, is_valid_uuidv7, UUIDv7Str

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class TestNewEventId:

    def test_returns_string(self):
        assert isinstance(new_event_id(), str)

    def test_format_is_uuid(self):
        eid = new_event_id()
        assert _UUID_RE.match(eid), f"Not a UUID format: {eid!r}"

    def test_version_nibble_is_7(self):
        eid = new_event_id()
        # 3rd group (index 2) starts with '7'
        assert eid.split("-")[2][0] == "7", f"Version nibble != 7: {eid!r}"

    def test_variant_bits_are_10xx(self):
        eid = new_event_id()
        variant_char = eid.split("-")[3][0]
        assert variant_char in "89ab", f"Variant char {variant_char!r} not in {{8,9,a,b}}: {eid!r}"

    def test_uniqueness(self):
        ids = {new_event_id() for _ in range(100)}
        assert len(ids) == 100, "Collision in 100 generated UUIDs"

    def test_time_ordering(self):
        ids = [new_event_id() for _ in range(10)]
        # UUIDv7 timestamp is in the first 12 hex chars (48 bits)
        ts_parts = [uid.replace("-", "")[:12] for uid in ids]
        assert ts_parts == sorted(ts_parts), "UUIDv7 IDs are not time-ordered"

    def test_is_valid_uuidv7_accepts_generated(self):
        eid = new_event_id()
        assert is_valid_uuidv7(eid)

    def test_is_valid_uuidv7_rejects_v4(self):
        import uuid
        v4 = str(uuid.uuid4())
        assert not is_valid_uuidv7(v4)

    def test_is_valid_uuidv7_rejects_garbage(self):
        assert not is_valid_uuidv7("not-a-uuid")
        assert not is_valid_uuidv7("")

    def test_uuidv7str_newtype(self):
        eid = new_event_id()
        assert isinstance(eid, str)


# ---------------------------------------------------------------------------
# Structural: all handler outbox helpers use new_event_id
# ---------------------------------------------------------------------------

_BASE = pathlib.Path(__file__).parents[2]


def _src(rel: str) -> str:
    return (_BASE / rel).read_text()


class TestHandlersUseNewEventId:

    def test_alert_handlers_uses_new_event_id(self):
        src = _src("application/use_cases/alert_handlers.py")
        assert "new_event_id" in src
        assert "uuid4" not in src

    def test_worker_handlers_uses_new_event_id(self):
        src = _src("application/use_cases/worker_handlers.py")
        assert "new_event_id" in src
        assert "uuid4" not in src

    def test_appointment_commands_uses_new_event_id(self):
        src = _src("application/use_cases/appointment_commands.py")
        assert "new_event_id" in src
        assert "uuid4" not in src

    def test_container_moved_handler_uses_new_event_id(self):
        src = _src("application/use_cases/container_moved_handler.py")
        assert "new_event_id" in src
        assert "uuid4" not in src

    def test_pending_review_handlers_uses_new_event_id(self):
        src = _src("application/use_cases/pending_review_handlers.py")
        assert "new_event_id" in src
        assert "uuid4" not in src

    def test_notification_handlers_uses_new_event_id(self):
        src = _src("application/use_cases/notification_handlers.py")
        assert "new_event_id" in src
        assert "uuid.uuid4" not in src


# ---------------------------------------------------------------------------
# Structural: hazmat route inbox dedup
# ---------------------------------------------------------------------------

class TestHazmatAlertInboxDedup:
    _ROUTE_SRC = _src("routes/alerts.py")
    _HANDLER_SRC = _src("application/use_cases/alert_handlers.py")

    def test_event_id_field_on_request_model(self):
        assert "event_id" in self._ROUTE_SRC

    def test_inbox_try_insert_received_called(self):
        # Dedup happens inside the use-case handler so it shares the UoW
        # with the alert insert (race condition fix).
        assert "try_insert_received" in self._HANDLER_SRC

    def test_duplicate_returns_409(self):
        assert "HTTP_409_CONFLICT" in self._ROUTE_SRC
        assert "DuplicateHazmatAlert" in self._HANDLER_SRC

    def test_dedup_only_when_event_id_provided(self):
        # Guard must be conditional — handler does dedup only when event_id is set
        assert "if event_id" in self._HANDLER_SRC
