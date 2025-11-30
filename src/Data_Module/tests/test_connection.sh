#!/bin/sh
# Assumindo que estás em IntelligentLogistics/src/Data_Module

echo "Esperar 5s para services estabilizarem..."
sleep 5

echo "Health do data-module:"
curl -s http://localhost:8000/health | jq .

echo "Enviar deteção de teste..."
curl -s -X POST http://localhost:8000/api/v1/detections \
  -H "Content-Type: application/json" \
  -d '{"timestamp":"2025-11-30T12:00:00Z","gate_id":1,"matricula_detectada":"AA-00-11","confidence":0.95}' | jq .

echo "Ver logs recentes do data-module (últimas 200 linhas):"
docker logs --tail 200 dm_data_module
