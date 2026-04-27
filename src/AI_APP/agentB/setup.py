import gdown  # type: ignore
import logging
import os

# Files to download (name, Google Drive ID, destination folder)
FILES_TO_DOWNLOAD = [
    ("license_plate_model.pt", "1h3AXDLcFj17kXo7L20jQeId-upQovGQu"),
    ("truck_model.pt", "1LL0zMJrppkqd51zQDLixzlOIJvwlMDXe")
]
NEW_DIR = "data"

logger = logging.getLogger("setup-AgentB")


def setup():
    logger.info("[setup] Downloading models from Google Drive")
    base_dir = os.path.dirname(__file__)

    # Build the full destination directory path
    dest_dir = os.path.join(base_dir, NEW_DIR)
    os.makedirs(dest_dir, exist_ok=True)

    for file_name, file_id in FILES_TO_DOWNLOAD:
        dest_path = os.path.join(dest_dir, file_name)
        if os.path.exists(dest_path):
            logger.info(f"[setup] {file_name} already exists in {NEW_DIR} — skipping.")
        else:
            url = f"https://drive.google.com/uc?id={file_id}"
            logger.info(f"[setup] Downloading {file_name} to {NEW_DIR}...")
            gdown.download(url, dest_path, quiet=False)

    logger.info("[setup] All files ready!")

if __name__ == "__main__":
    setup()