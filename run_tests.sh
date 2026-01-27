#!/bin/bash
# Run all unit tests and generate coverage report for SonarQube
# Usage: ./run_tests.sh

set -e

# Define root directory
ROOT_DIR="$(dirname "$0")"
cd "$ROOT_DIR"

# Activate virtual environment
if [ -d ".venv" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
else
    echo "Warning: .venv not found."
fi

echo "========================================="
echo "   Running IntelligentLogistics Tests    "
echo "========================================="

# Clean previous coverage data
echo "Cleaning previous coverage..."
coverage erase

# Run pytest on the src directory
# We exclude integration tests that might require Docker
# We include --cov flags to generate XML for Sonar
echo "Executing tests..."

# Run pytest on specific working directories
# Excludes Data_Module and api_gateway due to missing dependencies/environment
echo "Executing tests..."

# Run pytest per module to ensure correct import resolution and coverage
# We run tests in their respective directories but aggregate coverage reports

export PYTHONPATH=$PYTHONPATH:"$(pwd)/src"

run_module_test() {
    MODULE_PATH=$1
    REPORT_NAME=$2
    
    if [ -d "$MODULE_PATH" ]; then
        echo ">>> Testing $MODULE_PATH..."
        cd "$MODULE_PATH"
        # Determine coverage target (src vs .)
        if [ -d "src" ]; then
            COV_TARGET="src"
        else
            COV_TARGET="."
        fi
        
        # Run pytest
        # We allow failure if user requested "all available" but we want to fail on critical ones?
        # Ideally we fail if any fail.
        python -m pytest \
            --cov="$COV_TARGET" \
            --cov-report=xml:../../$REPORT_NAME \
            --cov-report=term \
            -v || exit 1
            
        cd - > /dev/null
    else
        echo "Warning: $MODULE_PATH not found."
    fi
}

echo "Executing tests..."
run_module_test "src/shared" "coverage-shared.xml"
run_module_test "src/decision_engine" "coverage-decision.xml"
run_module_test "src/agentA" "coverage-agentA.xml"
run_module_test "src/agentB" "coverage-agentB.xml"
run_module_test "src/agentC" "coverage-agentC.xml"
run_module_test "src/broker" "coverage-broker.xml"

echo "========================================="
echo "   Tests Complete! Reports generated.    "
echo "========================================="

echo "========================================="
echo "   Tests Complete! Coverage generated.   "
echo "========================================="
