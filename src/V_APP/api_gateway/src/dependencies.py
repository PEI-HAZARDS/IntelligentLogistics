from fastapi import Request # type: ignore
from shared.src.kafka_wrapper import KafkaProducerWrapper
from web_socket_manager import WebSocketManager
from auth.keycloak_client import KeycloakClient
from auth.token_validator import get_current_user, require_role, TokenPayload  # noqa: F401 — re-exported


def get_kafka_producer(request: Request) -> KafkaProducerWrapper:
    """FastAPI dependency — retrieves the Kafka producer from app.state."""
    return request.app.state.kafka_producer


def get_mediamtx_webrtc_internal_url(request: Request) -> str:
    """FastAPI dependency — internal MediaMTX WebRTC/WHEP base URL (server-to-server)."""
    return request.app.state.mediamtx_webrtc_internal_url


def get_mediamtx_hls_internal_url(request: Request) -> str:
    """FastAPI dependency — internal MediaMTX HLS base URL (server-to-server)."""
    return request.app.state.mediamtx_hls_internal_url


def get_minio_internal_url(request: Request) -> str:
    """FastAPI dependency — internal MinIO base URL (server-to-server, no S3 signing)."""
    return request.app.state.minio_internal_url


def get_api_prefix(request: Request) -> str:
    """FastAPI dependency — API mount prefix used to build client-facing paths."""
    return request.app.state.api_prefix


def get_data_module_url(request: Request) -> str:
    """FastAPI dependency — retrieves the Data Module URL from app.state."""
    return request.app.state.data_module_url


def get_ws_manager(request: Request) -> WebSocketManager:
    """FastAPI dependency — retrieves the WebSocketManager from app.state."""
    return request.app.state.ws_manager


def get_keycloak_client(request: Request) -> KeycloakClient:
    """FastAPI dependency — retrieves the KeycloakClient from app.state."""
    return request.app.state.keycloak_client

