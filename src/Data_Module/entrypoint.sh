#!/bin/bash

set -e

echo "Data Module entrypoint starting..."

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL..."
until pg_isready -h ${POSTGRES_HOST:-postgres} -p ${POSTGRES_PORT:-5432}; do
  sleep 1
done
echo "PostgreSQL is ready"

# Aguardar MongoDB estar pronto
echo "Waiting for MongoDB..."
until nc -z ${MONGO_HOST:-mongo} ${MONGO_PORT:-27017}; do
  sleep 1
done
echo "MongoDB is ready"

# Aguardar Redis estar pronto
echo "Waiting for Redis..."
until nc -z ${REDIS_HOST:-redis} ${REDIS_PORT:-6379}; do
  sleep 1
done
echo "Redis is ready"

# Rodar data init
echo "Running database initialization..."
python scripts/data_init.py
if [ $? -eq 0 ]; then
  echo "Data initialization completed successfully"
else
  echo "Data initialization failed"
  exit 1
fi

# Run database triggers migration
echo "Running database triggers migration..."
if [ -f "scripts/triggers.sql" ]; then
  PGPASSWORD=${POSTGRES_PASSWORD} psql -h ${POSTGRES_HOST:-postgres} -p ${POSTGRES_PORT:-5432} -U ${POSTGRES_USER} -d ${POSTGRES_DB} -f scripts/triggers.sql
  if [ $? -eq 0 ]; then
    echo "Triggers migration completed successfully"
  else
    echo "Triggers migration failed (may already exist, continuing...)"
  fi
else
  echo "No triggers.sql found, skipping..."
fi

# Iniciar o servidor FastAPI
echo "Starting FastAPI server..."
exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload

