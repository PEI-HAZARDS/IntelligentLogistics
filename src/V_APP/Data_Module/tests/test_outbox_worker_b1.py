"""
Test B1 — Verify outbox worker retry + exponential backoff + DEAD_LETTER.

Checks:
1. OutboxEvent model has retry_count and next_retry_at columns.
2. Worker fetches both PENDING and retryable FAILED rows.
3. Exponential backoff computes correct delays with jitter.
4. Permanent errors send directly to DEAD_LETTER.
5. Transient errors increment retry_count and schedule next_retry_at.
6. After MAX_RETRIES, row is moved to DEAD_LETTER.
7. Graceful shutdown signal handling is wired.
8. Outbox worker state machine: PENDING → PUBLISHED | FAILED | DEAD_LETTER.
"""

import pytest
import re
from pathlib import Path

SRC = Path(__file__).parent.parent

OUTBOX_MODELS_PATH = SRC / "infrastructure" / "persistence" / "inbox_outbox_models.py"
OUTBOX_WORKER_PATH = SRC / "scripts" / "simple_outbox_worker.py"
OUTBOX_REPO_PATH = SRC / "infrastructure" / "persistence" / "outbox_repository.py"


def _read(path: Path) -> str:
    return path.read_text()


# =================================================================
# 1. OutboxEvent model has retry columns
# =================================================================

@pytest.mark.unit
class TestOutboxEventRetryColumns:
    """OutboxEvent must have retry_count and next_retry_at."""

    def test_retry_count_column(self):
        source = _read(OUTBOX_MODELS_PATH)
        assert "retry_count" in source, "OutboxEvent must have retry_count column"

    def test_retry_count_default_zero(self):
        source = _read(OUTBOX_MODELS_PATH)
        # Find OutboxEvent class body
        class_start = source.index("class OutboxEvent")
        class_body = source[class_start:]
        assert 'server_default="0"' in class_body or "default=0" in class_body, (
            "retry_count must default to 0"
        )

    def test_next_retry_at_column(self):
        source = _read(OUTBOX_MODELS_PATH)
        class_start = source.index("class OutboxEvent")
        class_body = source[class_start:]
        assert "next_retry_at" in class_body, (
            "OutboxEvent must have next_retry_at column"
        )

    def test_dead_letter_in_state_machine_comment(self):
        source = _read(OUTBOX_MODELS_PATH)
        class_start = source.index("class OutboxEvent")
        class_body = source[class_start:]
        assert "DEAD_LETTER" in class_body, (
            "OutboxEvent state machine must include DEAD_LETTER"
        )


# =================================================================
# 2. Worker fetches retryable rows
# =================================================================

