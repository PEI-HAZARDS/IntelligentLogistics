#!/bin/bash
# Teste end-to-end para fluxo de infração no Data Module
# - Garante dados de teste
# - Envia mensagem para infraction-decision-{gate}
# - Verifica se appointment.highway_infraction foi atualizado

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

LICENSE_PLATE="${1:-AB-12-CD}"
GATE_ID="${2:-1}"
INFRACTION_RAW="${3:-true}"   # true|false
WAIT_SECONDS="${4:-6}"
TRUCK_ID="infraction-test-$(date +%s)"

INFRACTION="$(echo "${INFRACTION_RAW}" | tr '[:upper:]' '[:lower:]')"

if [[ "${INFRACTION}" != "true" && "${INFRACTION}" != "false" ]]; then
  echo -e "${RED}✗ Error: INFRACTION must be 'true' or 'false' (got '${INFRACTION_RAW}')${NC}"
  exit 1
fi

normalize_bool() {
  case "$(echo "$1" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')" in
    t|true|1|yes) echo "true" ;;
    f|false|0|no|"") echo "false" ;;
    *) echo "$1" ;;
  esac
}

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Infraction Flow Test${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "License Plate: ${YELLOW}${LICENSE_PLATE}${NC}"
echo -e "Gate ID: ${YELLOW}${GATE_ID}${NC}"
echo -e "Infraction: ${YELLOW}${INFRACTION}${NC}"
echo -e "Truck ID: ${YELLOW}${TRUCK_ID}${NC}"
echo ""

if ! docker ps | grep -q dm_data_module; then
  echo -e "${RED}✗ Error: dm_data_module container is not running${NC}"
  exit 1
fi

if ! docker ps | grep -q dm_postgres; then
  echo -e "${RED}✗ Error: dm_postgres container is not running${NC}"
  exit 1
fi

echo -e "${YELLOW}[1/5] Creating/refreshing test appointment...${NC}"
"${SCRIPT_DIR}/setup_test_data.sh" "${LICENSE_PLATE}" "${GATE_ID}"

TARGET_APPOINTMENT_ID=$(docker exec dm_postgres psql -U pei_user -d IntelligentLogistics -t -A -c "
SELECT id
FROM appointment
WHERE truck_license_plate = '${LICENSE_PLATE}'
  AND status IN ('in_transit', 'delayed', 'in_process')
ORDER BY scheduled_start_time DESC NULLS LAST, id DESC
LIMIT 1;" | tr -d '[:space:]')

if [ -z "${TARGET_APPOINTMENT_ID}" ]; then
  echo -e "${RED}✗ No active appointment found for plate '${LICENSE_PLATE}'${NC}"
  exit 1
fi

echo -e "Target appointment id: ${YELLOW}${TARGET_APPOINTMENT_ID}${NC}"

echo -e "${YELLOW}[2/5] Resetting appointment state to baseline...${NC}"
docker exec dm_postgres psql -U pei_user -d IntelligentLogistics -c "
UPDATE appointment
SET status = 'in_transit', highway_infraction = false
WHERE id = ${TARGET_APPOINTMENT_ID};" > /dev/null

echo -e "${YELLOW}[3/5] Reading DB state before publish...${NC}"
docker exec dm_postgres psql -U pei_user -d IntelligentLogistics -c "
SELECT
  id,
  truck_license_plate,
  gate_in_id,
  status,
  CASE WHEN COALESCE(highway_infraction, false) THEN 'true' ELSE 'false' END AS highway_infraction
FROM appointment
WHERE id = ${TARGET_APPOINTMENT_ID};"

BEFORE_FLAG_RAW=$(docker exec dm_postgres psql -U pei_user -d IntelligentLogistics -t -A -c "
SELECT COALESCE(highway_infraction, false)::text
FROM appointment
WHERE id = ${TARGET_APPOINTMENT_ID};" | tr -d '[:space:]')

BEFORE_FLAG="$(normalize_bool "${BEFORE_FLAG_RAW}")"

if [ -z "${BEFORE_FLAG}" ]; then
  echo -e "${RED}✗ No appointment found to test${NC}"
  exit 1
fi

echo -e "${YELLOW}[4/5] Publishing infraction message to Kafka...${NC}"
PUBLISH_OUTPUT=$(docker exec -i \
  -e LICENSE_PLATE="${LICENSE_PLATE}" \
  -e GATE_ID="${GATE_ID}" \
  -e TRUCK_ID="${TRUCK_ID}" \
  -e INFRACTION="${INFRACTION}" \
  dm_data_module \
  python - <<'PY'
import os
import time
from datetime import datetime, timezone

from shared.src.kafka_wrapper import KafkaProducerWrapper

license_plate = os.getenv("LICENSE_PLATE", "AB-12-CD")
gate_id = os.getenv("GATE_ID", "1")
truck_id = os.getenv("TRUCK_ID", f"infraction-test-{int(time.time())}")
infraction = os.getenv("INFRACTION", "true").lower() == "true"

producer = KafkaProducerWrapper("kafka:29092")
topic = f"infraction-decision-{gate_id}"

message = {
    "message_type": "infraction_decision",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "license_plate": license_plate,
    "license_crop_url": f"http://minio:9000/crops/lp_{truck_id}.jpg",
    "un": "1203",
    "kemler": "33",
    "hazard_crop_url": f"http://minio:9000/crops/hz_{truck_id}.jpg",
    "infraction": infraction,
    "gate_id": int(gate_id),
}

producer.produce(
    topic=topic,
    data=message,
    headers={"truckId": truck_id},
)
producer.flush()
print(f"Published to {topic} | truckId={truck_id} | infraction={infraction}")
PY
)

echo "${PUBLISH_OUTPUT}"

if ! echo "${PUBLISH_OUTPUT}" | grep -q "Published to infraction-decision-"; then
  echo -e "${RED}✗ Failed to publish infraction message to Kafka${NC}"
  exit 1
fi

echo -e "${YELLOW}Waiting ${WAIT_SECONDS}s for consumer processing...${NC}"
sleep "${WAIT_SECONDS}"

echo -e "${YELLOW}[5/5] Reading DB state after publish...${NC}"
docker exec dm_postgres psql -U pei_user -d IntelligentLogistics -c "
SELECT
  id,
  truck_license_plate,
  gate_in_id,
  status,
  CASE WHEN COALESCE(highway_infraction, false) THEN 'true' ELSE 'false' END AS highway_infraction
FROM appointment
WHERE id = ${TARGET_APPOINTMENT_ID};"

AFTER_FLAG_RAW=$(docker exec dm_postgres psql -U pei_user -d IntelligentLogistics -t -A -c "
SELECT COALESCE(highway_infraction, false)::text
FROM appointment
WHERE id = ${TARGET_APPOINTMENT_ID};" | tr -d '[:space:]')

AFTER_FLAG="$(normalize_bool "${AFTER_FLAG_RAW}")"

echo ""
echo -e "${BLUE}--- Data Module Logs (tail) ---${NC}"
CURRENT_TRUCK_LOGS=$(docker logs dm_data_module --tail=200 2>&1 | grep "${TRUCK_ID}" || true)
if [ -n "${CURRENT_TRUCK_LOGS}" ]; then
  echo "${CURRENT_TRUCK_LOGS}" | tail -30
else
  docker logs dm_data_module --tail=120 2>&1 | grep -E "infraction|${LICENSE_PLATE}" | tail -30 || true
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Result${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Before highway_infraction: ${YELLOW}${BEFORE_FLAG}${NC}"
echo -e "After  highway_infraction: ${YELLOW}${AFTER_FLAG}${NC}"

if [ "${INFRACTION}" = "true" ]; then
  EXPECTED="true"
else
  EXPECTED="${BEFORE_FLAG}"
fi

if [ "${AFTER_FLAG}" = "${EXPECTED}" ]; then
  echo -e "${GREEN}✓ SUCCESS: DB state changed as expected${NC}"
  exit 0
fi

echo -e "${RED}✗ FAILED: expected highway_infraction='${EXPECTED}' but got '${AFTER_FLAG}'${NC}"
exit 1
