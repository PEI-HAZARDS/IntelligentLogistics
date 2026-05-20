#!/bin/bash
# Run all unit tests and generate coverage reports for SonarQube
# Usage: ./run_tests.sh

set -e

# Define root directory
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

# Set up and activate virtual environment
if [ ! -d ".venv" ] || [ ! -f ".venv/bin/pip" ]; then
    echo "Creating virtual environment..."
    if command -v uv &>/dev/null; then
        uv venv --seed .venv
    else
        python3 -m venv .venv
    fi
fi

echo "Activating virtual environment..."
source .venv/bin/activate

# Ensure test dependencies are installed
if ! python -m pytest --version &>/dev/null; then
    echo "Installing test dependencies..."
    if command -v uv &>/dev/null; then
        uv pip install --quiet pytest pytest-cov pytest-mock
    else
        pip install --quiet pytest pytest-cov pytest-mock
    fi
fi

# Install all module requirements (skips if already satisfied)
echo "Installing project dependencies..."
find src/ -name "requirements.txt" -print0 | while IFS= read -r -d '' req; do
    if command -v uv &>/dev/null; then
        uv pip install --quiet -r "$req" 2>/dev/null || true
    else
        pip install --quiet -r "$req" 2>/dev/null || true
    fi
done

echo "========================================="
echo "   Running IntelligentLogistics Tests    "
echo "========================================="

# Clean previous coverage reports
echo "Cleaning previous coverage reports..."
rm -f coverage.xml .coverage .coverage.*

export PYTHONPATH="${ROOT_DIR}/src:${PYTHONPATH}"

FAILED=0

run_module_test() {
    MODULE_PATH=$1

    if [ -d "$MODULE_PATH" ]; then
        echo ""
        echo ">>> Testing $MODULE_PATH..."

        # Determine coverage target (src vs .)
        if [ -d "$MODULE_PATH/src" ]; then
            COV_TARGET="src"
        else
            COV_TARGET="."
        fi

        # Run pytest and collect coverage data (no XML yet – combined later)
        python -m pytest \
            "$MODULE_PATH" \
            --cov="$MODULE_PATH/$COV_TARGET" \
            --cov-append \
            --cov-report=term \
            -v || FAILED=1
    else
        echo "Warning: $MODULE_PATH not found, skipping."
    fi
}

echo ""
echo "--- Cross-Application Shared ---"
run_module_test "src/shared"

echo ""
echo "--- AI_APP Modules ---"
run_module_test "src/AI_APP/shared"
run_module_test "src/AI_APP/agentA"
run_module_test "src/AI_APP/agentB"
run_module_test "src/AI_APP/agentC"
#run_module_test "src/AI_APP/broker"
run_module_test "src/AI_APP/gateway"

echo ""
echo "--- V_APP Modules ---"
run_module_test "src/V_APP/decision_engine"
run_module_test "src/V_APP/infraction_engine"
run_module_test "src/V_APP/shared"
run_module_test "src/V_APP/gateway"
run_module_test "src/V_APP/v_brain"
#run_module_test "src/V_APP/api_gateway"

# Generate a single combined coverage XML for SonarQube
echo ""
echo "Generating combined coverage.xml..."
python -m coverage xml -o coverage.xml

echo ""
echo "========================================="
if [ $FAILED -ne 0 ]; then
    echo "   Some tests FAILED! See above.        "
    echo "========================================="
    exit 1
else
    echo "   All tests passed! Reports generated.  "
    echo "========================================="
fi
