#!/bin/bash
# Fluxo completo de teste
# Execute este script para testar tudo de uma vez

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

LICENSE_PLATE="${1:-AB-12-CD}"

echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Complete Decision Flow Test          ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
echo ""
echo -e "License Plate: ${YELLOW}${LICENSE_PLATE}${NC}"
echo ""

# Step 1: Setup test data
echo -e "${BLUE}[STEP 1/3]${NC} ${YELLOW}Setting up test data...${NC}"
./test_newArch/setup_test_data.sh "${LICENSE_PLATE}"
echo ""

# Step 2: Run decision flow test
echo -e "${BLUE}[STEP 2/3]${NC} ${YELLOW}Running decision flow test...${NC}"
./test_newArch/run_test.sh "${LICENSE_PLATE}"
echo ""

# Step 3: Verify results
echo -e "${BLUE}[STEP 3/3]${NC} ${YELLOW}Verifying results...${NC}"
./test_newArch/verify_decision.sh "${LICENSE_PLATE}"

echo ""
echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║           Test Complete                ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
