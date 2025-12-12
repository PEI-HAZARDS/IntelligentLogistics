from fastapi import APIRouter, WebSocket, WebSocketDisconnect

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

    # Registar ligação no hub
    await decisions_hub.connect(gate_id, websocket)

    try:
        # Mantém a ligação aberta.
        # Se quiseres, podes tratar mensagens vindas do cliente aqui (pings, etc.).
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        # Remover do hub quando o cliente se desconecta
        decisions_hub.disconnect(gate_id, websocket)
    except Exception:
        # Qualquer outro erro também encerra a ligação
        decisions_hub.disconnect(gate_id, websocket)
