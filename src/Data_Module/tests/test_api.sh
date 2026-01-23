#!/bin/bash

# Script para testar Data Module API
# Uso: ./test_api.sh [option]

set -e

BASE_URL="http://localhost:8080/api/v1"
TIMEOUT=10

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}Data Module API Test Script${NC}"
echo -e "${BLUE}================================${NC}\n"

# Função para fazer requests
function call_api() {
    local method=$1
    local endpoint=$2
    local data=$3
    
    if [[ -z "$data" ]]; then
        curl -s -X "$method" "$BASE_URL$endpoint" \
            -H "Content-Type: application/json" \
            -w "\n"
    else
        curl -s -X "$method" "$BASE_URL$endpoint" \
            -H "Content-Type: application/json" \
            -d "$data" \
            -w "\n"
    fi
}

# Função para testar endpoint
function test_endpoint() {
    local name=$1
    local method=$2
    local endpoint=$3
    local data=$4
    
    echo -e "${YELLOW}Testing: $name${NC}"
    echo "  Method: $method"
    echo "  Endpoint: $endpoint"
    
    if [[ -n "$data" ]]; then
        echo "  Data: $data"
        response=$(call_api "$method" "$endpoint" "$data")
    else
        response=$(call_api "$method" "$endpoint")
    fi
    
    # Verificar se a resposta é válida JSON
    if echo "$response" | jq . >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓ OK${NC}"
        echo "  Response: $(echo $response | jq . | head -5)"
    else
        echo -e "  ${RED}✗ FAILED${NC}"
        echo "  Response: $response"
    fi
    echo ""
}

# Menu de testes
case "${1:-menu}" in
    health)
        echo -e "${BLUE}=== HEALTH CHECK ===${NC}"
        test_endpoint "Health Check" "GET" "/health"
        ;;
    
    arrivals)
        echo -e "${BLUE}=== ARRIVALS ===${NC}"
        test_endpoint "List Arrivals" "GET" "/arrivals?skip=0&limit=5"
        test_endpoint "Get Stats" "GET" "/arrivals/stats"
        test_endpoint "Get Next" "GET" "/arrivals/next/1?limit=5"
        test_endpoint "Get by ID" "GET" "/arrivals/1"
        test_endpoint "Get by PIN" "GET" "/arrivals/pin/PRT-0001"
        ;;
    
    drivers)
        echo -e "${BLUE}=== DRIVERS ===${NC}"
        test_endpoint "Login" "POST" "/drivers/login" \
            '{"num_carta_cond":"PT12345678","password":"driver123"}'
        test_endpoint "Claim Arrival" "POST" "/drivers/claim?num_carta_cond=PT12345678" \
            '{"pin_acesso":"PRT-0001"}'
        test_endpoint "Get Active" "GET" "/drivers/me/active?num_carta_cond=PT12345678"
        test_endpoint "Get Today" "GET" "/drivers/me/today?num_carta_cond=PT12345678"
        test_endpoint "List Drivers" "GET" "/drivers?skip=0&limit=5"
        ;;
    
    decisions)
        echo -e "${BLUE}=== DECISIONS ===${NC}"
        test_endpoint "Query Arrivals" "POST" "/decisions/query-arrivals" \
            '{"matricula":"XX-XX-XX","gate_id":1}'
        test_endpoint "Register Detection" "POST" "/decisions/detection-event" \
            '{"type":"license_plate_detection","matricula":"XX-XX-XX","gate_id":1,"confidence":0.95,"agent":"AgentB"}'
        test_endpoint "Process Decision" "POST" "/decisions/process" \
            '{"matricula":"XX-XX-XX","gate_id":1,"id_chegada":1,"decision":"approved","estado_entrega":"in_transit"}'
        test_endpoint "Get Detection Events" "GET" "/decisions/events/detections?limit=5"
        ;;
    
    alerts)
        echo -e "${BLUE}=== ALERTS ===${NC}"
        test_endpoint "List Alerts" "GET" "/alerts?skip=0&limit=10"
        test_endpoint "Get Active" "GET" "/alerts/active?limit=5"
        test_endpoint "Get Stats" "GET" "/alerts/stats"
        test_endpoint "Get ADR Codes" "GET" "/alerts/reference/adr-codes"
        test_endpoint "Get Kemler Codes" "GET" "/alerts/reference/kemler-codes"
        ;;
    
    workers)
        echo -e "${BLUE}=== WORKERS ===${NC}"
        test_endpoint "Worker Login" "POST" "/workers/login" \
            '{"email":"carlos.oliveira@porto.pt","password":"password123"}'
        test_endpoint "Manager Login" "POST" "/workers/login" \
            '{"email":"joao.silva@porto.pt","password":"password123"}'
        test_endpoint "List Workers" "GET" "/workers?skip=0&limit=5"
        test_endpoint "List Operators" "GET" "/workers/operators?skip=0&limit=5"
        test_endpoint "List Managers" "GET" "/workers/managers?skip=0&limit=5"
        test_endpoint "Operator Dashboard" "GET" "/workers/operators/2/dashboard/1"
        test_endpoint "Manager Overview" "GET" "/workers/managers/1/overview"
        ;;
    
    all)
        echo -e "${BLUE}=== FULL TEST SUITE ===${NC}"
        echo -e "\n${YELLOW}1. Health${NC}"
        test_endpoint "Health" "GET" "/health"
        
        echo -e "${YELLOW}2. Arrivals${NC}"
        test_endpoint "Arrivals List" "GET" "/arrivals?skip=0&limit=3"
        
        echo -e "${YELLOW}3. Drivers${NC}"
        test_endpoint "Driver Login" "POST" "/drivers/login" \
            '{"num_carta_cond":"PT12345678","password":"driver123"}'
        
        echo -e "${YELLOW}4. Decisions${NC}"
        test_endpoint "Query Arrivals" "POST" "/decisions/query-arrivals" \
            '{"matricula":"XX-XX-XX","gate_id":1}'
        
        echo -e "${YELLOW}5. Alerts${NC}"
        test_endpoint "Alerts List" "GET" "/alerts?skip=0&limit=3"
        
        echo -e "${YELLOW}6. Workers${NC}"
        test_endpoint "Worker Login" "POST" "/workers/login" \
            '{"email":"carlos.oliveira@porto.pt","password":"password123"}'
        
        echo -e "\n${GREEN}=== All tests completed ===${NC}"
        ;;
    
    pytest)
        echo -e "${BLUE}=== RUNNING PYTEST ===${NC}"
        if command -v pytest &> /dev/null; then
            pytest tests/test_integration.py -v --tb=short
        else
            echo -e "${RED}pytest not found. Install with: pip install pytest${NC}"
        fi
        ;;
    
    docker-test)
        echo -e "${BLUE}=== RUNNING DOCKER TESTS ===${NC}"
        docker-compose run data-module pytest tests/test_integration.py -v
        ;;
    
    *)
        echo -e "${BLUE}Uso: $0 [option]${NC}\n"
        echo "Opções disponíveis:"
        echo "  health        - Health check"
        echo "  arrivals      - Testes de chegadas"
        echo "  drivers       - Testes de motoristas"
        echo "  decisions     - Testes de decisões"
        echo "  alerts        - Testes de alertas"
        echo "  workers       - Testes de trabalhadores"
        echo "  all           - Executar todos os testes"
        echo "  pytest        - Executar pytest"
        echo "  docker-test   - Executar testes em Docker"
        echo ""
        echo "Exemplo: $0 arrivals"
        echo "         $0 all"
        ;;
esac
