import gdown  # type: ignore
import logging
import os
from agentB_microservice.src.AgentB import AgentB

# Files to download (name, Google Drive ID, destination folder)
FILE_NAME = "license_plate_model.pt"
FILE_ID = "1h3AXDLcFj17kXo7L20jQeId-upQovGQu"
NEW_DIR = "data"

logger = logging.getLogger("setup-AgentB")


def setup():
    logger.info("[setup] Downloading models from Google Drive")
    base_dir = os.path.dirname(__file__)

    # Build the full destination directory path
    dest_dir = os.path.join(base_dir, NEW_DIR)
    os.makedirs(dest_dir, exist_ok=True)

    dest_path = os.path.join(dest_dir, FILE_NAME)
    if os.path.exists(dest_path):
        logger.info(f"[setup] {FILE_NAME} already exists in {NEW_DIR} — skipping.")
    else:
        url = f"https://drive.google.com/uc?id={FILE_ID}"
        logger.info(f"[setup] Downloading {FILE_NAME} to {NEW_DIR}...")
        gdown.download(url, dest_path, quiet=False)

    logger.info("[setup] All files ready!")

if __name__ == "__main__":
    setup()