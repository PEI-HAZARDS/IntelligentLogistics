#!/bin/bash
# Script para criar dados de teste no PostgreSQL

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

LICENSE_PLATE="${1:-AB-12-CD}"
GATE_ID="${2:-1}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Creating Test Data${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "License Plate: ${YELLOW}${LICENSE_PLATE}${NC}"
echo -e "Gate ID: ${YELLOW}${GATE_ID}${NC}"
echo ""

# Create test data
echo -e "${YELLOW}Creating test data in PostgreSQL...${NC}"

# Create terminal
docker exec dm_postgres psql -U pei_user -d IntelligentLogistics -c "
INSERT INTO terminal (id, name, latitude, longitude, hazmat_approved)
VALUES (1, 'Terminal Norte', 41.2345, -8.6789, true)
ON CONFLICT (id) DO NOTHING;" > /dev/null 2>&1

# Create gate
docker exec dm_postgres psql -U pei_user -d IntelligentLogistics -c "
INSERT INTO gate (id, label, latitude, longitude)
VALUES (${GATE_ID}, 'Gate ${GATE_ID}', 41.2345, -8.6789)
ON CONFLICT (id) DO NOTHING;" > /dev/null 2>&1

# Create company
docker exec dm_postgres psql -U pei_user -d IntelligentLogistics -c "
INSERT INTO company (nif, name)
VALUES ('999999999', 'Test Company')
ON CONFLICT (nif) DO NOTHING;" > /dev/null 2>&1

# Create driver
docker exec dm_postgres psql -U pei_user -d IntelligentLogistics -c "
INSERT INTO driver (drivers_license, company_nif, name, active)
VALUES ('DL123456', '999999999', 'Test Driver', true)
ON CONFLICT (drivers_license) DO NOTHING;" > /dev/null 2>&1

# Create truck
echo -e "  Creating truck ${LICENSE_PLATE}..."
docker exec dm_postgres psql -U pei_user -d IntelligentLogistics -c "
INSERT INTO truck (license_plate, company_nif, brand)
VALUES ('${LICENSE_PLATE}', '999999999', 'Test Truck Brand')
ON CONFLICT (license_plate) DO NOTHING
RETURNING license_plate, company_nif;"

# Create booking
docker exec dm_postgres psql -U pei_user -d IntelligentLogistics -c "
INSERT INTO booking (reference, direction)
VALUES ('BK-TEST-001', 'inbound')
ON CONFLICT (reference) DO NOTHING;" > /dev/null 2>&1

# Create appointment
echo -e "  Creating appointment..."
docker exec dm_postgres psql -U pei_user -d IntelligentLogistics -c "
INSERT INTO appointment (
    arrival_id,
    booking_reference,
    driver_license,
    truck_license_plate,
    terminal_id,
    gate_in_id,
    scheduled_start_time,
    expected_duration,
    status
)
VALUES (
    'TEST-ARR-${LICENSE_PLATE}',
    'BK-TEST-001',
    'DL123456',
    '${LICENSE_PLATE}',
    1,
    ${GATE_ID},
    NOW(),
    60,
    'in_transit'
)
ON CONFLICT (arrival_id) DO UPDATE SET
    truck_license_plate = EXCLUDED.truck_license_plate,
    gate_in_id = EXCLUDED.gate_in_id,
    status = 'in_transit'
RETURNING id, arrival_id, truck_license_plate, status, gate_in_id;"

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ Test data created successfully!${NC}"
    echo ""
    echo -e "${YELLOW}Verify appointment:${NC}"
    echo -e "${GREEN}docker exec dm_postgres psql -U pei_user -d IntelligentLogistics -c \"SELECT * FROM appointment WHERE truck_license_plate = '${LICENSE_PLATE}';\"${NC}"
else
    echo ""
    echo -e "${RED}✗ Error creating test data${NC}"
    exit 1
fi
