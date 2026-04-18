# AI_APP Shared Tests - Quick Guide (Unit Focus)

This folder contains unit tests for AI_APP shared modules.
Integration tests were moved to `src/AI_APP/tests` and are run explicitly.

## 1) Environment Setup (uv)

Run from repository root:

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -r src/AI_APP/shared/tests/requirements.txt
```

## 2) Base Command

Use `PYTHONPATH=src` so imports like `AI_APP.shared...` work correctly.

```bash
PYTHONPATH=src uv run --active pytest -q src/AI_APP/shared/tests
```

## 3) Common Commands

Run all shared unit tests:

```bash
PYTHONPATH=src uv run --active pytest -q src/AI_APP/shared/tests
```

Run only consensus tests:

```bash
PYTHONPATH=src uv run --active pytest -q src/AI_APP/shared/tests/consensus_algorithm_unit_test.py
```

Run by keyword (`-k`):

```bash
PYTHONPATH=src uv run --active pytest -q src/AI_APP/shared/tests/consensus_algorithm_unit_test.py -k "most_common_length or partial_confidence"
```

## 4) Output Modes (when to use)

Fast daily feedback (minimal output):

```bash
PYTHONPATH=src uv run --active pytest -q src/AI_APP/shared/tests
```

More detail (test names):

```bash
PYTHONPATH=src uv run --active pytest -vv src/AI_APP/shared/tests
```

Summary of skipped/xfailed/fail reasons:

```bash
PYTHONPATH=src uv run --active pytest -ra src/AI_APP/shared/tests
```

Show live logs from application code:

```bash
PYTHONPATH=src uv run --active pytest -o log_cli=true --log-cli-level=INFO src/AI_APP/shared/tests
```

Show slowest tests:

```bash
PYTHONPATH=src uv run --active pytest --durations=10 src/AI_APP/shared/tests
```

Disable output capture (show print/debug directly):

```bash
PYTHONPATH=src uv run --active pytest -s src/AI_APP/shared/tests
```

## 5) Troubleshooting

Error: `ModuleNotFoundError: No module named 'AI_APP'`
- Cause: missing `PYTHONPATH=src`
- Fix: run commands with `PYTHONPATH=src ...`

Error: `pytest: command not found`
- Cause: dependencies not installed in current env
- Fix: activate `.venv` and install requirements in this folder

---

Tip: Keep `-q` for normal local runs, and switch to `-vv` or log modes only when debugging.

## 6) Integration Tests (moved out of shared/tests)

For system/model integration tests, use the dedicated suite:

```bash
PYTHONPATH=src uv run --active pytest -q src/AI_APP/tests
```

Model-focused integration tests only:

```bash
PYTHONPATH=src uv run --active pytest -q src/AI_APP/tests/integration_models -m integration_model
```
