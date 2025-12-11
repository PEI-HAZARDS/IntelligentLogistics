from typing import Dict, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings

settings = get_settings()


# ---------- WebSocket Connection Manager ----------
class ConnectionManager:
    """Manages WebSocket connections for real-time decision notifications."""
    
    def __init__(self):
        # gate_id -> list of connected WebSockets
        self.active_connections: Dict[int, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, gate_id: int):
        """Accept and register a new WebSocket connection for a gate."""
        await websocket.accept()
        if gate_id not in self.active_connections:
            self.active_connections[gate_id] = []
        self.active_connections[gate_id].append(websocket)
    
    def disconnect(self, websocket: WebSocket, gate_id: int):
        """Remove a WebSocket connection."""
        if gate_id in self.active_connections:
            if websocket in self.active_connections[gate_id]:
                self.active_connections[gate_id].remove(websocket)
    
    async def broadcast_to_gate(self, gate_id: int, message: dict):
        """Broadcast a message to all connections for a specific gate."""
        if gate_id in self.active_connections:
            for connection in self.active_connections[gate_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass  # Connection may have been closed
    
    async def broadcast_all(self, message: dict):
        """Broadcast a message to all connected clients."""
        for gate_id in self.active_connections:
            await self.broadcast_to_gate(gate_id, message)


# Global connection manager instance
ws_manager = ConnectionManager()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Port Logistics Management API",
        description="""
        Backend API for Port Logistics Management System.
        
        ## Features
        
        * **Authentication**: JWT-based worker authentication with role-based access
        * **Trucks & Drivers**: Manage truck and driver registrations
        * **Appointments**: Create, confirm, and validate time-window arrivals
        * **Gates & Visits**: Handle check-in/out with visit lifecycle tracking
        * **AI Recognition**: Ingest AI events with confidence handling and corrections
        * **Decisions**: Access decisions from Decision Engine with manual review
        * **Telemetry**: System resource metrics ingestion
        * **WebSocket**: Real-time decision notifications for drivers and operators
        
        ## Business Logic
        
        * Validates truck arrivals against CONFIRMED appointments within time window
        * Tracks dwell time using visit event logs
        * Auto-creates corrections for low-confidence AI detections
        * Broadcasts decisions to connected clients via WebSocket
        """,
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include API routes
    app.include_router(api_router)
    
    @app.get("/", tags=["Health"])
    async def root():
        """Root endpoint for health checks."""
        return {
            "status": "healthy",
            "service": "Port Logistics Management API",
            "version": "1.0.0"
        }
    
    @app.get("/health", tags=["Health"])
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy"}
    
    @app.websocket("/ws/gate/{gate_id}")
    async def websocket_gate(websocket: WebSocket, gate_id: int):
        """
        WebSocket endpoint for real-time decision notifications.
        
        Clients (driver apps, gate operator UIs) connect to receive:
        - New access decisions
        - Manual review updates
        - Gate status changes
        """
        await ws_manager.connect(websocket, gate_id)
        try:
            while True:
                # Wait for messages (keep connection alive)
                data = await websocket.receive_text()
                # Echo back for ping/pong heartbeat
                if data == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket, gate_id)
    
    return app


# Create the application instance
app = create_app()
