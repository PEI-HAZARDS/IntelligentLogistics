from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from web_socket_manager import WebSocketManager

router = APIRouter(tags=["realtime"])


def _get_ws_manager(websocket: WebSocket) -> WebSocketManager:
    """Retrieve the shared WebSocketManager from app.state."""
    return websocket.app.state.ws_manager


@router.websocket("/ws/decisions/{gate_id}")
async def ws_decisions(websocket: WebSocket, gate_id: str):
    """
    WebSocket para o operador de um gate específico.

    - O frontend liga-se a:
        ws://<gateway>/api/ws/decisions/{gate_id}

      Exemplo:
        ws://localhost:8000/api/ws/decisions/1
        ws://gateway.mydomain.com/api/ws/decisions/global   (se quiser ouvir tudo)

    - O gateway regista esta ligação no WebSocketManager.
    - Quando chegar uma mensagem Kafka com esse gate_id, o hub envia:
        {
          "type": "decision_update",
          "payload": { ...mensagem original do Kafka... }
        }
    """
    ws_manager = _get_ws_manager(websocket)

    # Log connection attempt with origin
    origin = websocket.headers.get("origin", "unknown")
    logger.info(f"WebSocket connection attempt from origin: {origin}, gate_id: {gate_id}")

    # Registar ligação no hub (this calls websocket.accept())
    await ws_manager.connect(gate_id, websocket)
    logger.info(f"WebSocket connected for gate {gate_id}")

    try:
        # Mantém a ligação aberta.
        # Se quiseres, podes tratar mensagens vindas do cliente aqui (pings, etc.).
        while True:
            # Wait for messages from client (ping/pong, etc.)
            data = await websocket.receive_text()
            logger.debug(f"Received from client (gate {gate_id}): {data}")
    except WebSocketDisconnect:
        # Remover do hub quando o cliente se desconecta
        logger.info(f"WebSocket disconnected for gate {gate_id}")
        ws_manager.disconnect(gate_id, websocket)
    except Exception as e:
        # Qualquer outro erro também encerra a ligação
        logger.error(f"WebSocket error for gate {gate_id}: {e}")
        ws_manager.disconnect(gate_id, websocket)
