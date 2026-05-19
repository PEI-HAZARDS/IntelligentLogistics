"""
Unit tests for the V_APP API Gateway.

The gateway owns authentication enforcement, route-to-Data-Module proxy
translation, Kafka publication for manual reviews, WebSocket fan-out, and
Kafka-consumer event routing. External systems stay mocked at those borders.
"""

from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[4]
API_GATEWAY_SRC = ROOT / "src" / "V_APP" / "api_gateway" / "src"
SRC = ROOT / "src"
for path in (str(API_GATEWAY_SRC), str(SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

from api_gateway import APIGateway, APIGatewayConfig
from auth.token_validator import TokenPayload
from clients import internal_api_client
from shared.src.kafka_protocol import KafkaTopicFactory


@pytest.fixture
def config() -> APIGatewayConfig:
    return APIGatewayConfig(
        kafka_bootstrap="localhost:9092",
        gate_ids='["1","2","7"]',
        decision_gate_ids='["1","2"]',
        infraction_gate_ids='["7"]',
        data_module_url="http://data-module.test",
        mediamtx_hls_internal_url="http://media.test:8888",
        mediamtx_webrtc_internal_url="http://media.test:8889",
        env="test",
    )


@pytest.fixture
def kafka_producer() -> MagicMock:
    return MagicMock()


@pytest.fixture
def kafka_consumer() -> MagicMock:
    return MagicMock()


@pytest.fixture
def ws_manager() -> MagicMock:
    manager = MagicMock()
    manager.broadcast = AsyncMock()
    manager.broadcast_to_driver = AsyncMock()
    return manager


@pytest.fixture
def gateway(config, kafka_producer, kafka_consumer, ws_manager) -> APIGateway:
    return APIGateway(
        config=config,
        kafka_producer=kafka_producer,
        kafka_consumer=kafka_consumer,
        ws_manager=ws_manager,
    )


@pytest.fixture
def client(gateway) -> TestClient:
    def decode_token(token: str) -> TokenPayload:
        users = {
            "operator-token": TokenPayload(sub="OP-1", roles=["operator"]),
            "manager-token": TokenPayload(sub="MG-1", roles=["manager"]),
            "driver-token": TokenPayload(sub="dl-123", roles=["driver"]),
        }
        if token not in users:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return users[token]

    gateway.app.state.token_validator.decode = MagicMock(side_effect=decode_token)
    return TestClient(gateway.app)


def auth_headers(token: str = "operator-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestAPIGatewayConfig:
    def test_defaults(self):
        cfg = APIGatewayConfig()
        assert cfg.gateway_port == 8000
        assert cfg.gate_id_list == ["1"]
        assert cfg.decision_gate_id_list == ["1"]
        assert cfg.infraction_gate_id_list == ["1"]

    def test_accepts_numeric_gate_ids_as_strings(self):
        cfg = APIGatewayConfig(gate_ids="[2, 3]")
        assert cfg.gate_id_list == ["2", "3"]

    @pytest.mark.parametrize("value", ["invalid", "[]", "{}"])
    def test_rejects_invalid_gate_id_config(self, value):
        with pytest.raises(ValueError):
            APIGatewayConfig(gate_ids=value)


class TestGatewayAppAndAuth:
    def test_health_is_public_and_reports_environment(self, client):
        response = client.get("/health")

        assert response.status_code == 200, response.text
        assert response.json() == {"status": "ok", "env": "test"}

    def test_protected_route_requires_bearer_token(self, client):
        with patch("clients.internal_api_client.get", new_callable=AsyncMock) as data_get:
            response = client.get("/api/arrivals")

        assert response.status_code == 401
        assert response.json()["detail"] == "Not authenticated"
        data_get.assert_not_awaited()

    def test_manager_route_rejects_operator_role(self, client):
        with patch("clients.internal_api_client.get", new_callable=AsyncMock) as data_get:
            response = client.get("/api/drivers", headers=auth_headers("operator-token"))

        assert response.status_code == 403
        assert "manager" in response.json()["detail"]
        data_get.assert_not_awaited()

    def test_driver_cannot_read_another_driver_profile(self, client):
        with patch("clients.internal_api_client.get", new_callable=AsyncMock) as data_get:
            response = client.get("/api/drivers/DL-999", headers=auth_headers("driver-token"))

        assert response.status_code == 403
        assert "own data" in response.json()["detail"]
        data_get.assert_not_awaited()

    def test_driver_can_read_own_profile_case_insensitively(self, client):
        expected = {"drivers_license": "DL-123", "name": "Driver"}
        with patch("clients.internal_api_client.get", new_callable=AsyncMock) as data_get:
            data_get.return_value = expected
            response = client.get("/api/drivers/DL-123", headers=auth_headers("driver-token"))

        assert response.status_code == 200
        assert response.json() == expected
        data_get.assert_awaited_once_with("/drivers/DL-123")

    def test_manager_can_read_any_driver_profile(self, client):
        expected = {"drivers_license": "DL-999", "name": "Other Driver"}
        with patch("clients.internal_api_client.get", new_callable=AsyncMock) as data_get:
            data_get.return_value = expected
            response = client.get("/api/drivers/DL-999", headers=auth_headers("manager-token"))

        assert response.status_code == 200
        assert response.json() == expected
        data_get.assert_awaited_once_with("/drivers/DL-999")

    def test_driver_cannot_read_another_driver_arrivals(self, client):
        with patch("clients.internal_api_client.get", new_callable=AsyncMock) as data_get:
            response = client.get("/api/drivers/DL-999/arrivals", headers=auth_headers("driver-token"))

        assert response.status_code == 403
        assert "own data" in response.json()["detail"]
        data_get.assert_not_awaited()

    def test_driver_can_read_own_arrivals(self, client):
        expected = [{"id": 10, "driver_license": "DL-123"}]
        with patch("clients.internal_api_client.get", new_callable=AsyncMock) as data_get:
            data_get.return_value = expected
            response = client.get("/api/drivers/DL-123/arrivals", headers=auth_headers("driver-token"))

        assert response.status_code == 200
        assert response.json() == expected
        data_get.assert_awaited_once_with("/drivers/DL-123/arrivals", params={"limit": 50})

    def test_manager_can_read_any_driver_arrivals(self, client):
        expected = [{"id": 20, "driver_license": "DL-999"}]
        with patch("clients.internal_api_client.get", new_callable=AsyncMock) as data_get:
            data_get.return_value = expected
            response = client.get("/api/drivers/DL-999/arrivals", headers=auth_headers("manager-token"))

        assert response.status_code == 200
        assert response.json() == expected
        data_get.assert_awaited_once_with("/drivers/DL-999/arrivals", params={"limit": 50})


class TestProxyRoutes:
    def test_arrivals_proxy_translates_query_aliases_and_filters(self, client):
        expected = {"items": [{"id": 10}], "total": 1}
        with patch("clients.internal_api_client.get", new_callable=AsyncMock) as data_get:
            data_get.return_value = expected
            response = client.get(
                "/api/arrivals",
                params={
                    "matricula": "AA-11-BB",
                    "page": 2,
                    "limit": 10,
                    "status": "scheduled",
                    "scheduled_date": "2026-04-22",
                    "gate_id": 1,
                    "search": "ana",
                    "highway_infraction": "true",
                },
                headers=auth_headers(),
            )

        assert response.status_code == 200, response.text
        assert response.json() == expected
        data_get.assert_awaited_once_with(
            "/arrivals",
            params={
                "page": 2,
                "limit": 10,
                "license_plate": "AA-11-BB",
                "status": "scheduled",
                "scheduled_date": "2026-04-22",
                "gate_id": 1,
                "search": "ana",
                "highway_infraction": True,
            },
        )

    def test_gateway_validation_rejects_out_of_range_proxy_query(self, client):
        with patch("clients.internal_api_client.get", new_callable=AsyncMock) as data_get:
            response = client.get(
                "/api/arrivals",
                params={"limit": 101},
                headers=auth_headers(),
            )

        assert response.status_code == 422
        data_get.assert_not_awaited()

    def test_static_alert_reference_route_is_not_captured_by_dynamic_alert_id(self, client):
        with patch("clients.internal_api_client.get", new_callable=AsyncMock) as data_get:
            data_get.return_value = [{"un": "1203", "name": "Gasoline"}]
            response = client.get("/api/alerts/reference/adr-codes", headers=auth_headers())

        assert response.status_code == 200
        data_get.assert_awaited_once_with("/alerts/reference/adr-codes")

    def test_data_module_error_is_returned_to_caller(self, client):
        with patch("clients.internal_api_client.get", new_callable=AsyncMock) as data_get:
            data_get.side_effect = HTTPException(status_code=404, detail="Arrival not found")
            response = client.get("/api/arrivals/detail/999", headers=auth_headers())

        assert response.status_code == 404
        assert response.json() == {"detail": "Arrival not found"}

    def test_stream_route_builds_gateway_owned_media_urls(self, client):
        response = client.get("/api/stream/gate-1/high", headers=auth_headers())

        assert response.status_code == 200, response.text
        assert response.json() == {
            "gate_id": "gate-1",
            "quality": "high",
            "hls_url": "/api/stream/gate-1/high/hls/index.m3u8",
            "webrtc_url": "/api/stream/gate-1/high/whep",
        }

    def test_stream_route_rejects_driver(self, client):
        response = client.get(
            "/api/stream/gate-1/high",
            headers={"Authorization": "Bearer driver-token"},
        )
        assert response.status_code == 403


class TestAuthRoutes:
    def test_worker_login_returns_tokens_and_profile(self, client, gateway):
        gateway.app.state.keycloak_client.exchange_credentials = AsyncMock(
            return_value={
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_in": 300,
                "token_type": "Bearer",
            }
        )
        with patch("clients.internal_api_client.get", new_callable=AsyncMock) as data_get:
            data_get.return_value = {"email": "manager@example.com", "name": "Manager"}
            response = client.post(
                "/api/auth/workers/login",
                json={"email": "manager@example.com", "password": "secret"},
            )

        assert response.status_code == 200
        assert response.json()["user_info"] == {"email": "manager@example.com", "name": "Manager"}
        gateway.app.state.keycloak_client.exchange_credentials.assert_awaited_once_with(
            "manager@example.com",
            "secret",
        )
        data_get.assert_awaited_once_with("/workers/by-email/manager@example.com")

    def test_driver_login_falls_back_when_profile_lookup_fails(self, client, gateway):
        gateway.app.state.keycloak_client.exchange_credentials = AsyncMock(
            return_value={"access_token": "access", "refresh_token": "refresh"}
        )
        with patch("clients.internal_api_client.get", new_callable=AsyncMock) as data_get:
            data_get.side_effect = HTTPException(status_code=404, detail="missing profile")
            response = client.post(
                "/api/auth/drivers/login",
                json={"drivers_license": "dl-123", "password": "secret"},
            )

        assert response.status_code == 200
        assert response.json()["user_info"] == {"drivers_license": "dl-123"}


class TestManualReviewAndWebSockets:
    def test_manual_review_publishes_to_gate_topic_and_broadcasts(self, client, kafka_producer, ws_manager):
        response = client.post(
            "/api/manual-review/",
            params={
                "gate_id": "2",
                "license_plate": "AA-11-BB",
                "license_crop_url": "license.jpg",
                "un": "1203",
                "kemler": "33",
                "hazard_crop_url": "hazard.jpg",
                "route": "A1",
                "decision": "ACCEPTED",
                "decision_reason": "documents match",
                "alerts": ["adr_ok"],
                "decision_source": "operator",
                "truck_id": "truck-7",
            },
            headers=auth_headers(),
        )

        assert response.status_code == 200, response.text
        assert response.json() == {
            "status": "ACCEPTED",
            "message": "Decision 'ACCEPTED' propagated",
        }
        kafka_producer.produce.assert_called_once()
        _, kwargs = kafka_producer.produce.call_args
        assert kwargs["topic"] == KafkaTopicFactory.operator_decision("2")
        assert kwargs["headers"] == {"truckId": "truck-7"}
        assert kwargs["data"]["license_plate"] == "AA-11-BB"
        assert kwargs["data"]["decision"] == "ACCEPTED"
        assert kwargs["data"]["alerts"] == ["adr_ok"]
        ws_manager.broadcast.assert_awaited_once()
        assert ws_manager.broadcast.await_args.args[0] == "2"
        assert ws_manager.broadcast.await_args.args[1]["truck_id"] == "truck-7"
        assert ws_manager.broadcast.await_args.args[1]["alerts"] == ["adr_ok"]

    def test_manual_review_preserves_frontend_style_alerts_array(self, client, kafka_producer, ws_manager):
        response = client.post(
            "/api/manual-review/",
            params={
                "gate_id": "2",
                "license_plate": "AA-11-BB",
                "decision": "REJECTED",
                "decision_reason": "operator rejected",
                # Axios serializes query arrays as alerts[]=a&alerts[]=b by default.
                "alerts[]": ["adr_mismatch", "expired_documents"],
            },
            headers=auth_headers(),
        )

        assert response.status_code == 200, response.text
        kafka_producer.produce.assert_called_once()
        _, kwargs = kafka_producer.produce.call_args
        assert kwargs["topic"] == KafkaTopicFactory.operator_decision("2")
        assert kwargs["data"]["alerts"] == ["adr_mismatch", "expired_documents"]
        ws_manager.broadcast.assert_awaited_once()
        assert ws_manager.broadcast.await_args.args[1]["alerts"] == ["adr_mismatch", "expired_documents"]

    def test_manual_review_openapi_keeps_alerts_as_query_params_only(self, gateway):
        operation = gateway.app.openapi()["paths"]["/api/manual-review/"]["post"]
        parameter_names = {
            (parameter["in"], parameter["name"])
            for parameter in operation["parameters"]
        }

        assert ("query", "alerts") in parameter_names
        assert ("query", "alerts[]") in parameter_names
        assert "requestBody" not in operation

    def test_manual_review_validation_failure_does_not_publish(self, client, kafka_producer, ws_manager):
        response = client.post(
            "/api/manual-review/",
            params={"gate_id": "2", "license_plate": "AA-11-BB"},
            headers=auth_headers(),
        )

        assert response.status_code == 422
        kafka_producer.produce.assert_not_called()
        ws_manager.broadcast.assert_not_awaited()

    def test_status_update_broadcast_failures_do_not_break_proxy_response(self, client, ws_manager):
        ws_manager.broadcast.side_effect = RuntimeError("ws down")
        result = {"id": 55, "gate_in_id": 1, "driver_license": "DL-123", "status": "completed"}

        with patch("clients.internal_api_client.patch", new_callable=AsyncMock) as data_patch:
            data_patch.return_value = result
            response = client.patch(
                "/api/arrivals/55/status",
                json={"status": "completed", "notes": "left gate"},
                headers=auth_headers(),
            )

        assert response.status_code == 200
        assert response.json() == result
        data_patch.assert_awaited_once_with(
            "/arrivals/55/status",
            json={"status": "completed", "notes": "left gate"},
        )
        ws_manager.broadcast.assert_awaited_once()
        ws_manager.broadcast_to_driver.assert_awaited_once_with(
            "DL-123",
            {"message_type": "status_changed", "appointment_id": 55, "new_status": "completed"},
        )

    def test_driver_status_update_requires_owned_appointment(self, client, ws_manager):
        with (
            patch("clients.internal_api_client.get", new_callable=AsyncMock) as data_get,
            patch("clients.internal_api_client.patch", new_callable=AsyncMock) as data_patch,
        ):
            data_get.return_value = {"id": 55, "driver_license": "DL-999", "gate_in_id": 1}
            response = client.patch(
                "/api/drivers/appointments/55/status",
                json={"status": "completed"},
                headers=auth_headers("driver-token"),
            )

        assert response.status_code == 403
        assert "own appointments" in response.json()["detail"]
        data_get.assert_awaited_once_with("/arrivals/55")
        data_patch.assert_not_awaited()
        ws_manager.broadcast.assert_not_awaited()
        ws_manager.broadcast_to_driver.assert_not_awaited()

    def test_driver_status_update_allows_owned_appointment(self, client, ws_manager):
        appointment = {"id": 55, "driver_license": "DL-123", "gate_in_id": 1}
        result = {"id": 55, "driver_license": "DL-123", "gate_in_id": 1, "status": "completed"}

        with (
            patch("clients.internal_api_client.get", new_callable=AsyncMock) as data_get,
            patch("clients.internal_api_client.patch", new_callable=AsyncMock) as data_patch,
        ):
            data_get.return_value = appointment
            data_patch.return_value = result
            response = client.patch(
                "/api/drivers/appointments/55/status",
                json={"status": "completed"},
                headers=auth_headers("driver-token"),
            )

        assert response.status_code == 200
        assert response.json() == result
        data_get.assert_awaited_once_with("/arrivals/55")
        data_patch.assert_awaited_once_with("/arrivals/55/status", json={"status": "completed"})
        ws_manager.broadcast.assert_awaited_once()
        ws_manager.broadcast_to_driver.assert_awaited_once_with(
            "DL-123",
            {"message_type": "status_changed", "appointment_id": 55, "new_status": "completed"},
        )

    def test_driver_visit_update_denied_for_non_owned_appointment(self, client, ws_manager):
        with (
            patch("clients.internal_api_client.get", new_callable=AsyncMock) as data_get,
            patch("clients.internal_api_client.patch", new_callable=AsyncMock) as data_patch,
        ):
            data_get.return_value = {"id": 55, "driver_license": "DL-999", "gate_in_id": 1}
            response = client.patch(
                "/api/drivers/appointments/55/visit",
                json={"state": "unloading"},
                headers=auth_headers("driver-token"),
            )

        assert response.status_code == 403
        assert "own appointments" in response.json()["detail"]
        data_get.assert_awaited_once_with("/arrivals/55")
        data_patch.assert_not_awaited()
        ws_manager.broadcast.assert_not_awaited()
        ws_manager.broadcast_to_driver.assert_not_awaited()

    def test_driver_visit_update_allowed_for_owned_appointment(self, client, ws_manager):
        appointment = {"id": 55, "driver_license": "DL-123", "gate_in_id": 1}
        result = {"id": 55, "driver_license": "DL-123", "gate_in_id": 1, "visit_state": "unloading"}

        with (
            patch("clients.internal_api_client.get", new_callable=AsyncMock) as data_get,
            patch("clients.internal_api_client.patch", new_callable=AsyncMock) as data_patch,
        ):
            data_get.return_value = appointment
            data_patch.return_value = result
            response = client.patch(
                "/api/drivers/appointments/55/visit",
                json={"state": "unloading"},
                headers=auth_headers("driver-token"),
            )

        assert response.status_code == 200
        assert response.json() == result
        data_get.assert_awaited_once_with("/arrivals/55")
        data_patch.assert_awaited_once_with("/arrivals/55/visit", json={"state": "unloading"})
        ws_manager.broadcast.assert_awaited_once_with(
            "1",
            {"message_type": "status_changed", "appointment_id": 55, "new_status": "unloading"},
        )
        ws_manager.broadcast_to_driver.assert_awaited_once_with(
            "DL-123",
            {"message_type": "status_changed", "appointment_id": 55, "new_status": "unloading"},
        )


class TestInternalDataModuleClient:
    @pytest.mark.anyio
    async def test_request_error_becomes_bad_gateway(self):
        with patch("clients.internal_api_client.httpx.AsyncClient") as async_client:
            async_client.return_value.__aenter__.return_value.request = AsyncMock(
                side_effect=httpx.ConnectError("connection refused")
            )

            with pytest.raises(HTTPException) as exc_info:
                await internal_api_client.get("/arrivals")

        assert exc_info.value.status_code == 502
        assert "Data Module" in exc_info.value.detail

    @pytest.mark.anyio
    async def test_non_json_success_response_returns_text(self):
        response = MagicMock(status_code=200)
        response.json.side_effect = ValueError("not json")
        response.text = "plain ok"

        with patch("clients.internal_api_client.httpx.AsyncClient") as async_client:
            async_client.return_value.__aenter__.return_value.request = AsyncMock(return_value=response)
            result = await internal_api_client.get("health")

        assert result == "plain ok"
        async_client.return_value.__aenter__.return_value.request.assert_awaited_once_with(
            method="GET",
            url="http://data-module:8000/api/v1/health",
            params=None,
            json=None,
            headers=None,
        )


class TestConsumerEventRouting:
    def test_initializes_consumer_topics_for_scale_decision_and_infraction(self, gateway):
        assert KafkaTopicFactory.scale_up() in gateway.consume_topics
        assert KafkaTopicFactory.scale_down() in gateway.consume_topics
        assert KafkaTopicFactory.agent_decision("1") in gateway.consume_topics
        assert KafkaTopicFactory.agent_decision("2") in gateway.consume_topics
        assert KafkaTopicFactory.infraction_decision("7") in gateway.consume_topics

    def test_resolves_gate_from_payload_before_topic_suffix(self, gateway):
        assert gateway._resolve_target_gate({"gate_id": "payload-gate"}, "agent-decision-topic-gate") == "payload-gate"

    def test_resolves_gate_from_topic_suffix_when_payload_has_no_gate(self, gateway):
        assert gateway._resolve_target_gate({}, "agent-decision-12") == "12"

    def test_infraction_fanout_targets_source_gate_other_operator_gates_and_driver(self, gateway):
        gateway._broadcast_async = MagicMock()
        gateway._notify_driver_of_infraction = MagicMock()

        gateway._handle_infraction(
            {"message_type": "infraction_decision", "license_plate": "AA-11-BB", "infraction": True},
            "1",
        )

        assert gateway._broadcast_async.call_args_list[0].args == (
            {"message_type": "infraction_decision", "license_plate": "AA-11-BB", "infraction": True},
            "1",
        )
        assert gateway._broadcast_async.call_args_list[1].args == (
            {"message_type": "status_changed", "reason": "infraction_decision"},
            "2",
        )
        gateway._notify_driver_of_infraction.assert_called_once_with("AA-11-BB", "1")

    def test_accepted_decision_broadcasts_gate_and_notifies_driver(self, gateway):
        gateway._broadcast_async = MagicMock()
        gateway._notify_driver_of_acceptance = MagicMock()
        payload = {
            "message_type": "decision_results",
            "decision": "ACCEPTED",
            "license_plate": "AA-11-BB",
        }

        gateway._handle_decision(payload, "2")

        gateway._broadcast_async.assert_called_once_with(payload, "2")
        gateway._notify_driver_of_acceptance.assert_called_once_with("AA-11-BB")

    def test_consumer_loop_skips_invalid_and_skipped_messages(self, gateway, kafka_consumer):
        invalid_message = object()
        skipped_message = object()
        calls = iter([invalid_message, skipped_message, None])

        def consume_once_then_stop(timeout):
            message = next(calls)
            if message is None:
                gateway.running = False
            return message

        kafka_consumer.consume_message.side_effect = consume_once_then_stop
        kafka_consumer.parse_message.side_effect = [
            ("agent-decision-1", {"message_type": "unknown"}, None),
            (
                "agent-decision-1",
                {
                    "message_type": "decision_results",
                    "license_plate": "AA-11-BB",
                    "license_crop_url": "license.jpg",
                    "un": "1203",
                    "kemler": "33",
                    "hazard_crop_url": "hazard.jpg",
                    "alerts": [],
                    "route": "A1",
                    "decision": "SKIPPED",
                    "decision_reason": "not enough confidence",
                    "decision_source": "agent",
                },
                "truck-1",
            ),
        ]
        gateway._handle_decision = MagicMock()
        gateway.running = True

        gateway._consumer_loop()

        kafka_consumer.clear_stale_messages.assert_called_once()
        gateway._handle_decision.assert_not_called()