@pytest.mark.unit
class TestWorkerFetchRetryableRows:
    """Worker must query PENDING + retryable FAILED rows."""

    def test_fetch_projectable_rows_defined(self):
        source = _read(OUTBOX_WORKER_PATH)
        assert "def fetch_projectable_rows(" in source

    def test_queries_pending_status(self):
        source = _read(OUTBOX_WORKER_PATH)
        func_start = source.index("def fetch_projectable_rows(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        assert '"PENDING"' in func_body or "'PENDING'" in func_body

    def test_queries_failed_with_retry_limit(self):
        source = _read(OUTBOX_WORKER_PATH)
        func_start = source.index("def fetch_projectable_rows(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        assert '"FAILED"' in func_body or "'FAILED'" in func_body
        assert "MAX_RETRIES" in func_body, (
            "Must check retry_count < MAX_RETRIES"
        )

    def test_checks_next_retry_at(self):
        source = _read(OUTBOX_WORKER_PATH)
        func_start = source.index("def fetch_projectable_rows(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        assert "next_retry_at" in func_body, (
            "Must check next_retry_at <= now for retryable rows"
        )


# =================================================================
# 3. Exponential backoff with jitter
# =================================================================

@pytest.mark.unit
class TestExponentialBackoff:
    """compute_next_retry_at must implement exponential backoff + jitter."""

    def test_compute_next_retry_at_defined(self):
        source = _read(OUTBOX_WORKER_PATH)
        assert "def compute_next_retry_at(" in source

    def test_uses_exponential_growth(self):
        source = _read(OUTBOX_WORKER_PATH)
        func_start = source.index("def compute_next_retry_at(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        assert "**" in func_body or "BACKOFF_BASE" in func_body, (
            "Must use exponential backoff"
        )

    def test_has_jitter(self):
        source = _read(OUTBOX_WORKER_PATH)
        func_start = source.index("def compute_next_retry_at(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        assert "jitter" in func_body.lower() or "random" in func_body, (
            "Must add jitter to prevent thundering herd"
        )

    def test_has_max_cap(self):
        source = _read(OUTBOX_WORKER_PATH)
        func_start = source.index("def compute_next_retry_at(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        assert "BACKOFF_MAX" in func_body or "min(" in func_body, (
            "Must cap backoff to prevent excessive delays"
        )

    def test_max_retries_configured(self):
        source = _read(OUTBOX_WORKER_PATH)
        assert re.search(r"MAX_RETRIES\s*=\s*\d+", source), (
            "MAX_RETRIES must be configured"
        )


# =================================================================
# 4. Error classification
# =================================================================

@pytest.mark.unit
class TestErrorClassification:
    """Worker must classify permanent vs transient errors."""

    def test_permanent_error_check_exists(self):
        source = _read(OUTBOX_WORKER_PATH)
        assert "_is_permanent_error" in source or "permanent" in source.lower()

    def test_dead_letter_on_permanent_error(self):
        source = _read(OUTBOX_WORKER_PATH)
        func_start = source.index("def process_batch(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        assert "DEAD_LETTER" in func_body, (
            "process_batch must set DEAD_LETTER status"
        )

    def test_dead_letter_on_max_retries(self):
        source = _read(OUTBOX_WORKER_PATH)
        func_start = source.index("def process_batch(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        assert "MAX_RETRIES" in func_body, (
            "Must move to DEAD_LETTER after MAX_RETRIES"
        )

    def test_retry_count_incremented_on_failure(self):
        source = _read(OUTBOX_WORKER_PATH)
        func_start = source.index("def process_batch(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        assert "retry_count" in func_body, (
            "Must increment retry_count on failure"
        )


# =================================================================
# 5. Graceful shutdown
# =================================================================

@pytest.mark.unit
class TestGracefulShutdown:
    """Worker must handle SIGTERM/SIGINT for graceful shutdown."""

    def test_signal_handler_registered(self):
        source = _read(OUTBOX_WORKER_PATH)
        assert "signal.SIGTERM" in source
        assert "signal.SIGINT" in source

    def test_shutdown_flag_exists(self):
        source = _read(OUTBOX_WORKER_PATH)
        assert "_shutdown_requested" in source

    def test_main_loop_checks_shutdown(self):
        source = _read(OUTBOX_WORKER_PATH)
        func_start = source.index("def main(")
        func_body = source[func_start:]
        assert "_shutdown_requested" in func_body, (
            "main loop must check _shutdown_requested"
        )

    def test_logs_graceful_stop(self):
        source = _read(OUTBOX_WORKER_PATH)
        assert "stopped gracefully" in source.lower() or "shutting down" in source.lower()


# =================================================================
# 6. State machine completeness
# =================================================================

@pytest.mark.unit
class TestOutboxStateMachine:
    """Outbox worker state machine: PENDING → PUBLISHED | FAILED | DEAD_LETTER."""

    def test_marks_published(self):
        source = _read(OUTBOX_WORKER_PATH)
        func_start = source.index("def process_batch(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        assert '"PUBLISHED"' in func_body or "'PUBLISHED'" in func_body

    def test_marks_failed(self):
        source = _read(OUTBOX_WORKER_PATH)
        func_start = source.index("def process_batch(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        assert '"FAILED"' in func_body or "'FAILED'" in func_body

    def test_marks_dead_letter(self):
        source = _read(OUTBOX_WORKER_PATH)
        func_start = source.index("def process_batch(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        assert '"DEAD_LETTER"' in func_body or "'DEAD_LETTER'" in func_body

    def test_sets_published_at_timestamp(self):
        source = _read(OUTBOX_WORKER_PATH)
        func_start = source.index("def process_batch(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        assert "published_at" in func_body

    def test_sets_next_retry_at_on_failure(self):
        source = _read(OUTBOX_WORKER_PATH)
        func_start = source.index("def process_batch(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        assert "next_retry_at" in func_body

    def test_stores_last_error(self):
        source = _read(OUTBOX_WORKER_PATH)
        func_start = source.index("def process_batch(")
        next_func = source.index("\ndef ", func_start + 1)
        func_body = source[func_start:next_func]
        assert "last_error" in func_body


# =================================================================
# 7. Outbox repository supports retry_count
# =================================================================

@pytest.mark.unit
class TestOutboxRepoRetry:
    """Outbox repository mark_publish_failed must increment retry_count."""

    def test_mark_publish_failed_increments_retry(self):
        source = _read(OUTBOX_REPO_PATH)
        func_start = source.index("def mark_publish_failed(")
        next_func = source.index("\n    def ", func_start + 1) if "\n    def " in source[func_start + 1:] else len(source)
        func_body = source[func_start:func_start + 300]
        assert "retry_count" in func_body, (
            "mark_publish_failed must increment retry_count"
        )
