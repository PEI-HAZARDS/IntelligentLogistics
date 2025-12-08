from collections import defaultdict
from typing import Dict, Set

from fastapi import WebSocket


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
        except Exception:
            pass  # fail silent

    async def broadcast_to_gate(self, gate_id: str, message: dict) -> None:
        """
        Envia uma mensagem JSON para todos os WebSockets ligados
        ao mesmo gate_id.
        """
        conns = list(self._connections.get(gate_id, []))

        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                # Se der erro ao enviar, desligar o websocket
                self.disconnect(gate_id, ws)


# Instância global usada pelo resto do gateway
decisions_hub = DecisionsHub()
