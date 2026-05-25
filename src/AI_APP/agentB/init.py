import os
import sys

# Auto-configure PYTHONPATH for local execution
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(current_dir)  # Go up to 'src/'
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

import logging
import signal

# Prometheus metrics
from prometheus_client import start_http_server, Counter, Histogram, Gauge  # type: ignore

from agentB.src.agentB import AgentB
from agentB.setup import setup

logger = logging.getLogger("init-AgentB")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s – %(message)s",
    handlers=[logging.StreamHandler()]
)

# Prometheus metrics
METRICS_PORT = int(os.getenv("METRICS_PORT", 8000))
MESSAGES_PROCESSED = Counter('agent_messages_processed_total', 'Total messages processed', ['agent', 'status'])
INFERENCE_TIME = Histogram('agent_inference_seconds', 'Inference time in seconds', ['agent'])
AGENT_UP = Gauge('agent_up', 'Agent is running', ['agent'])


def main():
    # Start Prometheus metrics server
    logger.info(f"Starting Prometheus metrics server on port {METRICS_PORT}")
    start_http_server(METRICS_PORT)
    AGENT_UP.labels(agent='agent-b').set(1)

    setup()

    logger.info("Creating AgentB instance...")
    agent = AgentB()

    # Reset logging level AFTER AgentB is created
    # PaddleOCR overrides it during OCR() initialization
    logging.getLogger().setLevel(logging.INFO)

    logger.info("AgentB instance created!")

    # Register signal handler for graceful shutdown
    def signal_handler(sig, frame):
        logger.info("\nSignal received, stopping agent...")
        AGENT_UP.labels(agent='agent-b').set(0)
        agent.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        logger.info("Starting AgentB main loop...")
        agent.start()
    except KeyboardInterrupt:
        logger.info("\nKeyboard interrupt received, stopping agent...")
        AGENT_UP.labels(agent='agent-b').set(0)
        agent.stop()
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        AGENT_UP.labels(agent='agent-b').set(0)
        agent.stop()
        raise


if __name__ == "__main__":
    main()