import logging
import sys

from V_APP.v_brain.config import VBrainConfig
from V_APP.v_brain.src.v_brain import VBrain

# ── Logging ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S,%f",
    stream=sys.stdout,
)
logger = logging.getLogger("VBrain")


def main():
    config = VBrainConfig()
    logger.info(f"V_Brain configuration: gate_ids={config.gate_id_list}, "
                f"kafka={config.kafka_bootstrap}, "
                f"timeout={config.correlator_timeout_seconds}s")

    brain = VBrain(config=config)
    brain.start()


if __name__ == "__main__":
    main()
