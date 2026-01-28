from collections import defaultdict
from typing import Dict, Set

from fastapi import WebSocket
from loguru import logger


class DecisionsHub:
    """
    Mantém uma lista de WebSockets ligados ao Gateway para receber
    notificações em tempo real.

    Estrutura interna:
      _connections : Dict[str, Set[WebSocket]]

    Onde a chave é o gate_id e o valor é um conjunto de WebSockets
    que pertencem a utilizadores nesse gate.
    """

    def __init__(self) -> None:
        self._connections: Dict[str, Set[WebSocket]] = defaultdict(set)

    async def connect(self, gate_id: str, websocket: WebSocket) -> None:
        """
        Regista um WebSocket como estando ligado a um determinado gate.
        """
        await websocket.accept()
        self._connections[gate_id].add(websocket)
        logger.info(f"[Hub] Registered connection for gate '{gate_id}'. Total connections: {len(self._connections[gate_id])}")

    def disconnect(self, gate_id: str, websocket: WebSocket) -> None:
        """
        Remove um WebSocket da lista quando o cliente fecha a ligação.
        """
        try:
            conns = self._connections.get(gate_id, set())
            conns.discard(websocket)
            if not conns:
                # Se ficou vazio, removemos a chave
                self._connections.pop(gate_id, None)
            logger.info(f"[Hub] Disconnected from gate '{gate_id}'. Remaining: {len(self._connections.get(gate_id, set()))}")
        except Exception:
            pass  # fail silent

    async def broadcast_to_gate(self, gate_id: str, message: dict) -> None:
        """
        Envia uma mensagem JSON para todos os WebSockets ligados
        ao mesmo gate_id.
        """
        conns = list(self._connections.get(gate_id, []))
        logger.info(f"[Hub] Broadcasting to gate '{gate_id}': {len(conns)} connections. All gates: {list(self._connections.keys())}")

        for ws in conns:
            try:
                await ws.send_json(message)
                logger.info(f"[Hub] Sent message to WebSocket for gate '{gate_id}'")
            except Exception as e:
                # Se der erro ao enviar, desligar o websocket
                logger.error(f"[Hub] Failed to send to WebSocket: {e}")
                self.disconnect(gate_id, ws)


# Instância global usada pelo resto do gateway
decisions_hub = DecisionsHub()
