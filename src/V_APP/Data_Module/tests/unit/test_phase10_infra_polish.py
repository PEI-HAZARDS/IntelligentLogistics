"""
Phase 10 unit tests — Infrastructure polish.

- UoW commit retries on OperationalError (structural + unit)
- Inbox try_insert_received uses begin_nested (SAVEPOINT)
- visit_repository uses INSERT ON CONFLICT DO NOTHING
- redis.py no longer exports is_duplicate_and_mark
- decision_queries.py legacy fallback removed
- kafka_decision_consumer MAX_TRANSIENT_RETRIES removed
- main.py suppresses CancelledError for consumer stop
- outbox worker forwards DEAD_LETTER to DLQ
"""
import pathlib
import pytest

_BASE = pathlib.Path(__file__).parents[2]


def _src(rel: str) -> str:
    return (_BASE / rel).read_text()


# ---------------------------------------------------------------------------
# UoW retry on OperationalError
# ---------------------------------------------------------------------------

class TestUoWCommitRetry:

    def test_retry_constants_defined(self):
        src = _src("infrastructure/persistence/unit_of_work.py")
        assert "_COMMIT_MAX_RETRIES" in src
        assert "_COMMIT_BACKOFF_BASE" in src

    def test_operational_error_imported(self):
        src = _src("infrastructure/persistence/unit_of_work.py")
        assert "OperationalError" in src

    def test_commit_has_retry_loop(self):
        src = _src("infrastructure/persistence/unit_of_work.py")
        fn_start = src.index("def commit(")
        fn_end = src.index("\n    def ", fn_start + 1)
        fn_body = src[fn_start:fn_end]
        assert "for attempt in range" in fn_body
        assert "OperationalError" in fn_body
        assert "rollback" in fn_body

    def test_commit_retry_unit(self):
        """Commit retries on OperationalError and succeeds on second attempt."""
        from unittest.mock import MagicMock, call
        from sqlalchemy.exc import OperationalError

        session = MagicMock()
        session.commit.side_effect = [
            OperationalError("deadlock", None, None),
            None,  # succeeds on second attempt
        ]

        from infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
        uow = SqlAlchemyUnitOfWork.__new__(SqlAlchemyUnitOfWork)
        uow._session = session
        uow.commit()

        assert session.commit.call_count == 2
        assert session.rollback.call_count == 1

    def test_commit_raises_after_max_retries(self):
        from unittest.mock import MagicMock
        from sqlalchemy.exc import OperationalError

        session = MagicMock()
        session.commit.side_effect = OperationalError("deadlock", None, None)

        from infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
        uow = SqlAlchemyUnitOfWork.__new__(SqlAlchemyUnitOfWork)
        uow._session = session
        with pytest.raises(OperationalError):
            uow.commit()

        assert session.commit.call_count == 3


# ---------------------------------------------------------------------------
# Inbox SAVEPOINT
# ---------------------------------------------------------------------------

class TestInboxSavepoint:

    def test_begin_nested_used(self):
        src = _src("infrastructure/persistence/inbox_repository.py")
        fn_start = src.index("def try_insert_received(")
        fn_end = src.index("\n    def ", fn_start + 1)
        fn_body = src[fn_start:fn_end]
        assert "begin_nested" in fn_body, (
            "try_insert_received must use begin_nested() for SAVEPOINT semantics"
        )

    def test_no_full_session_rollback_in_try_insert(self):
        src = _src("infrastructure/persistence/inbox_repository.py")
        fn_start = src.index("def try_insert_received(")
        fn_end = src.index("\n    def ", fn_start + 1)
        fn_body = src[fn_start:fn_end]
        assert "self._session.rollback()" not in fn_body, (
            "try_insert_received must not call self._session.rollback() — "
            "it rolls back the whole transaction; use begin_nested() instead"
        )


# ---------------------------------------------------------------------------
# visit_repository ON CONFLICT DO NOTHING
# ---------------------------------------------------------------------------

class TestVisitRepositoryShiftRace:

    def test_insert_on_conflict_do_nothing_used(self):
        src = _src("infrastructure/persistence/visit_repository.py")
        assert "ON CONFLICT" in src
        assert "DO NOTHING" in src

    def test_text_import_present(self):
        src = _src("infrastructure/persistence/visit_repository.py")
        assert "from sqlalchemy import text" in src or "sqlalchemy.text" in src

    def test_no_select_before_insert_race(self):
        src = _src("infrastructure/persistence/visit_repository.py")
        fn_start = src.index("def _ensure_shift_exists(")
        fn_end = src.index("\n    def ", fn_start + 1)
        fn_body = src[fn_start:fn_end]
        # The old SELECT-then-INSERT pattern used .one_or_none()
        assert ".one_or_none()" not in fn_body, (
            "_ensure_shift_exists must not use SELECT + conditional INSERT "
            "(TOCTOU race) — use ON CONFLICT DO NOTHING instead"
        )


# ---------------------------------------------------------------------------
# redis.py: is_duplicate_and_mark removed
# ---------------------------------------------------------------------------

class TestLegacyDedupRemoved:

    def test_is_duplicate_and_mark_gone_from_redis(self):
        src = _src("infrastructure/persistence/redis.py")
        assert "def is_duplicate_and_mark(" not in src, (
            "is_duplicate_and_mark must be removed from redis.py (Phase 10)"
        )

    def test_legacy_import_gone_from_decision_queries(self):
        src = _src("application/queries/decision_queries.py")
        assert "is_duplicate_and_mark as redis_is_duplicate_legacy" not in src

    def test_decision_queries_legacy_fallback_removed(self):
        src = _src("application/queries/decision_queries.py")
        assert "redis_is_duplicate_legacy" not in src
        assert "time-window dedup" not in src


# ---------------------------------------------------------------------------
# kafka_decision_consumer: MAX_TRANSIENT_RETRIES removed
# ---------------------------------------------------------------------------

class TestKafkaConstantRemoved:

    def test_max_transient_retries_removed(self):
        src = _src("infrastructure/messaging/kafka_decision_consumer.py")
        assert "MAX_TRANSIENT_RETRIES" not in src, (
            "MAX_TRANSIENT_RETRIES was unused — it must be removed (Phase 10)"
        )


# ---------------------------------------------------------------------------
# main.py: CancelledError suppressed for consumer stop
# ---------------------------------------------------------------------------

class TestMainCancelledError:

    def test_consumer_stop_suppresses_cancelled_error(self):
        src = _src("main.py")
        # Both scheduler and consumer stop must handle CancelledError
        assert src.count("asyncio.CancelledError") >= 2, (
            "main.py must suppress CancelledError for both scheduler and consumer shutdown"
        )


# ---------------------------------------------------------------------------
# outbox worker: DEAD_LETTER forwarded to DLQ
# ---------------------------------------------------------------------------

class TestOutboxWorkerDLQ:

    def test_forward_to_dlq_function_defined(self):
        src = _src("scripts/simple_outbox_worker.py")
        assert "def _forward_to_dlq(" in src

    def test_forward_called_on_dead_letter(self):
        src = _src("scripts/simple_outbox_worker.py")
        # The DEAD_LETTER branch must call _forward_to_dlq
        dl_pos = src.index('"DEAD_LETTER"')
        # Find the next occurrence of _forward_to_dlq after DEAD_LETTER assignment
        assert "_forward_to_dlq(" in src[dl_pos:dl_pos + 400], (
            "_forward_to_dlq must be called after setting status = DEAD_LETTER"
        )

    def test_dlq_topic_defined(self):
        src = _src("scripts/simple_outbox_worker.py")
        assert "data.dlq" in src
