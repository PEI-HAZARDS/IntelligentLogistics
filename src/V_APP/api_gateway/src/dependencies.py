from fastapi import Request # type: ignore
from shared.src.kafka_wrapper import KafkaProducerWrapper
from web_socket_manager import WebSocketManager


def get_kafka_producer(request: Request) -> KafkaProducerWrapper:
    """FastAPI dependency — retrieves the Kafka producer from app.state."""
    return request.app.state.kafka_producer


def get_stream_base_url(request: Request) -> str:
    """FastAPI dependency — retrieves the stream base URL from app.state."""
    return request.app.state.stream_base_url


def get_stream_webrtc_base_url(request: Request) -> str:
    """FastAPI dependency — retrieves the WebRTC stream base URL from app.state."""
    return request.app.state.stream_webrtc_base_url


def get_data_module_url(request: Request) -> str:
    """FastAPI dependency — retrieves the Data Module URL from app.state."""
    return request.app.state.data_module_url


def get_ws_manager(request: Request) -> WebSocketManager:
    """FastAPI dependency — retrieves the WebSocketManager from app.state."""
    return request.app.state.ws_manager

