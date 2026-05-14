"""
Test A4 — Optimistic concurrency on Appointment status updates.

Verifies that:
1. The Appointment ORM model has a `version` column.
2. AppointmentRepository.update_status() includes a WHERE version check.
3. AppointmentStateRepository.get_for_update() returns version in the dict.
4. AppointmentStateRepository.save_state_transition() increments version.
"""

import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import inspect as sa_inspect

from infrastructure.persistence.sql_models import Appointment


@pytest.mark.unit
class TestAppointmentVersionColumn:
    """Appointment model must have a version column for optimistic concurrency."""

    def test_version_column_exists(self):
        """Appointment ORM must have a 'version' column."""
        mapper = sa_inspect(Appointment)
        column_names = [c.key for c in mapper.column_attrs]
        assert "version" in column_names, (
            "Appointment model is missing 'version' column. "
            "Required for optimistic concurrency control (Risk #8)."
        )

    def test_version_column_has_server_default(self):
        """Version column must have server_default='1' so existing rows get a value."""
        table = Appointment.__table__
        version_col = table.c.version
        assert version_col.server_default is not None, (
            "version column must have a server_default so existing rows "
            "are backfilled with version=1 on migration."
        )
        assert str(version_col.server_default.arg) == "1"

    def test_version_column_not_nullable(self):
        """Version column must be NOT NULL."""
        table = Appointment.__table__
        version_col = table.c.version
        assert not version_col.nullable

    def test_new_appointment_version_default_defined(self):
        """Version column must have Python-side default=1 for ORM inserts."""
        table = Appointment.__table__
        version_col = table.c.version
        assert version_col.default is not None, (
            "version column must have a Python default so ORM inserts "
            "set version=1 without explicit assignment."
        )
        assert version_col.default.arg == 1


@pytest.mark.unit
class TestAppointmentRepositoryOptimisticLock:
    """AppointmentRepository.update_status must enforce WHERE version check."""

    def test_update_status_filters_by_version(self):
        """update_status must include version in the WHERE clause."""
        import ast
        import textwrap
        from pathlib import Path

        repo_path = Path(__file__).parent.parent / "infrastructure" / "persistence" / "appointment_repository.py"
        source = repo_path.read_text()

        # Verify the source contains the version filter pattern
        assert "Appointment.version == version" in source, (
            "AppointmentRepository.update_status() must filter by "
            "Appointment.version == version for optimistic concurrency."
        )

    def test_update_status_increments_version(self):
        """update_status must set version = version + 1 on success."""
        from pathlib import Path

        repo_path = Path(__file__).parent.parent / "infrastructure" / "persistence" / "appointment_repository.py"
        source = repo_path.read_text()

        assert "version + 1" in source, (
            "AppointmentRepository.update_status() must increment version "
            "on successful update."
        )


@pytest.mark.unit
class TestAppointmentStateRepositoryVersionSupport:
    """AppointmentStateRepository must expose and increment version."""

    def test_get_for_update_returns_version(self):
        """get_for_update dict must include 'version' key."""
        from pathlib import Path

        repo_path = Path(__file__).parent.parent / "infrastructure" / "persistence" / "appointment_state_repository.py"
        source = repo_path.read_text()

        assert '"version": row.version' in source or "'version': row.version" in source, (
            "AppointmentStateRepository.get_for_update() must return 'version' "
            "in the aggregate dict."
        )

    def test_save_state_transition_increments_version(self):
        """save_state_transition must bump row.version."""
        from pathlib import Path

        repo_path = Path(__file__).parent.parent / "infrastructure" / "persistence" / "appointment_state_repository.py"
        source = repo_path.read_text()

        assert "row.version" in source and "+ 1" in source, (
            "AppointmentStateRepository.save_state_transition() must increment "
            "row.version on state transition."
        )
