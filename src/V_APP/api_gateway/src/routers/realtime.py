from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import logging

from web_socket_manager import WebSocketManager
from auth.token_validator import validate_ws_token

router = APIRouter(tags=["realtime"])
logger = logging.getLogger("WebSocketRouter")

def _get_ws_manager(websocket: WebSocket) -> WebSocketManager:
    """Retrieve the shared (unified) WebSocketManager from app.state."""
    return websocket.app.state.ws_manager

@router.websocket("/ws/gate/{gate_id}")
async def ws_gate(websocket: WebSocket, gate_id: str, token: str = Query(default=None)):
    """
    Unified WebSocket for a specific gate operator.
    Receives all real-time events: decisions, scale changes, and infractions.
    Requires a valid token as a query parameter.
    """
    # Validate token before accepting the connection
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return
    try:
        user = validate_ws_token(websocket, token)
        if "operator" not in user.roles and "manager" not in user.roles:
            await websocket.close(code=4003, reason="Insufficient permissions")
            return
    except Exception:
        await websocket.close(code=4001, reason="Invalid authentication token")
        return

    ws_manager = _get_ws_manager(websocket)

    origin = websocket.headers.get("origin", "unknown")
    logger.info(f"WebSocket connection attempt for gate {gate_id} from origin: {origin}")

    await ws_manager.connect(gate_id, websocket)
    logger.info(f"WebSocket connected for gate {gate_id} (user: {user.sub})")

    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received from client (gate {gate_id}): {data}")
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for gate {gate_id}")
        ws_manager.disconnect(gate_id, websocket)
    except Exception as e:
        logger.error(f"WebSocket error for gate {gate_id}: {e}")
        ws_manager.disconnect(gate_id, websocket)


@router.websocket("/ws/driver/{drivers_license}")
async def ws_driver(websocket: WebSocket, drivers_license: str, token: str = Query(default=None)):
    """
    Driver-scoped WebSocket for the mobile app.
    Receives status_changed events targeted at this specific driver.
    Requires a valid token as a query parameter.
    """
    # Validate token before accepting the connection
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return
    try:
        user = validate_ws_token(websocket, token)
        if "driver" not in user.roles:
            await websocket.close(code=4003, reason="Insufficient permissions")
            return
        # Ensure the driver can only connect to their own channel
        if user.sub != drivers_license:
            await websocket.close(code=4003, reason="Cannot subscribe to another driver's channel")
            return
    except Exception:
        await websocket.close(code=4001, reason="Invalid authentication token")
        return

    ws_manager = _get_ws_manager(websocket)
    await ws_manager.connect_driver(drivers_license, websocket)
    logger.info(f"Driver WebSocket connected for '{drivers_license}'")

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info(f"Driver WebSocket disconnected for '{drivers_license}'")
        ws_manager.disconnect_driver(drivers_license, websocket)
    except Exception as e:
        logger.error(f"Driver WebSocket error for '{drivers_license}': {e}")
        ws_manager.disconnect_driver(drivers_license, websocket)
