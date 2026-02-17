"""
Entrypoint for the API Gateway.

Used by the Dockerfile CMD:
    uvicorn main:app --host 0.0.0.0 --port 8000

Since the APIGateway class manages its own Kafka consumer thread,
we use the lifespan context to start/stop it alongside uvicorn.
"""
import asyncio
import logging
import threading

from api_gateway import APIGateway

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-18s | %(levelname)-7s | %(message)s",
)

# Create the gateway instance (reads config from env vars)
gateway = APIGateway(kafka_producer=None, kafka_consumer=None, WSManager=None)

# Expose the FastAPI app for uvicorn
app = gateway.app


@app.on_event("startup")
async def on_startup():
    """Start the Kafka consumer thread when uvicorn starts."""
    gateway.running = True
    gateway._loop = asyncio.get_running_loop()
    gateway._consumer_thread = threading.Thread(
        target=gateway._consumer_loop,
        name="api-gateway-consumer",
        daemon=True,
    )
    gateway._consumer_thread.start()
    logging.getLogger("APIGateway").info("Kafka consumer thread started")


@app.on_event("shutdown")
async def on_shutdown():
    """Stop the Kafka consumer thread when uvicorn shuts down."""
    gateway.stop()
