#!/bin/bash
# Run tests for IntelligentLogistics
# Usage: ./run_tests.sh [data|gateway|all]

set -e
SRC_DIR="$(dirname "$0")/src"

echo "========================================="
echo "   IntelligentLogistics Test Runner     "
echo "========================================="

case "${1:-all}" in
    data)
        echo ">>> Data Module Tests"
        cd "$SRC_DIR/Data_Module"
        pytest tests/ -v
        ;;
    gateway)
        echo ">>> API Gateway Tests"
        cd "$SRC_DIR/api_gateway"
        pytest tests/ -v
        ;;
    all)
        echo ">>> Data Module Tests"
        cd "$SRC_DIR/Data_Module"
        pytest tests/ -v || true
        
        echo ">>> API Gateway Tests"
        cd "$SRC_DIR/api_gateway"
        pytest tests/ -v || true
        ;;
    *)
        echo "Usage: $0 [data|gateway|all]"
        exit 1
        ;;
esac

echo "========================================="
echo "   Tests Complete!                      "
echo "========================================="
