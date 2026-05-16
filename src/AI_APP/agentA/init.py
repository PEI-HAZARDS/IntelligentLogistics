import os
import signal
import sys
import logging

# Prometheus metrics
from prometheus_client import start_http_server, Gauge # type: ignore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s – %(message)s",
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger("init-AgentA")

from agentA.src.agentA import AgentA, AgentAConfig

# Prometheus metrics
METRICS_PORT = int(os.getenv("METRICS_PORT", 8000))
AGENT_UP = Gauge('agent_up', 'Agent is running', ['agent'])

def main():
    config = AgentAConfig()
    logger.info(f"AgentA config loaded: gate_id={config.gate_id}, models_path={config.models_path}")

    # Start Prometheus metrics server
    logger.info(f"Starting Prometheus metrics server on port {METRICS_PORT}")
    start_http_server(METRICS_PORT)
    AGENT_UP.labels(agent='agent-a').set(1)

    agent = AgentA(config=config)

    # Register signal handler for graceful shutdown
    def signal_handler(sig, frame):
        logger.info(f"Signal {sig} received, stopping agent...")
        AGENT_UP.labels(agent='agent-a').set(0)
        try:
            agent.stop()
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
        finally:
            sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        agent.start()
    
    except KeyboardInterrupt:
        logger.info("\nKeyboard interrupt received, stopping agent...")
        AGENT_UP.labels(agent='agent-a').set(0)
        agent.stop()
    
    except Exception as e:
        logger.exception("Unexpected error")
        AGENT_UP.labels(agent='agent-a').set(0)
        agent.stop()
        raise

if __name__ == "__main__":
    main()