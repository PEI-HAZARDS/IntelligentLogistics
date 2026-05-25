"""
Tests for infraction review logic (cmd_review_infraction) and route structure.

Rules enforced:
- Raises ValueError when appointment has no highway_infraction flag
- Sets reviewed_at (UTC datetime), reviewed_by, review_note on success
- review_note is None when omitted or empty string
- Re-reviewing (idempotent) overwrites the previous record
- Route source wires ValueError → 409 and missing appointment → 404
- migrationDBv4.sql contains the review columns with IF NOT EXISTS guard
"""

import pytest
from datetime import datetime
from application.use_cases.appointment_commands import cmd_review_infraction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _appt(has_infraction: bool = True, already_reviewed: bool = False) -> dict:
    return {
        "id": 1,
        "truck_license_plate": "AA-00-BB",
        "highway_infraction": has_infraction,
        "reviewed_at": datetime(2026, 1, 1) if already_reviewed else None,
        "reviewed_by": "MG001" if already_reviewed else None,
        "review_note": "prior note" if already_reviewed else None,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestReviewInfractionNoFlag:
    def test_raises_value_error_when_no_infraction(self):
        with pytest.raises(ValueError):
            cmd_review_infraction(_appt(has_infraction=False), reviewed_by="MG001")

    def test_error_message_mentions_appointment_id(self):
        with pytest.raises(ValueError) as exc_info:
            cmd_review_infraction(_appt(has_infraction=False), reviewed_by="MG001")
        assert "1" in str(exc_info.value)

    def test_error_message_mentions_infraction(self):
        with pytest.raises(ValueError) as exc_info:
            cmd_review_infraction(_appt(has_infraction=False), reviewed_by="MG001")
        assert "infraction" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestReviewInfractionSuccess:
    def test_sets_reviewed_by(self):
        result = cmd_review_infraction(_appt(), reviewed_by="MG042")
        assert result["reviewed_by"] == "MG042"

    def test_sets_reviewed_at_as_datetime(self):
        result = cmd_review_infraction(_appt(), reviewed_by="MG001")
        assert isinstance(result["reviewed_at"], datetime)

    def test_reviewed_at_has_no_tzinfo(self):
        # Route stores as naive UTC (TIMESTAMP not TIMESTAMPTZ in ORM column)
        result = cmd_review_infraction(_appt(), reviewed_by="MG001")
        assert result["reviewed_at"].tzinfo is None

    def test_stores_note_when_provided(self):
        result = cmd_review_infraction(_appt(), reviewed_by="MG001", note="Warned carrier")
        assert result["review_note"] == "Warned carrier"

    def test_strips_whitespace_from_note(self):
        result = cmd_review_infraction(_appt(), reviewed_by="MG001", note="  note  ")
        assert result["review_note"] == "note"

    def test_stores_none_when_note_omitted(self):
        result = cmd_review_infraction(_appt(), reviewed_by="MG001")
        assert result["review_note"] is None

    def test_stores_none_when_note_is_empty_string(self):
        result = cmd_review_infraction(_appt(), reviewed_by="MG001", note="")
        assert result["review_note"] is None

    def test_stores_none_when_note_is_only_whitespace(self):
        result = cmd_review_infraction(_appt(), reviewed_by="MG001", note="   ")
        assert result["review_note"] is None

    def test_returns_updated_dict(self):
        result = cmd_review_infraction(_appt(), reviewed_by="MG001", note="Test")
        assert result["id"] == 1
        assert result["reviewed_by"] == "MG001"
        assert result["review_note"] == "Test"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestReviewInfractionIdempotent:
    def test_overwrites_reviewed_by(self):
        appt = _appt(already_reviewed=True)
        result = cmd_review_infraction(appt, reviewed_by="MG099", note="Second review")
        assert result["reviewed_by"] == "MG099"

    def test_overwrites_review_note(self):
        appt = _appt(already_reviewed=True)
        result = cmd_review_infraction(appt, reviewed_by="MG001", note="Updated note")
        assert result["review_note"] == "Updated note"

    def test_overwrites_reviewed_at_with_new_timestamp(self):
        appt = _appt(already_reviewed=True)
        old_ts = appt["reviewed_at"]
        result = cmd_review_infraction(appt, reviewed_by="MG001")
        assert result["reviewed_at"] != old_ts


# ---------------------------------------------------------------------------
# Route structural checks (source inspection, no heavy imports)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestReviewRouteStructure:
    def _arrivals_src(self) -> str:
        from pathlib import Path
        return (Path(__file__).parent.parent.parent / "routes" / "arrivals.py").read_text()

    def test_route_exposes_review_endpoint(self):
        assert "review" in self._arrivals_src()

    def test_route_returns_404_for_missing_appointment(self):
        assert "404" in self._arrivals_src()

    def test_route_returns_409_for_guard_violations(self):
        # Both infraction guard (highway_infraction) and review guard use 409
        assert self._arrivals_src().count("409") >= 2

    def test_route_calls_cmd_review_infraction(self):
        assert "cmd_review_infraction" in self._arrivals_src()

    def test_migration_v4_contains_reviewed_at(self):
        from pathlib import Path
        sql = (
            Path(__file__).parent.parent.parent / "scripts" / "migrationDBv4.sql"
        ).read_text()
        assert "reviewed_at" in sql
        assert "reviewed_by" in sql
        assert "review_note" in sql
        assert "IF NOT EXISTS" in sql
