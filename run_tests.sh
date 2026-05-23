#!/bin/bash
# Run all unit tests and generate coverage reports for SonarQube.
# Usage: ./run_tests.sh [--no-datamodule] [--no-cross]
#
# Sections:
#   1. Cross-Application Shared
#   2. AI_APP  (shared, agentA/B/C, gateway)
#   3. V_APP   (decision_engine, infraction_engine, v_brain, gateway, shared)
#   4. V_APP Data Module  (unit + structural integration; no running DB required)
#   5. Cross-Component Contract Tests (AI_APP ↔ V_APP Kafka/event contracts)

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

# ── Parse flags ──────────────────────────────────────────────────────────────
RUN_DATAMODULE=true
RUN_CROSS=true
for arg in "$@"; do
    case $arg in
        --no-datamodule) RUN_DATAMODULE=false ;;
        --no-cross)      RUN_CROSS=false ;;
    esac
done

# ── Root venv (used for all modules except Data Module) ───────────────────
if [ ! -d ".venv" ] || [ ! -f ".venv/bin/pip" ]; then
    echo "Creating root virtual environment..."
    if command -v uv &>/dev/null; then
        uv venv --seed .venv
    else
        python3 -m venv .venv
    fi
fi
source .venv/bin/activate

if ! python -m pytest --version &>/dev/null; then
    echo "Installing test dependencies..."
    if command -v uv &>/dev/null; then
        uv pip install --quiet pytest pytest-cov pytest-mock
    else
        pip install --quiet pytest pytest-cov pytest-mock
    fi
fi

echo "Installing project dependencies..."
find src/ -name "requirements.txt" -print0 | while IFS= read -r -d '' req; do
    if command -v uv &>/dev/null; then
        uv pip install --quiet -r "$req" 2>/dev/null || true
    else
        pip install --quiet -r "$req" 2>/dev/null || true
    fi
done

echo ""
echo "╔════════════════════════════════════════════╗"
echo "║   IntelligentLogistics — Test Suite        ║"
echo "╚════════════════════════════════════════════╝"

rm -f coverage.xml .coverage .coverage.*
export PYTHONPATH="${ROOT_DIR}/src:${PYTHONPATH}"

# ── Per-section result tracking ───────────────────────────────────────────────
declare -A SECTION_RESULTS   # section_name → "PASS" | "FAIL" | "SKIP"
OVERALL_FAILED=0

# ── Helpers ───────────────────────────────────────────────────────────────────

run_module() {
    # run_module <label> <path>
    local LABEL="$1"
    local MODULE_PATH="$2"
    if [ ! -d "$MODULE_PATH" ]; then
        echo "  ⚠  $LABEL: directory not found, skipping."
        return
    fi
    local COV_TARGET="."
    [ -d "$MODULE_PATH/src" ] && COV_TARGET="src"

    if python -m pytest "$MODULE_PATH" \
        --cov="$MODULE_PATH/$COV_TARGET" \
        --cov-append \
        --cov-report=term-missing \
        -q 2>&1; then
        echo "  ✔  $LABEL"
    else
        echo "  ✘  $LABEL — FAILED"
        return 1
    fi
}

run_section() {
    # run_section <section_name> <function_that_runs_tests>
    local NAME="$1"
    shift
    echo ""
    echo "┌─ $NAME ─────────────────────────────────────"
    if "$@"; then
        SECTION_RESULTS["$NAME"]="PASS"
        echo "└─ $NAME: PASSED"
    else
        SECTION_RESULTS["$NAME"]="FAIL"
        OVERALL_FAILED=1
        echo "└─ $NAME: FAILED"
    fi
}

# ── Section runners ───────────────────────────────────────────────────────────

section_shared() {
    run_module "shared" "src/shared"
}

section_ai_app() {
    local FAILED=0
    run_module "AI_APP/shared"   "src/AI_APP/shared"  || FAILED=1
    run_module "AI_APP/agentA"   "src/AI_APP/agentA"  || FAILED=1
    run_module "AI_APP/agentB"   "src/AI_APP/agentB"  || FAILED=1
    run_module "AI_APP/agentC"   "src/AI_APP/agentC"  || FAILED=1
    run_module "AI_APP/gateway"  "src/AI_APP/gateway" || FAILED=1
    return $FAILED
}

section_v_app() {
    local FAILED=0
    run_module "V_APP/decision_engine"   "src/V_APP/decision_engine"   || FAILED=1
    run_module "V_APP/infraction_engine" "src/V_APP/infraction_engine" || FAILED=1
    run_module "V_APP/v_brain"           "src/V_APP/v_brain"           || FAILED=1
    run_module "V_APP/gateway"           "src/V_APP/gateway"           || FAILED=1
    run_module "V_APP/shared"            "src/V_APP/shared"            || FAILED=1
    return $FAILED
}

