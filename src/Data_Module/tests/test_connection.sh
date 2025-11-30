#!/bin/sh
# Smoke test detalhado para Data Module (usa Decision Engine mock)
# Coloca em IntelligentLogistics/src/Data_Module/tests/smoke_test_detailed.sh
#
# Requisitos no host: docker, docker-compose, curl, jq, timeout (coreutils)
# Executar a partir de IntelligentLogistics/src/Data_Module
set -eu

HEALTH_URL="http://localhost:8000/health"
DE_HEALTH_URL="http://localhost:8001/health"
DETECTION_URL="http://localhost:8000/api/v1/detections"
TEST_TIMESTAMP="2025-11-30T12:00:00Z"
TEST_GATE=1
TEST_PLATE="AA-00-11"
TEST_CONFIDENCE=0.95
REDIS_CONTAINER="dm_redis"
MONGO_CONTAINER="dm_mongo"
POSTGRES_CONTAINER="dm_postgres"
DATA_MODULE_CONTAINER="dm_data_module"
DE_CONTAINER="dm_decision_engine"

echo "=== Smoke test detalhado: iniciar ==="

wait_for_url() {
  url="$1"
  timeout_secs="${2:-60}"
  echo "Aguardar $timeout_secs s pelo endpoint $url ..."
  start_ts=$(date +%s)
  while : ; do
    if curl -s "$url" >/dev/null 2>&1; then
      echo "  $url disponível"
      return 0
    fi
    now=$(date +%s)
    if [ $((now - start_ts)) -ge "$timeout_secs" ]; then
      echo "  Timeout esperando por $url"
      return 1
    fi
    sleep 1
  done
}

# 1) Esperar readiness do data-module e do DE
if ! wait_for_url "$HEALTH_URL" 60; then
  echo "ERROR: data-module não respondeu em $HEALTH_URL"
  docker compose ps || true
  exit 1
fi

if ! wait_for_url "$DE_HEALTH_URL" 30; then
  echo "WARN: decision-engine não respondeu em $DE_HEALTH_URL (continuando mesmo assim)"
fi

echo
echo "=== Estado dos containers ==="
docker compose ps --services --filter "status=running" | while read svc; do
  echo " - $svc"
done
docker compose ps || true
echo

# 2) Health endpoint: mostrar JSON
echo "Health do data-module:"
curl -s "$HEALTH_URL" | jq .
echo

# 3) Enviar uma deteção de teste
echo "Enviar deteção de teste -> plate=$TEST_PLATE"
resp_file=$(mktemp /tmp/dm_resp.XXXX)
http_code=$(curl -s -w "%{http_code}" -o "$resp_file" -X POST "$DETECTION_URL" \
  -H "Content-Type: application/json" \
  -d "{\"timestamp\":\"$TEST_TIMESTAMP\",\"gate_id\":$TEST_GATE,\"matricula_detectada\":\"$TEST_PLATE\",\"confidence\":$TEST_CONFIDENCE}")
echo "HTTP status: $http_code"
if [ -s "$resp_file" ]; then
  cat "$resp_file" | jq . || cat "$resp_file"
else
  echo "(sem corpo de resposta)"
fi
echo

# 4) Esperar um breve momento para persistência assíncrona
sleep 1

# 5) MongoDB: contagens e últimos documentos
echo "MongoDB counts (detections / events):"
docker exec -i "$MONGO_CONTAINER" mongosh --quiet --eval 'db.getSiblingDB("intelligent_logistics").detections.count()' || true
docker exec -i "$MONGO_CONTAINER" mongosh --quiet --eval 'db.getSiblingDB("intelligent_logistics").events.count()' || true
echo
echo "Última deteção (detections):"
docker exec -i "$MONGO_CONTAINER" mongosh --quiet --eval 'db.getSiblingDB("intelligent_logistics").detections.find().sort({_id:-1}).limit(1).pretty()' || true
echo
echo "Último evento (events):"
docker exec -i "$MONGO_CONTAINER" mongosh --quiet --eval 'db.getSiblingDB("intelligent_logistics").events.find().sort({_id:-1}).limit(1).pretty()' || true
echo

# 6) Redis: listar keys relacionadas e conteúdo de decision:* (se existir)
echo "Redis keys relevantes (pattern plate:* e decision:*):"
docker exec -i "$REDIS_CONTAINER" redis-cli --scan --pattern 'plate:*' | sed -n '1,200p' || true
docker exec -i "$REDIS_CONTAINER" redis-cli --scan --pattern 'decision:*' | sed -n '1,200p' || true
echo

# 7) Ver valor dos primeiro few decision:* keys (se existirem)
first_decision_key=$(docker exec -i "$REDIS_CONTAINER" sh -c "redis-cli --scan --pattern 'decision:*' | head -n1" || true)
if [ -n "$first_decision_key" ]; then
  echo "Exibir conteudo de $first_decision_key:"
  docker exec -i "$REDIS_CONTAINER" redis-cli GET "$first_decision_key" || true
  echo
fi

# 8) Tentar capturar publicação Redis (timeout curto)
# Nota: subscrever bloqueia; usamos timeout para não travar o script.
PUB_CHANNEL="notifications:driver:driver-123"
echo "Tentar escutar um publish em $PUB_CHANNEL (timeout 5s)..."
# Executar subscribe com timeout e mostrar output
if command -v timeout >/dev/null 2>&1; then
  timeout 5 docker exec -i "$REDIS_CONTAINER" redis-cli SUBSCRIBE "$PUB_CHANNEL" | sed -n '1,200p' || true
else
  # sem timeout, executa em background por 5s e depois kill
  docker exec -i "$REDIS_CONTAINER" redis-cli SUBSCRIBE "$PUB_CHANNEL" &
  sleep 5
  pkill -f "redis-cli SUBSCRIBE $PUB_CHANNEL" || true
fi
echo

# 9) Postgres: garantir que existe chegada de teste (id=1) e verificar atualização
echo "Postgres: verificar/insere chegada de teste id=1"
docker exec -i "$POSTGRES_CONTAINER" psql -U porto -d porto_logistica -tAc "SELECT count(*) FROM chegadas_diarias WHERE id_chegada=1;" | sed -n '1,200p' || true
cnt=$(docker exec -i "$POSTGRES_CONTAINER" psql -U porto -d porto_logistica -tAc "SELECT count(*) FROM chegadas_diarias WHERE id_chegada=1;" 2>/dev/null || echo "0")
if [ "$cnt" -eq 0 ]; then
  echo "Inserir registo de chegada de teste (id=1)"
  docker exec -i "$POSTGRES_CONTAINER" psql -U porto -d porto_logistica -c "\
INSERT INTO chegadas_diarias (id_chegada, id_gate_entrada, matricula_pesado, data_prevista) \
VALUES (1, 1, '$TEST_PLATE', CURRENT_DATE) ON CONFLICT (id_chegada) DO NOTHING;" || true
fi
echo "Linha chegadas_diarias id=1:"
docker exec -i "$POSTGRES_CONTAINER" psql -U porto -d porto_logistica -c "SELECT id_chegada, matricula_pesado, estado_entrega, data_hora_chegada FROM chegadas_diarias WHERE id_chegada = 1;" || true
echo

# 10) Mostrar logs relevantes (últimas 200 linhas cada)
echo "Logs do data-module (últimas 200 linhas):"
docker logs --tail 200 "$DATA_MODULE_CONTAINER" || true
echo
echo "Logs do decision-engine (últimas 200 linhas):"
docker logs --tail 200 "$DE_CONTAINER" || true
echo

echo "=== Smoke test completo ==="
