"""
Test A2 — Verify demo-critical writes go through UoW + Outbox.

Checks:
1. appointment_commands.py defines all 5 command functions.
2. Each command function uses uow.outbox.append (Guardrail 3).
3. Each command function uses uow.commit() (Guardrail 6).
4. IVisitRepository interface exists in domain/interfaces.py.
5. visit_repository.py implements SqlAlchemyVisitRepository.
6. UoW registers visits repository.
7. Routes import command functions instead of raw query mutations.
8. process_incoming_decision uses cmd_process_decision (not raw SessionLocal writes).
"""

import pytest
from pathlib import Path

SRC = Path(__file__).parent.parent

COMMANDS_PATH = SRC / "application" / "use_cases" / "appointment_commands.py"
INTERFACES_PATH = SRC / "domain" / "interfaces.py"
VISIT_REPO_PATH = SRC / "infrastructure" / "persistence" / "visit_repository.py"
UOW_PATH = SRC / "infrastructure" / "persistence" / "unit_of_work.py"
ARRIVALS_ROUTE_PATH = SRC / "routes" / "arrivals.py"
DECISIONS_ROUTE_PATH = SRC / "routes" / "decisions.py"
DECISION_QUERIES_PATH = SRC / "application" / "queries" / "decision_queries.py"


def _read(path: Path) -> str:
    return path.read_text()


# =================================================================
# 1. Command functions exist
# =================================================================

@pytest.mark.unit
class TestCommandFunctionsDefined:
    """appointment_commands.py must define the 5 command functions."""

    @pytest.mark.parametrize("fn_name", [
        "cmd_update_status",
        "cmd_process_decision",
        "cmd_flag_highway_infraction",
        "cmd_create_visit",
        "cmd_update_visit_state",
    ])
    def test_command_function_defined(self, fn_name):
        source = _read(COMMANDS_PATH)
        assert f"def {fn_name}(" in source, (
            f"appointment_commands.py must define {fn_name}"
        )


# =================================================================
# 2. Each command uses outbox.append (Guardrail 3)
# =================================================================

@pytest.mark.unit
class TestCommandsUseOutbox:
    """Every command must persist a side-effect in the outbox."""

    def test_commands_use_outbox_append(self):
        source = _read(COMMANDS_PATH)
        assert source.count("uow.outbox.append(") >= 5, (
            "Each of the 5 command functions must call uow.outbox.append "
            "(Guardrail 3 — Transactional Outbox)."
        )


# =================================================================
# 3. Each command uses uow.commit (Guardrail 6)
# =================================================================

@pytest.mark.unit
class TestCommandsUseUoWCommit:
    """Every command must commit through UoW, not raw session."""

    def test_commands_use_uow_commit(self):
        source = _read(COMMANDS_PATH)
        assert source.count("uow.commit()") >= 5, (
            "Each of the 5 command functions must call uow.commit() "
            "(Guardrail 6 — UoW abstraction)."
        )

    def test_commands_do_not_use_session_local(self):
        source = _read(COMMANDS_PATH)
        # Check import lines and function bodies for SessionLocal usage
        import_lines = [l for l in source.splitlines() if l.strip().startswith(("import ", "from "))]
        assert not any("SessionLocal" in l for l in import_lines), (
            "Command handlers must not import SessionLocal directly "
            "(Guardrail 6)."
        )
        # Check for SessionLocal() calls (not in strings/comments)
        assert "SessionLocal()" not in source, (
            "Command handlers must not call SessionLocal() directly "
            "(Guardrail 6)."
        )

    def test_commands_do_not_import_session(self):
        source = _read(COMMANDS_PATH)
        assert "from sqlalchemy" not in source, (
            "Command handlers must not import SQLAlchemy directly "
            "(Guardrail 6)."
        )


# =================================================================
# 4. IVisitRepository interface exists
# =================================================================

@pytest.mark.unit
class TestVisitRepositoryInterface:
    """domain/interfaces.py must define IVisitRepository."""

    def test_interface_defined(self):
        source = _read(INTERFACES_PATH)
        assert "class IVisitRepository" in source

    def test_create_method_defined(self):
        source = _read(INTERFACES_PATH)
        assert "def create(" in source

    def test_update_state_method_defined(self):
        source = _read(INTERFACES_PATH)
        assert "def update_state(" in source

    def test_uow_has_visits_property(self):
        source = _read(INTERFACES_PATH)
        assert "visits: IVisitRepository" in source


# =================================================================
# 5. SqlAlchemyVisitRepository exists
# =================================================================

@pytest.mark.unit
class TestVisitRepositoryImplementation:
    """visit_repository.py must implement SqlAlchemyVisitRepository."""

    def test_class_defined(self):
        source = _read(VISIT_REPO_PATH)
        assert "class SqlAlchemyVisitRepository" in source

    def test_implements_interface(self):
        source = _read(VISIT_REPO_PATH)
        assert "IVisitRepository" in source

    def test_create_method(self):
        source = _read(VISIT_REPO_PATH)
        assert "def create(" in source

    def test_update_state_method(self):
        source = _read(VISIT_REPO_PATH)
        assert "def update_state(" in source


# =================================================================
# 6. UoW registers visits repository
# =================================================================

@pytest.mark.unit
class TestUoWRegistersVisits:
    """SqlAlchemyUnitOfWork must instantiate visits repository."""

    def test_uow_imports_visit_repo(self):
        source = _read(UOW_PATH)
        assert "SqlAlchemyVisitRepository" in source

    def test_uow_declares_visits_property(self):
        source = _read(UOW_PATH)
        assert "visits:" in source and "IVisitRepository" in source

    def test_uow_instantiates_visits(self):
        source = _read(UOW_PATH)
        assert "SqlAlchemyVisitRepository(self._session)" in source


# =================================================================
# 7. Routes use command handlers
# =================================================================

@pytest.mark.unit
class TestRoutesUseCommands:
    """arrivals.py write endpoints must import and use command handlers."""

    def test_arrivals_imports_commands(self):
        source = _read(ARRIVALS_ROUTE_PATH)
        assert "from application.use_cases.appointment_commands import" in source

    @pytest.mark.parametrize("cmd", [
        "cmd_update_status",
        "cmd_process_decision",
        "cmd_flag_highway_infraction",
        "cmd_create_visit",
        "cmd_update_visit_state",
    ])
    def test_arrivals_uses_command(self, cmd):
        source = _read(ARRIVALS_ROUTE_PATH)
        assert cmd in source, (
            f"arrivals.py must use {cmd} for write operations (Guardrail 6)."
        )

    def test_arrivals_does_not_import_write_functions(self):
        """arrivals.py must NOT import legacy write functions."""
        source = _read(ARRIVALS_ROUTE_PATH)
        for legacy in [
            "update_appointment_status",
            "update_appointment_from_decision",
            "flag_appointment_highway_infraction",
            "create_visit_for_appointment",
            "update_visit_status",
        ]:
            assert f"import" not in source.split(legacy)[0].split("\n")[-1] if legacy in source else True, (
                f"arrivals.py should not import legacy {legacy} — use command handlers."
            )

    def test_arrivals_has_uow_factory(self):
        source = _read(ARRIVALS_ROUTE_PATH)
        assert "_uow_factory" in source
        assert "SqlAlchemyUnitOfWork" in source


# =================================================================
# 8. process_incoming_decision uses UoW for PG writes
# =================================================================

@pytest.mark.unit
class TestProcessIncomingDecisionRefactored:
    """process_incoming_decision must delegate PG writes to command handlers."""

    def test_uses_cmd_process_decision(self):
        source = _read(DECISION_QUERIES_PATH)
        assert "cmd_process_decision" in source, (
            "process_incoming_decision must use cmd_process_decision for PG writes."
        )

    def test_uses_cmd_update_visit_state(self):
        source = _read(DECISION_QUERIES_PATH)
        assert "cmd_update_visit_state" in source, (
            "process_incoming_decision must use cmd_update_visit_state for delivery state."
        )

    def test_no_raw_db_commit_in_process_decision(self):
        """The main function must not do raw db.commit()."""
        source = _read(DECISION_QUERIES_PATH)
        # Find the process_incoming_decision function body
        func_start = source.index("def process_incoming_decision(")
        # Find the next top-level function
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        assert "db.commit()" not in func_body, (
            "process_incoming_decision must not call db.commit() directly — "
            "PG writes go through UoW."
        )

    def test_manual_review_uses_cmd_in_decisions_route(self):
        source = _read(DECISIONS_ROUTE_PATH)
        assert "cmd_process_decision" in source, (
            "decisions.py manual-review must use cmd_process_decision."
        )

    def test_manual_review_uses_cmd_create_visit(self):
        source = _read(DECISIONS_ROUTE_PATH)
        assert "cmd_create_visit" in source, (
            "decisions.py manual-review must use cmd_create_visit."
        )


# =================================================================
# 9. process_incoming_decision does NOT write partial Redis cache
# =================================================================

ARRIVAL_QUERIES_PATH = SRC / "application" / "queries" / "arrival_queries.py"

@pytest.mark.unit
class TestNoPartialCacheWrite:
    """process_incoming_decision must NOT call cache_appointment directly."""

    def test_no_cache_appointment_in_process_incoming_decision(self):
        source = _read(DECISION_QUERIES_PATH)
        func_start = source.index("def process_incoming_decision(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        assert "cache_appointment(" not in func_body, (
            "process_incoming_decision must not call cache_appointment "
            "directly — it writes a partial snapshot that overwrites "
            "the full projection from the outbox worker."
        )

    def test_no_invalidate_appointment_cache_in_process_decision(self):
        source = _read(DECISION_QUERIES_PATH)
        func_start = source.index("def process_incoming_decision(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        assert "invalidate_appointment_cache(" not in func_body, (
            "process_incoming_decision must not call invalidate_appointment_cache "
            "directly — outbox worker handles cache maintenance (DW-04)."
        )


# =================================================================
# 10. Legacy ORM functions removed (DW-08)
# =================================================================

@pytest.mark.unit
class TestLegacyFunctionsRemoved:
    """Legacy direct-ORM functions were deleted in Phase 7 (DW-08)."""

    @pytest.mark.parametrize("fn_name", [
        "update_appointment_status",
        "create_visit_for_appointment",
        "update_visit_status",
        "update_appointment_from_decision",
        "flag_appointment_highway_infraction",
    ])
    def test_legacy_function_is_gone(self, fn_name):
        source = _read(ARRIVAL_QUERIES_PATH)
        assert f"def {fn_name}(" not in source, (
            f"{fn_name} must be removed from arrival_queries.py (DW-08) — "
            "use appointment_commands.py command handlers instead."
        )
