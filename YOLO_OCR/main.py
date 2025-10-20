from shared_utils.Broker import *
import threading
import time
from agentA_microservice.src.AgentA import AgentA
from agentB_microservice.src.AgentB import AgentB

def main():
    broker = BrokerQueue()

    agent_a = AgentA(broker=broker)
    agent_b = AgentB(broker=broker)

    t_a = threading.Thread(target=agent_a.run, daemon=True)
    t_b = threading.Thread(target=agent_b.run, daemon=True)
    t_a.start()
    t_b.start()

    try:
        while t_a.is_alive() or t_b.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        agent_a.stop()
        agent_b.stop()
        time.sleep(0.5)

if __name__ == "__main__":
    main()