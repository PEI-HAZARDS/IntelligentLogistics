#!/usr/bin/env python3
"""
Integration tests for Data Module MVP
Run with: pytest tests/test_integration.py -v
"""

import pytest
import httpx
import os
from typing import Generator

# Base URL para os testes (ajustar conforme necessário)
BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8080/api/v1")
TIMEOUT = 30.0


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    """Cria um cliente HTTP para testes"""
    return httpx.Client(base_url=BASE_URL, timeout=TIMEOUT)


@pytest.fixture
def driver_credentials():
    """Credenciais padrão do motorista para testes"""
    return {
        "num_carta_cond": "PT12345678",
        "password": "driver123"
    }


@pytest.fixture
def worker_credentials():
    """Credenciais padrão do trabalhador para testes"""
    return {
        "email": "carlos.oliveira@porto.pt",
        "password": "password123"
    }


@pytest.fixture
def manager_credentials():
    """Credenciais do gestor para testes"""
    return {
        "email": "joao.silva@porto.pt",
        "password": "password123"
    }


# ============================================================================
# HEALTH CHECK
# ============================================================================

class TestHealth:
    """Testes de health check"""

    def test_health_check(self, client: httpx.Client):
        """Verifica se o servidor está respondendo"""
        response = client.get("health")
        assert response.status_code == 200


# ============================================================================
# ARRIVALS
# ============================================================================

