from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from web_socket_manager import WebSocketManager

router = APIRouter(tags=["realtime"])


def _get_ws_manager(websocket: WebSocket) -> WebSocketManager:
    """Retrieve the shared WebSocketManager for decisions from app.state."""
    return websocket.app.state.ws_manager


def _get_stream_ws_manager(websocket: WebSocket) -> WebSocketManager:
    """Retrieve the shared WebSocketManager for stream scale events from app.state."""
    return websocket.app.state.stream_ws_manager


@router.websocket("/ws/decisions/{gate_id}")
async def ws_decisions(websocket: WebSocket, gate_id: str):
    """
    WebSocket para o operador de um gate específico.

    - O frontend liga-se a:
        ws://<gateway>/api/ws/decisions/{gate_id}

    - Recebe: decision_results (agent-decision, operator-decision)
    """
    ws_manager = _get_ws_manager(websocket)

    origin = websocket.headers.get("origin", "unknown")
    logger.info(f"WebSocket [decisions] connection attempt from origin: {origin}, gate_id: {gate_id}")

    await ws_manager.connect(gate_id, websocket)
    logger.info(f"WebSocket [decisions] connected for gate {gate_id}")

    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received from client [decisions] (gate {gate_id}): {data}")
    except WebSocketDisconnect:
        logger.info(f"WebSocket [decisions] disconnected for gate {gate_id}")
        ws_manager.disconnect(gate_id, websocket)
    except Exception as e:
        logger.error(f"WebSocket [decisions] error for gate {gate_id}: {e}")
        ws_manager.disconnect(gate_id, websocket)


@router.websocket("/ws/stream/{gate_id}")
async def ws_stream(websocket: WebSocket, gate_id: str):
    """
    WebSocket para o HLS player — recebe eventos de stream scale.

    - O frontend liga-se a:
        ws://<gateway>/api/ws/stream/{gate_id}

    - Recebe: stream_scale events (scale_up / scale_down)
    """
    stream_ws_manager = _get_stream_ws_manager(websocket)

    origin = websocket.headers.get("origin", "unknown")
    logger.info(f"WebSocket [stream] connection attempt from origin: {origin}, gate_id: {gate_id}")

    await stream_ws_manager.connect(gate_id, websocket)
    logger.info(f"WebSocket [stream] connected for gate {gate_id}")

    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received from client [stream] (gate {gate_id}): {data}")
    except WebSocketDisconnect:
        logger.info(f"WebSocket [stream] disconnected for gate {gate_id}")
        stream_ws_manager.disconnect(gate_id, websocket)
    except Exception as e:
        logger.error(f"WebSocket [stream] error for gate {gate_id}: {e}")
        stream_ws_manager.disconnect(gate_id, websocket)
