import os
import signal
import sys
import logging

# Prometheus metrics
from prometheus_client import start_http_server, Counter, Histogram, Gauge

# Auto-configure PYTHONPATH for local execution
# This ensures it works both in Docker (/app) and locally
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(current_dir)  # Go up to 'src/'
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

logger = logging.getLogger("init-DecisionEngine")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s – %(message)s",
    handlers=[logging.StreamHandler()]
)

# Prometheus metrics
METRICS_PORT = int(os.getenv("METRICS_PORT", 8001))
DECISIONS_TOTAL = Counter('decisions_total', 'Total decisions made', ['decision_type'])
DECISION_TIME = Histogram('decision_processing_seconds', 'Decision processing time in seconds')
ENGINE_UP = Gauge('decision_engine_up', 'Decision engine is running')

from decision_engine_microservice.src.DecisionEngine import DecisionEngine

def main():
    # Start Prometheus metrics server
    logger.info(f"[init] Starting Prometheus metrics server on port {METRICS_PORT}")
    start_http_server(METRICS_PORT)
    ENGINE_UP.set(1)
    
    decision_engine = DecisionEngine()
    
    # Register signal handler for graceful shutdown
    def signal_handler(sig, frame):
        logger.info("\n[init] Keyboard interrupt received, stopping agent...")
        ENGINE_UP.set(0)
        decision_engine.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        decision_engine._loop()
    except KeyboardInterrupt:
        logger.info("\n[init] Keyboard interrupt received, stopping agent...")
        ENGINE_UP.set(0)
        decision_engine.stop()
    except Exception as e:
        logger.error(f"[init] Unexpected error: {e}")
        ENGINE_UP.set(0)
        decision_engine.stop()
        raise

if __name__ == "__main__":
    main()