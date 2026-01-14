import os
import signal
import sys
import logging
import threading

# Prometheus metrics
from prometheus_client import start_http_server, Counter, Histogram, Gauge

# Auto-configure PYTHONPATH for local execution
# This ensures it works both in Docker (/app) and locally
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(current_dir)  # Go up to 'src/'
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

logger = logging.getLogger("init-AgentA")

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

from agentA_microservice.src.AgentA import AgentA

def main():
    # Start Prometheus metrics server
    logger.info(f"[init] Starting Prometheus metrics server on port {METRICS_PORT}")
    start_http_server(METRICS_PORT)
    AGENT_UP.labels(agent='agent-a').set(1)
    
    agent = AgentA()
    
    # Register signal handler for graceful shutdown
    def signal_handler(sig, frame):
        logger.info("\n[init] Keyboard interrupt received, stopping agent...")
        AGENT_UP.labels(agent='agent-a').set(0)
        agent.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        agent._loop()
    except KeyboardInterrupt:
        logger.info("\n[init] Keyboard interrupt received, stopping agent...")
        AGENT_UP.labels(agent='agent-a').set(0)
        agent.stop()
    except Exception as e:
        logger.error(f"[init] Unexpected error: {e}")
        AGENT_UP.labels(agent='agent-a').set(0)
        agent.stop()
        raise

if __name__ == "__main__":
    main()