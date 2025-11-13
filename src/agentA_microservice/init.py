import os
import gdown  # type: ignore
import signal
import sys
import logging

# Auto-configure PYTHONPATH for local execution
# This ensures it works both in Docker (/app) and locally
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(current_dir)  # Go up to 'src/'
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s – %(message)s",
    handlers=[logging.StreamHandler()]
)

from agentA_microservice.src.AgentA import AgentA

# Files to download (name, Google Drive ID, destination folder)
FILE_NAME = "truck_model.pt"
FILE_ID = "1LL0zMJrppkqd51zQDLixzlOIJvwlMDXe"
NEW_DIR = "data"

logger = logging.getLogger("init-AgentA")


def setup():
    logger.info("[init] Downloading models from Google Drive")
    base_dir = os.path.dirname(__file__)

   
    # Build the full destination directory path
    dest_dir = os.path.join(base_dir, NEW_DIR)
    os.makedirs(dest_dir, exist_ok=True)

    dest_path = os.path.join(dest_dir, FILE_NAME)
    if os.path.exists(dest_path):
        print(f"[init] {FILE_NAME} already exists in {NEW_DIR} — skipping.")
    else:
        url = f"https://drive.google.com/uc?id={FILE_ID}"
        logger.info(f"[init] Downloading {FILE_NAME} to {NEW_DIR}...")
        gdown.download(url, dest_path, quiet=False)

    logger.info("[init] All files ready!")


def main():
    setup()
    agent = AgentA()
    
    # Register signal handler for graceful shutdown
    def signal_handler(sig, frame):
        logger.info("\n[init] Keyboard interrupt received, stopping agent...")
        agent.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        agent._loop()
    except KeyboardInterrupt:
        logger.info("\n[init] Keyboard interrupt received, stopping agent...")
        agent.stop()
    except Exception as e:
        logger.error(f"[init] Unexpected error: {e}")
        agent.stop()
        raise

if __name__ == "__main__":
    main()