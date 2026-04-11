#!/bin/bash
# Debug script - Check appointment details

LICENSE_PLATE="${1:-AB-12-CD}"

echo "=== Checking Appointment ==="
docker exec dm_postgres psql -U pei_user -d IntelligentLogistics -c "
SELECT 
    id, 
    arrival_id,
    truck_license_plate, 
    gate_in_id, 
    status,
    scheduled_start_time
FROM appointment 
WHERE truck_license_plate = '${LICENSE_PLATE}'
ORDER BY id DESC 
LIMIT 1;
"

echo ""
echo "=== All appointments ==="
docker exec dm_postgres psql -U pei_user -d IntelligentLogistics -c "
SELECT 
    id, 
    truck_license_plate, 
    gate_in_id, 
    status
FROM appointment 
LIMIT 5;
"
