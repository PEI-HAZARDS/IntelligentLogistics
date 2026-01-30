import os
import sys

# Auto-configure PYTHONPATH for local execution
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(current_dir)  # Go up to 'src/'
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s – %(message)s",
    handlers=[logging.StreamHandler()]
)


import gdown  # type: ignore
import signal

# Prometheus metrics
from prometheus_client import start_http_server, Counter, Histogram, Gauge # type: ignore

from agentC.src.agentC import AgentC

# Files to download (name, Google Drive ID, destination folder)
FILE_NAME = "hazard_plate_model.pt"
FILE_ID = "1Dx1XS4pALjzP6AN5ryAJXA7sJ4KgH4JD"
FILE_ID_V2 = "12Y0Knu9J-yLIlKGhowg_iKVCBt59jZwe"
NEW_DIR = "data"

logger = logging.getLogger("init-AgentC")

# Prometheus metrics
METRICS_PORT = int(os.getenv("METRICS_PORT", 8000))
MESSAGES_PROCESSED = Counter('agent_messages_processed_total', 'Total messages processed', ['agent', 'status'])
INFERENCE_TIME = Histogram('agent_inference_seconds', 'Inference time in seconds', ['agent'])
AGENT_UP = Gauge('agent_up', 'Agent is running', ['agent'])


def setup():
    logger.info("[init] Downloading models from Google Drive")
    base_dir = os.path.dirname(__file__)

    # Build the full destination directory path
    dest_dir = os.path.join(base_dir, NEW_DIR)
    os.makedirs(dest_dir, exist_ok=True)

    dest_path = os.path.join(dest_dir, FILE_NAME)
    if os.path.exists(dest_path):
        logger.info(f"[init] {FILE_NAME} already exists in {NEW_DIR} — skipping.")
    else:
        url = f"https://drive.google.com/uc?id={FILE_ID_V2}"
        logger.info(f"[init] Downloading {FILE_NAME} to {NEW_DIR}...")
        gdown.download(url, dest_path, quiet=False)

    logger.info("[init] All files ready!")


def main():
    # Start Prometheus metrics server
    logger.info(f"[init] Starting Prometheus metrics server on port {METRICS_PORT}")
    start_http_server(METRICS_PORT)
    AGENT_UP.labels(agent='agent-c').set(1)
    
    setup()
    
    logger.info("[init] Creating AgentC instance...")
    agent = AgentC()

    # Reset logging level AFTER AgentC is created
    # PaddleOCR overrides it during OCR() initialization
    logging.getLogger().setLevel(logging.INFO)
    
    logger.info("[init] AgentC instance created!")
    
    # Register signal handler for graceful shutdown
    def signal_handler(sig, frame):
        logger.info("\n[init] Keyboard interrupt received, stopping agent...")
        AGENT_UP.labels(agent='agent-c').set(0)
        agent.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        logger.info("[init] Starting AgentC main loop...")
        agent.loop()
    except KeyboardInterrupt:
        logger.info("\n[init] Keyboard interrupt received, stopping agent...")
        AGENT_UP.labels(agent='agent-c').set(0)
        agent.stop()
    except Exception as e:
        logger.info(f"[init] Unexpected error: {e}")
        AGENT_UP.labels(agent='agent-c').set(0)
        agent.stop()
        raise

if __name__ == "__main__":
    main()