section_data_module() {
    # Data Module has its own isolated venv (tests/.venv) with its own deps.
    # It does NOT have pytest-cov — coverage is intentionally skipped here to
    # avoid polluting the combined report. Run the Data Module's own coverage
    # separately when needed:
    #   cd src/V_APP/Data_Module && PYTHONPATH=. tests/.venv/bin/python -m pytest tests/ --cov=.
    #
    # Only unit tests and structural (no-DB) integration tests run here.
    # @pytest.mark.integration tests require a running PostgreSQL.

    local DM_ROOT="${ROOT_DIR}/src/V_APP/Data_Module"
    local DM_VENV="${DM_ROOT}/tests/.venv/bin/python"

    if [ ! -f "$DM_VENV" ]; then
        echo "  › Data Module venv not found — creating..."
        (
            cd "${DM_ROOT}/tests"
            python3 -m venv .venv
            .venv/bin/pip install -q -r "${DM_ROOT}/requirements.txt"
        ) || { echo "  ✘  Failed to create Data Module venv"; return 1; }
        echo "  ✔  Data Module venv ready"
    fi

    local FAILED=0

    # Unit tests (all files under tests/unit/)
    echo "  › Data Module — unit tests"
    (
        cd "$DM_ROOT"
        PYTHONPATH=. "$DM_VENV" -m pytest tests/unit/ -q 2>&1
    ) || FAILED=1

    # Structural integration tests — source inspection + Pydantic only, no DB
    echo "  › Data Module — structural integration tests (no DB)"
    (
        cd "$DM_ROOT"
        PYTHONPATH=. "$DM_VENV" -m pytest \
            tests/integration/test_arrival_state_enums.py \
            tests/integration/test_container_moved_atomicity.py \
            -m "not integration" \
            -q \
            2>&1
    ) || FAILED=1

    # Top-level unit-style tests (outbox, commands, optimistic concurrency…)
    echo "  › Data Module — top-level command/outbox tests"
    (
        cd "$DM_ROOT"
        PYTHONPATH=. "$DM_VENV" -m pytest \
            tests/test_appointment_commands_uow.py \
            tests/test_appointment_optimistic_concurrency.py \
            tests/test_arrival_id_no_orm_listener.py \
            tests/test_event_dedup_a3.py \
            tests/test_manual_review_outbox.py \
            tests/test_outbox_worker_b1.py \
            tests/test_manager_statistics_endpoints.py \
            -q \
            2>&1
    ) || FAILED=1

    return $FAILED
}

section_cross_component() {
    if python -m pytest tests/cross_component/ \
        --cov=src \
        --cov-append \
        --cov-report=term-missing \
        -q 2>&1; then
        return 0
    else
        return 1
    fi
}

# ── Run all sections ──────────────────────────────────────────────────────────

run_section "Cross-Application Shared"        section_shared
run_section "AI_APP"                          section_ai_app
run_section "V_APP"                           section_v_app

if [ "$RUN_DATAMODULE" = true ]; then
    run_section "V_APP Data Module"           section_data_module
else
    SECTION_RESULTS["V_APP Data Module"]="SKIP"
    echo ""
    echo "── V_APP Data Module: SKIPPED (--no-datamodule)"
fi

if [ "$RUN_CROSS" = true ]; then
    run_section "Cross-Component Contracts"   section_cross_component
else
    SECTION_RESULTS["Cross-Component Contracts"]="SKIP"
    echo ""
    echo "── Cross-Component Contracts: SKIPPED (--no-cross)"
fi

# ── Generate combined coverage XML ───────────────────────────────────────────
echo ""
echo "Generating combined coverage.xml..."
python -m coverage xml -o coverage.xml 2>/dev/null || true

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "╔════════════════════════════════════════════╗"
echo "║              Test Summary                  ║"
echo "╠════════════════════════════════════════════╣"

declare -A STATUS_ICON=( ["PASS"]="✔" ["FAIL"]="✘" ["SKIP"]="─" )
for section in \
    "Cross-Application Shared" \
    "AI_APP" \
    "V_APP" \
    "V_APP Data Module" \
    "Cross-Component Contracts"
do
    status="${SECTION_RESULTS[$section]:-SKIP}"
    icon="${STATUS_ICON[$status]}"
    printf "║  %s  %-38s ║\n" "$icon" "$section"
done

echo "╚════════════════════════════════════════════╝"

if [ $OVERALL_FAILED -ne 0 ]; then
    echo ""
    echo "RESULT: Some tests FAILED — see above."
    exit 1
else
    echo ""
    echo "RESULT: All sections passed."
    exit 0
fi
