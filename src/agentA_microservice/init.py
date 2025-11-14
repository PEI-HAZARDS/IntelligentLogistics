import os
import signal
import sys
import logging

# Auto-configure PYTHONPATH for local execution
# This ensures it works both in Docker (/app) and locally
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(current_dir)  # Go up to 'src/'
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

logger = logging.getLogger("init-AgentA")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s – %(message)s",
    handlers=[logging.StreamHandler()]
)

from agentA_microservice.src.AgentA import AgentA

def main():
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