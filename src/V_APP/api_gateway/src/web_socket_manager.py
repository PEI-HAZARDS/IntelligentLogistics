from collections import defaultdict
from typing import Dict, Set
import logging

from fastapi import WebSocket # type: ignore

logger = logging.getLogger("websocket_manager")

class WebSocketManager:
    """
    Maintains a list of WebSockets connected to the Gateway to receive
    real-time notifications.

    Internal structure:
      _connections : Dict[str, Set[WebSocket]]

    Where the key is the gate_id and the value is a set of WebSockets
    belonging to users at that gate.
    """

    def __init__(self) -> None:
        self._connections: Dict[str, Set[WebSocket]] = defaultdict(set)

    async def connect(self, gate_id: str, websocket: WebSocket) -> None:
        """
        Registers a WebSocket as connected to a specific gate.
        """
        await websocket.accept()
        self._connections[gate_id].add(websocket)
        logger.info(f"Registered connection for gate '{gate_id}'. Total connections: {len(self._connections[gate_id])}")

    def disconnect(self, gate_id: str, websocket: WebSocket) -> None:
        """
        Removes a WebSocket from the list when the client closes the connection.
        """
        try:
            conns = self._connections.get(gate_id, set())
            conns.discard(websocket)
            if not conns:
                # If the set is empty, remove the key
                self._connections.pop(gate_id, None)
            logger.info(f"Disconnected from gate '{gate_id}'. Remaining: {len(self._connections.get(gate_id, set()))}")
        except Exception:
            pass  # fail silent

    async def broadcast_to_gate(self, gate_id: str, message: dict) -> None:
        """
        Sends a JSON message to all WebSockets connected
        to the same gate_id.
        """
        conns = list(self._connections.get(gate_id, []))
        logger.info(f"Broadcasting to gate '{gate_id}': {len(conns)} connections. All gates: {list(self._connections.keys())}")

        for ws in conns:
            try:
                await ws.send_json(message)
                logger.info(f"Sent message to WebSocket for gate '{gate_id}'")
            except Exception as e:
                # If sending fails, disconnect the websocket
                logger.error(f"Failed to send to WebSocket: {e}")
                self.disconnect(gate_id, ws)