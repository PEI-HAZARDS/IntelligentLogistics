import os
import sys
import shutil
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s – %(message)s")
logger = logging.getLogger("setup-AgentC")

# Make the ml-registry scripts importable
_REGISTRY_SCRIPTS = os.path.join(
    os.path.dirname(__file__),   # agentC/
    "..", "..", "ml-registry", "scripts"
)
sys.path.insert(0, os.path.abspath(_REGISTRY_SCRIPTS))

from download_model import load_model, ModelRequest  # type: ignore


# --- Model config ---
MODEL_NAME   = "hazard-plate-detector"
MODEL_ALIAS  = "champion"
DEST_DIR     = os.path.join(os.path.dirname(__file__), "data")
DEST_FILE    = "hazard_plate_model.pt"


def setup():
    logger.info(f"[setup] Downloading model '{MODEL_NAME}@{MODEL_ALIAS}' from MLflow registry...")

    os.makedirs(DEST_DIR, exist_ok=True)
    dest_path = os.path.join(DEST_DIR, DEST_FILE)

    if os.path.exists(dest_path):
        logger.info(f"[setup] {DEST_FILE} already exists in data/ — skipping download.")
        return

    pt_path = load_model(ModelRequest(model_name=MODEL_NAME, alias=MODEL_ALIAS))

    # Copy from cache to the expected model directory
    shutil.copy2(pt_path, dest_path)
    logger.info(f"[setup] Model saved to {dest_path}")
    logger.info("[setup] All files ready!")


if __name__ == "__main__":
    setup()