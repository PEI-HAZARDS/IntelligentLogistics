#!/bin/bash
# reseed.sh — Wipes and reseeds the database without touching other containers.
# Usage: ./reseed.sh

set -e

POSTGRES_CONTAINER="dm_postgres"
DATA_MODULE_CONTAINER="dm_data_module"
POSTGRES_USER="pei_user"
POSTGRES_PASSWORD="peiHazards**"
POSTGRES_DB="IntelligentLogistics"

echo "==> Dropping database (force-disconnects active sessions)..."
docker exec "$POSTGRES_CONTAINER" \
  env PGPASSWORD="$POSTGRES_PASSWORD" \
  psql -U "$POSTGRES_USER" -d postgres \
  -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\" WITH (FORCE);"

echo "==> Recreating database..."
docker exec "$POSTGRES_CONTAINER" \
  env PGPASSWORD="$POSTGRES_PASSWORD" \
  psql -U "$POSTGRES_USER" -d postgres \
  -c "CREATE DATABASE \"$POSTGRES_DB\";"

echo "==> Restarting data module (triggers entrypoint: create tables → triggers → seed)..."
docker restart "$DATA_MODULE_CONTAINER"

echo "==> Waiting for data module to be healthy..."
until [ "$(docker inspect -f '{{.State.Health.Status}}' "$DATA_MODULE_CONTAINER" 2>/dev/null)" = "healthy" ]; do
  sleep 2
  echo "   still waiting..."
done

echo ""
echo "==> Done. Verifying arrival_id for 87AX60:"
docker exec "$POSTGRES_CONTAINER" \
  env PGPASSWORD="$POSTGRES_PASSWORD" \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT arrival_id, truck_license_plate, status FROM appointment WHERE truck_license_plate = '87AX60' AND status = 'scheduled';"
