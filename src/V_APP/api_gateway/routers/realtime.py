from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from realtime.hub import decisions_hub

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/decisions/{gate_id}")
async def ws_decisions(websocket: WebSocket, gate_id: str):
    """
    WebSocket para o operador de um gate específico.

    - O frontend liga-se a:
        ws://<gateway>/api/ws/decisions/{gate_id}

      Exemplo:
        ws://localhost:8000/api/ws/decisions/1
        ws://gateway.mydomain.com/api/ws/decisions/global   (se quiser ouvir tudo)

    - O gateway regista esta ligação no DecisionsHub.
    - Quando chegar uma mensagem Kafka com esse gate_id, o hub envia:
        {
          "type": "decision_update",
          "payload": { ...mensagem original do Kafka... }
        }
    """
    # Log connection attempt with origin
    origin = websocket.headers.get("origin", "unknown")
    logger.info(f"WebSocket connection attempt from origin: {origin}, gate_id: {gate_id}")

    # Registar ligação no hub (this calls websocket.accept())
    await decisions_hub.connect(gate_id, websocket)
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
        decisions_hub.disconnect(gate_id, websocket)
    except Exception as e:
        # Qualquer outro erro também encerra a ligação
        logger.error(f"WebSocket error for gate {gate_id}: {e}")
        decisions_hub.disconnect(gate_id, websocket)
