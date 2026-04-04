from collections import defaultdict
from typing import Dict, Set
import logging

from fastapi import WebSocket # type: ignore

logger = logging.getLogger("websocket_manager")

class WebSocketManager:
    """
    Maintains two WebSocket registries:
      _connections        : Dict[gate_id, Set[WebSocket]]   — gate operators / kiosk UIs
      _driver_connections : Dict[drivers_license, Set[WebSocket]] — driver mobile app
    """

    def __init__(self) -> None:
        self._connections: Dict[str, Set[WebSocket]] = defaultdict(set)
        self._driver_connections: Dict[str, Set[WebSocket]] = defaultdict(set)

    async def connect(self, gate_id: str, websocket: WebSocket) -> None:
        """
        Registers a WebSocket as connected to a specific gate.
        """
        gate_id = str(gate_id).strip()
        await websocket.accept()
        self._connections[gate_id].add(websocket)
        logger.info(
            f"Registered connection for gate '{gate_id}'. "
            f"Total connections: {len(self._connections[gate_id])}"
        )

    def disconnect(self, gate_id: str, websocket: WebSocket) -> None:
        """
        Removes a WebSocket from the list when the client closes the connection.
        """
        try:
            gate_id = str(gate_id).strip()
            conns = self._connections.get(gate_id, set())
            conns.discard(websocket)
            if not conns:
                # If the set is empty, remove the key
                self._connections.pop(gate_id, None)
            logger.info(
                f"Disconnected from gate '{gate_id}'. "
                f"Remaining: {len(self._connections.get(gate_id, set()))}"
            )
        except Exception:
            pass  # fail silent

    async def connect_driver(self, drivers_license: str, websocket: WebSocket) -> None:
        """Registers a driver WebSocket keyed by drivers_license."""
        key = drivers_license.strip()
        await websocket.accept()
        self._driver_connections[key].add(websocket)
        logger.info(
            f"Registered driver connection for '{key}'. "
            f"Total: {len(self._driver_connections[key])}"
        )

    def disconnect_driver(self, drivers_license: str, websocket: WebSocket) -> None:
        """Removes a driver WebSocket."""
        try:
            key = drivers_license.strip()
            conns = self._driver_connections.get(key, set())
            conns.discard(websocket)
            if not conns:
                self._driver_connections.pop(key, None)
            logger.info(f"Driver '{key}' disconnected.")
        except Exception:
            pass

    async def broadcast_to_driver(self, drivers_license: str, message: dict) -> None:
        """Sends a JSON message to a specific driver."""
        key = drivers_license.strip()
        conns = list(self._driver_connections.get(key, []))
        logger.info(f"Broadcasting to driver '{key}': {len(conns)} connection(s)")
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.error(f"Failed to send to driver '{key}': {e}")
                self.disconnect_driver(key, ws)

    async def broadcast(self, gate_ids: str | list[str], message: dict) -> None:
        """
        Sends a JSON message to one or multiple gates.
        Accepts:
          - gate_ids as str   -> single gate
          - gate_ids as list  -> multiple gates
        """
        if isinstance(gate_ids, str):
            raw_gate_ids = [gate_ids]
        else:
            raw_gate_ids = gate_ids

    
        normalized_gates = [str(gid).strip() for gid in raw_gate_ids if str(gid).strip()]
        unique_gates = list(dict.fromkeys(normalized_gates))

        if not unique_gates:
            logger.warning("broadcast called with no valid gate IDs")
            return

        logger.info(f"Broadcasting to gates {unique_gates}. All gates: {list(self._connections.keys())}")

        for gate_id in unique_gates:
            conns = list(self._connections.get(gate_id, []))
            logger.info(f"Gate '{gate_id}': {len(conns)} connections")

            for ws in conns:
                try:
                    await ws.send_json(message)
                    logger.info(f"Sent message to WebSocket for gate '{gate_id}'")
                except Exception as e:
                    logger.error(f"Failed to send to WebSocket: {e}")
                    self.disconnect(gate_id, ws)