class TestArrivals:
    """Testes para o módulo de chegadas"""

    def test_list_arrivals(self, client: httpx.Client):
        """Lista chegadas"""
        response = client.get("/arrivals?skip=0&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if data:
            assert "id_chegada" in data[0]
            assert "matricula_pesado" in data[0]

    def test_get_arrival_stats(self, client: httpx.Client):
        """Obtém estatísticas de chegadas"""
        response = client.get("/arrivals/stats")
        assert response.status_code == 200
        data = response.json()
        assert "in_transit" in data
        assert "delayed" in data
        assert "unloading" in data
        assert "completed" in data

    def test_get_next_arrivals(self, client: httpx.Client):
        """Obtém próximas chegadas para um gate"""
        response = client.get("/arrivals/next/1?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_arrival_by_id(self, client: httpx.Client):
        """Obtém chegada por ID"""
        response = client.get("/arrivals/1")
        assert response.status_code == 200
        data = response.json()
        assert "id_chegada" in data
        assert data["id_chegada"] == 1

    def test_get_arrival_by_pin(self, client: httpx.Client):
        """Obtém chegada pelo PIN"""
        response = client.get("/arrivals/pin/PRT-0001")
        assert response.status_code == 200
        data = response.json()
        assert "pin_acesso" in data
        assert data["pin_acesso"] == "PRT-0001"

    def test_get_arrival_by_plate(self, client: httpx.Client):
        """Consulta chegadas por matrícula"""
        response = client.get("/arrivals/query/matricula/XX-XX-XX")
        assert response.status_code in [200, 404]  # Pode não existir

    def test_get_decision_candidates(self, client: httpx.Client):
        """Obtém candidatas para decisão"""
        response = client.get("/arrivals/decision/candidates/1/XX-XX-XX")
        assert response.status_code in [200, 404]

    def test_update_arrival_status(self, client: httpx.Client):
        """Atualiza estado de uma chegada"""
        response = client.patch(
            "/arrivals/1/status",
            json={
                "estado_entrega": "unloading",
                "observacoes": "Teste de atualização"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["estado_entrega"] == "unloading"

    def test_process_arrival_decision(self, client: httpx.Client):
        """Processa decisão para chegada"""
        response = client.post(
            "/arrivals/1/decision",
            json={
                "decision": "approved",
                "estado_entrega": "in_transit",
                "observacoes": "Decisão de teste"
            }
        )
        assert response.status_code == 200


# ============================================================================
# DRIVERS
# ============================================================================

class TestDrivers:
    """Testes para o módulo de motoristas"""

    def test_driver_login(self, client: httpx.Client, driver_credentials):
        """Testa login de motorista"""
        response = client.post(
            "/drivers/login",
            json=driver_credentials
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["num_carta_cond"] == driver_credentials["num_carta_cond"]

    def test_driver_login_invalid(self, client: httpx.Client):
        """Testa login inválido"""
        response = client.post(
            "/drivers/login",
            json={
                "num_carta_cond": "INVALID",
                "password": "wrong"
            }
        )
        assert response.status_code == 401

    def test_claim_arrival_with_pin(self, client: httpx.Client):
        """Testa reclamação de chegada com PIN"""
        response = client.post(
            "/drivers/claim?num_carta_cond=PT12345678",
            json={"pin_acesso": "PRT-0001"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "id_chegada" in data

    def test_get_driver_active_arrival(self, client: httpx.Client):
        """Obtém chegada ativa do motorista"""
        response = client.get("/drivers/me/active?num_carta_cond=PT12345678")
        assert response.status_code == 200

    def test_get_driver_today_arrivals(self, client: httpx.Client):
        """Obtém chegadas de hoje do motorista"""
        response = client.get("/drivers/me/today?num_carta_cond=PT12345678")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_drivers(self, client: httpx.Client):
        """Lista motoristas"""
        response = client.get("/drivers?skip=0&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_specific_driver(self, client: httpx.Client):
        """Obtém motorista específico"""
        response = client.get("/drivers/PT12345678")
        assert response.status_code == 200
        data = response.json()
        assert data["num_carta_cond"] == "PT12345678"

    def test_get_driver_arrivals_history(self, client: httpx.Client):
        """Obtém histórico de chegadas do motorista"""
        response = client.get("/drivers/PT12345678/arrivals?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


# ============================================================================
# DECISIONS
# ============================================================================

class TestDecisions:
    """Testes para o módulo de decisões"""

    def test_query_arrivals_for_decision(self, client: httpx.Client):
        """Consulta chegadas para decisão"""
        response = client.post(
            "/decisions/query-arrivals",
            json={
                "matricula": "XX-XX-XX",
                "gate_id": 1
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "found" in data
        assert "candidates" in data

    def test_register_detection_event(self, client: httpx.Client):
        """Registra evento de deteção"""
        response = client.post(
            "/decisions/detection-event",
            json={
                "type": "license_plate_detection",
                "matricula": "XX-XX-XX",
                "gate_id": 1,
                "confidence": 0.95,
                "agent": "AgentB"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_process_decision(self, client: httpx.Client):
        """Processa decisão"""
        response = client.post(
            "/decisions/process",
            json={
                "matricula": "XX-XX-XX",
                "gate_id": 1,
                "id_chegada": 1,
                "decision": "approved",
                "estado_entrega": "in_transit",
                "observacoes": "Decisão de teste"
            }
        )
        assert response.status_code == 200

    def test_get_detection_events(self, client: httpx.Client):
        """Obtém eventos de deteção"""
        response = client.get("/decisions/events/detections?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_decision_events(self, client: httpx.Client):
        """Obtém eventos de decisão"""
        response = client.get("/decisions/events/decisions?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_manual_review_decision(self, client: httpx.Client):
        """Testa revisão manual de decisão"""
        response = client.post(
            "/decisions/manual-review/1?decision=approved&observacoes=Revisão de teste"
        )
        assert response.status_code == 200


# ============================================================================
# ALERTS
# ============================================================================

class TestAlerts:
    """Testes para o módulo de alertas"""

    def test_list_alerts(self, client: httpx.Client):
        """Lista alertas"""
        response = client.get("/alerts?skip=0&limit=20")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_active_alerts(self, client: httpx.Client):
        """Obtém alertas ativos"""
        response = client.get("/alerts/active?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_alert_stats(self, client: httpx.Client):
        """Obtém estatísticas de alertas"""
        response = client.get("/alerts/stats")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_get_adr_reference_codes(self, client: httpx.Client):
        """Obtém códigos ADR de referência"""
        response = client.get("/alerts/reference/adr-codes")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        if data:
            # Verifica se há pelo menos um código UN
            assert any(code for code in data.keys())

    def test_get_kemler_reference_codes(self, client: httpx.Client):
        """Obtém códigos Kemler de referência"""
        response = client.get("/alerts/reference/kemler-codes")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_get_alert_by_id(self, client: httpx.Client):
        """Obtém alerta por ID"""
        response = client.get("/alerts/1")
        assert response.status_code in [200, 404]

    def test_create_alert(self, client: httpx.Client):
        """Cria alerta"""
        response = client.post(
            "/alerts",
            json={
                "id_historico_ocorrencia": 1,
                "id_carga": 1,
                "tipo": "DELAY",
                "severidade": 2,
                "descricao": "Teste de alerta"
            }
        )
        assert response.status_code in [200, 201]

    def test_create_adr_alert(self, client: httpx.Client):
        """Cria alerta ADR"""
        response = client.post(
            "/alerts/adr",
            json={
                "id_chegada": 1,
                "un_code": "1203",
                "kemler_code": "33",
                "detected_hazmat": "Teste ADR"
            }
        )
        assert response.status_code in [200, 201]


# ============================================================================
# WORKERS
# ============================================================================

class TestWorkers:
    """Testes para o módulo de trabalhadores"""

    def test_worker_login(self, client: httpx.Client, worker_credentials):
        """Testa login de operador"""
        response = client.post(
            "/workers/login",
            json=worker_credentials
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["email"] == worker_credentials["email"]

    def test_manager_login(self, client: httpx.Client, manager_credentials):
        """Testa login de gestor"""
        response = client.post(
            "/workers/login",
            json=manager_credentials
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["role"] == "manager"

    def test_list_workers(self, client: httpx.Client):
        """Lista trabalhadores"""
        response = client.get("/workers?skip=0&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_operators(self, client: httpx.Client):
        """Lista operadores"""
        response = client.get("/workers/operators")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_managers(self, client: httpx.Client):
        """Lista gestores"""
        response = client.get("/workers/managers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_operator_dashboard(self, client: httpx.Client):
        """Obtém dashboard do operador"""
        response = client.get("/workers/operators/2/dashboard/1")
        assert response.status_code == 200
        data = response.json()
        assert "proximas_chegadas" in data
        assert "stats" in data

    def test_get_manager_overview(self, client: httpx.Client):
        """Obtém visão geral do gestor"""
        response = client.get("/workers/managers/1/overview")
        assert response.status_code == 200
        data = response.json()
        assert "gates_ativos" in data
        assert "turnos_hoje" in data


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """Testes de integração completos"""

    def test_complete_driver_flow(self, client: httpx.Client, driver_credentials):
        """Testa fluxo completo de motorista"""
        # 1. Login
        login_response = client.post(
            "/drivers/login",
            json=driver_credentials
        )
        assert login_response.status_code == 200
        token = login_response.json()["token"]

        # 2. Reivindicar chegada
        claim_response = client.post(
            "/drivers/claim?num_carta_cond=" + driver_credentials["num_carta_cond"],
            json={"pin_acesso": "PRT-0001"}
        )
        assert claim_response.status_code == 200

        # 3. Ver chegada ativa
        active_response = client.get(
            "/drivers/me/active?num_carta_cond=" + driver_credentials["num_carta_cond"]
        )
        assert active_response.status_code == 200

    def test_complete_operator_flow(self, client: httpx.Client, worker_credentials):
        """Testa fluxo completo de operador"""
        # 1. Login
        login_response = client.post(
            "/workers/login",
            json=worker_credentials
        )
        assert login_response.status_code == 200
        worker_id = login_response.json()["num_trabalhador"]

        # 2. Ver dashboard
        dashboard_response = client.get(
            f"/workers/operators/{worker_id}/dashboard/1"
        )
        assert dashboard_response.status_code == 200
        data = dashboard_response.json()
        assert "proximas_chegadas" in data

    def test_complete_decision_flow(self, client: httpx.Client):
        """Testa fluxo completo de decisão"""
        # 1. Registar deteção
        detection_response = client.post(
            "/decisions/detection-event",
            json={
                "type": "license_plate_detection",
                "matricula": "XX-XX-XX",
                "gate_id": 1,
                "confidence": 0.95,
                "agent": "AgentB"
            }
        )
        assert detection_response.status_code == 200

        # 2. Consultar chegadas
        query_response = client.post(
            "/decisions/query-arrivals",
            json={
                "matricula": "XX-XX-XX",
                "gate_id": 1
            }
        )
        assert query_response.status_code == 200

        # 3. Processar decisão
        decision_response = client.post(
            "/decisions/process",
            json={
                "matricula": "XX-XX-XX",
                "gate_id": 1,
                "id_chegada": 1,
                "decision": "approved",
                "estado_entrega": "in_transit"
            }
        )
        assert decision_response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
