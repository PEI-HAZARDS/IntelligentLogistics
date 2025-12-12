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

from agentB_microservice.src.AgentB import AgentB

# Files to download (name, Google Drive ID, destination folder)
FILE_NAME = "license_plate_model.pt"
FILE_ID = "1h3AXDLcFj17kXo7L20jQeId-upQovGQu"
NEW_DIR = "data"

logger = logging.getLogger("init-AgentB")


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
        url = f"https://drive.google.com/uc?id={FILE_ID}"
        logger.info(f"[init] Downloading {FILE_NAME} to {NEW_DIR}...")
        gdown.download(url, dest_path, quiet=False)

    logger.info("[init] All files ready!")


def main():
    setup()
    
    logger.info("[init] Creating AgentB instance...")
    agent = AgentB()
    
    # Reset logging level AFTER AgentB is created
    # PaddleOCR overrides it during OCR() initialization
    logging.getLogger().setLevel(logging.INFO)
    
    logger.info("[init] AgentB instance created!")
    
    # Register signal handler for graceful shutdown
    def signal_handler(sig, frame):
        logger.info("\n[init] Keyboard interrupt received, stopping agent...")
        agent.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        logger.info("[init] Starting AgentB main loop...")
        agent._loop()
    except KeyboardInterrupt:
        logger.info("\n[init] Keyboard interrupt received, stopping agent...")
        agent.stop()
    except Exception as e:
        logger.info(f"[init] Unexpected error: {e}")
        agent.stop()
        raise

if __name__ == "__main__":
    main()