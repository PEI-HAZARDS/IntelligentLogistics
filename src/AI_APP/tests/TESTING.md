# AI_APP Integration Tests - Quick Guide

This directory is reserved for integration suites outside normal unit-test scope.

- `integration_models/`: model validation and inference behavior tests
- `integration_system/`: end-to-end system integration tests (cross-component)

## 1) Environment Setup

Run from repository root:

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -r src/AI_APP/shared/tests/requirements.txt
```

## 2) Base Command

```bash
PYTHONPATH=src uv run --active pytest -q src/AI_APP/tests
```

## 3) Run Model Integration Only

```bash
PYTHONPATH=src uv run --active pytest -q src/AI_APP/tests/integration_models -m integration_model
```

## 4) Run System Integration Only

```bash
PYTHONPATH=src uv run --active pytest -q src/AI_APP/tests/integration_system -m integration_system
```

