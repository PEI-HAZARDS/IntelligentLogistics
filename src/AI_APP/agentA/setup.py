import os
import logging
import gdown  # type: ignore

# Files (name, Google Drive ID, destination folder)
FILE_NAME = "truck_model.pt"
FILE_ID = "1LL0zMJrppkqd51zQDLixzlOIJvwlMDXe"
NEW_DIR = "data"

logger = logging.getLogger("setup-AgentA")


def setup():
    logger.info("[setup] Downloading models from Google Drive")

    # Determine which folder the script is running in
    base_dir = os.path.dirname(__file__)

    # Create destination folder if it doesn't exist
    dest_dir = os.path.join(base_dir, NEW_DIR)
    os.makedirs(dest_dir, exist_ok=True)

    # Build the full path of the destination file
    dest_path = os.path.join(dest_dir, FILE_NAME)
    if os.path.exists(dest_path):
        print(f"[setup] {FILE_NAME} already exists in {NEW_DIR} — skipping.")
    else:
        url = f"https://drive.google.com/uc?id={FILE_ID}"
        logger.info(f"[setup] Downloading {FILE_NAME} to {NEW_DIR}...")
        gdown.download(url, dest_path, quiet=False)

    logger.info("[setup] All files ready!")

if __name__ == "__main__":
    setup()