"""
Unit tests for WebSocketManager.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from V_APP.api_gateway.src.web_socket_manager import WebSocketManager


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def ws_manager():
    return WebSocketManager()


def make_websocket():
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


# ═══════════════════════════════════════════════════════════════════
# Connect
# ═══════════════════════════════════════════════════════════════════

class TestConnect:
    def test_registers_websocket(self, ws_manager):
        async def _run():
            ws = make_websocket()
            await ws_manager.connect("gate-1", ws)
            assert ws in ws_manager._connections["gate-1"]
            ws.accept.assert_awaited_once()
        asyncio.run(_run())

    def test_multiple_connections_same_gate(self, ws_manager):
        async def _run():
            ws1 = make_websocket()
            ws2 = make_websocket()
            await ws_manager.connect("gate-1", ws1)
            await ws_manager.connect("gate-1", ws2)
            assert len(ws_manager._connections["gate-1"]) == 2
        asyncio.run(_run())

    def test_multiple_gates(self, ws_manager):
        async def _run():
            ws1 = make_websocket()
            ws2 = make_websocket()
            await ws_manager.connect("gate-1", ws1)
            await ws_manager.connect("gate-2", ws2)
            assert len(ws_manager._connections["gate-1"]) == 1
            assert len(ws_manager._connections["gate-2"]) == 1
        asyncio.run(_run())


# ═══════════════════════════════════════════════════════════════════
# Disconnect
# ═══════════════════════════════════════════════════════════════════

class TestDisconnect:
    def test_removes_websocket(self, ws_manager):
        async def _run():
            ws = make_websocket()
            await ws_manager.connect("gate-1", ws)
            ws_manager.disconnect("gate-1", ws)
            assert ws not in ws_manager._connections.get("gate-1", set())
        asyncio.run(_run())

    def test_removes_gate_key_when_empty(self, ws_manager):
        async def _run():
            ws = make_websocket()
            await ws_manager.connect("gate-1", ws)
            ws_manager.disconnect("gate-1", ws)
            assert "gate-1" not in ws_manager._connections
        asyncio.run(_run())

    def test_disconnect_unknown_gate(self, ws_manager):
        ws = make_websocket()
        ws_manager.disconnect("nonexistent", ws)  # Should not raise

    def test_disconnect_keeps_other_connections(self, ws_manager):
        async def _run():
            ws1 = make_websocket()
            ws2 = make_websocket()
            await ws_manager.connect("gate-1", ws1)
            await ws_manager.connect("gate-1", ws2)
            ws_manager.disconnect("gate-1", ws1)
            assert ws2 in ws_manager._connections["gate-1"]
            assert ws1 not in ws_manager._connections["gate-1"]
        asyncio.run(_run())


# ═══════════════════════════════════════════════════════════════════
# Broadcast
# ═══════════════════════════════════════════════════════════════════

class TestBroadcastToGate:
    def test_sends_to_all_connections(self, ws_manager):
        async def _run():
            ws1 = make_websocket()
            ws2 = make_websocket()
            await ws_manager.connect("gate-1", ws1)
            await ws_manager.connect("gate-1", ws2)
            message = {"type": "test", "data": 123}
            await ws_manager.broadcast_to_gate("gate-1", message)
            ws1.send_json.assert_awaited_once_with(message)
            ws2.send_json.assert_awaited_once_with(message)
        asyncio.run(_run())

    def test_no_connections(self, ws_manager):
        asyncio.run(ws_manager.broadcast_to_gate("gate-1", {"test": True}))

    def test_failed_send_disconnects(self, ws_manager):
        async def _run():
            ws = make_websocket()
            ws.send_json.side_effect = Exception("Connection closed")
            await ws_manager.connect("gate-1", ws)
            await ws_manager.broadcast_to_gate("gate-1", {"test": True})
            assert ws not in ws_manager._connections.get("gate-1", set())
        asyncio.run(_run())

    def test_does_not_send_to_other_gates(self, ws_manager):
        async def _run():
            ws1 = make_websocket()
            ws2 = make_websocket()
            await ws_manager.connect("gate-1", ws1)
            await ws_manager.connect("gate-2", ws2)
            await ws_manager.broadcast_to_gate("gate-1", {"test": True})
            ws1.send_json.assert_awaited_once()
            ws2.send_json.assert_not_awaited()
        asyncio.run(_run())
