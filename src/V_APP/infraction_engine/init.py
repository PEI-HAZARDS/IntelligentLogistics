import os
import signal
import sys
import logging

# Prometheus metrics
from prometheus_client import start_http_server, Counter, Histogram, Gauge  # type: ignore

# Auto-configure PYTHONPATH for local execution
# This ensures it works both in Docker (/app) and locally
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(current_dir)  # Go up to 'src/'
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

logger = logging.getLogger("init")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s – %(message)s",
    handlers=[logging.StreamHandler()]
)

# Prometheus metrics
METRICS_PORT = int(os.getenv("METRICS_PORT", 8002))
INFRACTIONS_TOTAL = Counter('infractions_total', 'Total infraction evaluations', ['result'])
INFRACTION_TIME = Histogram('infraction_processing_seconds', 'Infraction processing time in seconds')
ENGINE_UP = Gauge('infraction_engine_up', 'Infraction engine is running')

from infraction_engine.src.infraction_engine import InfractionEngine

def main():
    # Start Prometheus metrics server
    logger.info(f"Starting Prometheus metrics server on port {METRICS_PORT}")
    start_http_server(METRICS_PORT)
    ENGINE_UP.set(1)
    
    infraction_engine = InfractionEngine()
    
    # Register signal handler for graceful shutdown
    def signal_handler(sig, frame):
        logger.info("\nKeyboard interrupt received, stopping agent...")
        ENGINE_UP.set(0)
        infraction_engine.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        infraction_engine.start()
    except KeyboardInterrupt:
        logger.info("\nKeyboard interrupt received, stopping agent...")
        ENGINE_UP.set(0)
        infraction_engine.stop()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        ENGINE_UP.set(0)
        infraction_engine.stop()
        raise

if __name__ == "__main__":
    main()
