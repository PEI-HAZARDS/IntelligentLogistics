#!/bin/bash
# Script de verificação rápida do fluxo de decisão
# Uso: ./verify_decision.sh <LICENSE_PLATE>

LICENSE_PLATE="$1"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

if [ -z "$LICENSE_PLATE" ]; then
  echo -e "${RED}Error: License plate required${NC}"
  echo -e "Usage: $0 <LICENSE_PLATE>"
  echo -e "Example: $0 AB-12-CD"
  exit 1
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Decision Flow Verification${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "License Plate: ${YELLOW}${LICENSE_PLATE}${NC}"
echo ""

# 1. Data Module Logs
echo -e "${BLUE}=== 1. Data Module Logs (correlation flow) ===${NC}"
docker logs dm_data_module --tail=50 2>&1 | grep -E "truck_id=test-truck|MANUAL_REVIEW|Operator decision|Persisting|persisted|Appointment updated|${LICENSE_PLATE}" | tail -20
if [ $? -ne 0 ]; then
  echo -e "${RED}No relevant logs found${NC}"
fi
echo ""

# 2. MongoDB Decision Event
echo -e "${BLUE}=== 2. MongoDB Decision Event ===${NC}"
MONGO_RESULT=$(docker exec dm_mongo mongosh --username pei_user --password "peiHazards**" --authenticationDatabase admin intelligent_logistics --quiet --eval "db.events.find({license_plate: \"$LICENSE_PLATE\"}).sort({_id: -1}).limit(1).pretty()" 2>&1)
if [ $? -eq 0 ]; then
  echo "$MONGO_RESULT"
  
  # Check for expected fields
  echo ""
  echo -e "${YELLOW}Checking expected fields:${NC}"
  
  if echo "$MONGO_RESULT" | grep -q "type.*decision"; then
    echo -e "  ${GREEN}✓ type: decision${NC}"
  else
    echo -e "  ${RED}✗ type: decision not found${NC}"
  fi
  
  if echo "$MONGO_RESULT" | grep -q "decision.*ACCEPTED"; then
    echo -e "  ${GREEN}✓ decision: ACCEPTED (final)${NC}"
  else
    echo -e "  ${RED}✗ decision: ACCEPTED not found${NC}"
  fi
  
  if echo "$MONGO_RESULT" | grep -q "agent_decision.*MANUAL_REVIEW"; then
    echo -e "  ${GREEN}✓ agent_decision: MANUAL_REVIEW${NC}"
  else
    echo -e "  ${YELLOW}⚠ agent_decision: MANUAL_REVIEW not found${NC}"
  fi
  
  if echo "$MONGO_RESULT" | grep -q "operator_decision.*ACCEPTED"; then
    echo -e "  ${GREEN}✓ operator_decision: ACCEPTED${NC}"
  else
    echo -e "  ${YELLOW}⚠ operator_decision: ACCEPTED not found${NC}"
  fi
  
  if echo "$MONGO_RESULT" | grep -q "decision_source.*operator"; then
    echo -e "  ${GREEN}✓ decision_source: operator${NC}"
  else
    echo -e "  ${YELLOW}⚠ decision_source: operator not found${NC}"
  fi
else
  echo -e "${RED}Error querying MongoDB: $MONGO_RESULT${NC}"
fi
echo ""

# 3. PostgreSQL Appointment
echo -e "${BLUE}=== 3. PostgreSQL Appointment Status ===${NC}"
PG_RESULT=$(docker exec dm_postgres psql -U pei_user -d IntelligentLogistics -t -c "SELECT id, truck_license_plate, status FROM appointment WHERE truck_license_plate = '$LICENSE_PLATE' ORDER BY id DESC LIMIT 1;" 2>&1)
if [ $? -eq 0 ]; then
  echo "$PG_RESULT"
  
  # Check for expected status
  echo ""
  echo -e "${YELLOW}Checking appointment status:${NC}"
  if echo "$PG_RESULT" | grep -q "in_process"; then
    echo -e "  ${GREEN}✓ status: in_process${NC}"
  elif echo "$PG_RESULT" | grep -q "in_transit"; then
    echo -e "  ${YELLOW}⚠ status: in_transit (not updated yet)${NC}"
  else
    echo -e "  ${RED}✗ Appointment not found or unexpected status${NC}"
  fi
else
  echo -e "${RED}Error querying PostgreSQL: $PG_RESULT${NC}"
fi
echo ""

# 4. Summary
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Verification Summary${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Expected Flow:${NC}"
echo -e "  1. Agent sends MANUAL_REVIEW → stored in pending_manual_reviews"
echo -e "  2. Operator sends ACCEPTED → merged with agent decision"
echo -e "  3. Final decision persisted to MongoDB with both decisions"
echo -e "  4. Appointment status updated to in_process in PostgreSQL"
echo ""
echo -e "${YELLOW}If verification fails:${NC}"
echo -e "  - Check Data Module is running: ${GREEN}docker ps | grep dm_data_module${NC}"
echo -e "  - Check Kafka consumer started: ${GREEN}docker logs dm_data_module | grep 'Kafka decision consumer started'${NC}"
echo -e "  - Check for errors: ${GREEN}docker logs dm_data_module | grep -i error${NC}"
echo -e "  - Ensure test data exists: ${GREEN}./setup_test_data.sh ${LICENSE_PLATE}${NC}"
echo ""
