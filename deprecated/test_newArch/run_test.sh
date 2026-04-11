#!/bin/bash
# Wrapper script para executar o teste Python dentro do container Data Module
# Isso garante acesso ao código shared e conexão com Kafka interno

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

# Custom license plate from args
LICENSE_PLATE="${1:-AB-12-CD}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Running Test Inside Data Module Container${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "License Plate: ${YELLOW}${LICENSE_PLATE}${NC}"
echo ""

# Check if Data Module is running
if ! docker ps | grep -q dm_data_module; then
  echo -e "${RED}✗ Error: dm_data_module container is not running${NC}"
  echo -e "Start it with: ${GREEN}docker-compose up -d data-module${NC}"
  exit 1
fi

# Note: setup_test_data.sh already called by test_all.sh, skipping redundant call

# Copy the test script to container (use /tmp to avoid WatchFiles reload)
echo -e "${YELLOW}Copying test script to container...${NC}"
docker cp "${SCRIPT_DIR}/send_test_decisions.py" dm_data_module:/tmp/send_test_decisions.py

# Run the test inside container
echo -e "${YELLOW}Executing test inside container...${NC}"
echo ""

docker exec -e LICENSE_PLATE="${LICENSE_PLATE}" dm_data_module python /tmp/send_test_decisions.py

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Test completed! Now run verification:${NC}"
echo -e "${GREEN}./verify_decision.sh ${LICENSE_PLATE}${NC}"
echo -e "${BLUE}========================================${NC}"
