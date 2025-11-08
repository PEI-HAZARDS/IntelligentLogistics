""" from multiprocessing import Process, Manager
import time
from shared_utils.Broker import BrokerQueue
from agentA_microservice.src.AgentA import AgentA
from agentB_microservice.src.AgentB import AgentB


def run_agent(agent_class, shared_broker):
    Run a single agent in its own process.
    agent = agent_class(broker=shared_broker)
    try:
        agent.run()
    except KeyboardInterrupt:
        agent.stop()


def main():
    with Manager() as manager:
        # Pass the manager so the queue is process-safe
        broker = BrokerQueue(manager)

        # Create agent processes
        p_a = Process(target=run_agent, args=(AgentA, broker), name="AgentA")
        p_b = Process(target=run_agent, args=(AgentB, broker), name="AgentB")

        p_a.start()
        p_b.start()

        try:
            # Keep main alive while both agents run
            while p_a.is_alive() or p_b.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("Stopping agents...")
            p_a.terminate()
            p_b.terminate()
        finally:
            p_a.join()
            p_b.join()


if __name__ == "__main__":
    main()
 """

from multiprocessing import Process
import time
from agentA_microservice.src.AgentA import AgentA
from agentB_microservice.src.AgentB import AgentB  # <- versão Kafka (consumer)

def run_agent(agent_class):
    agent = agent_class()  # não passamos mais broker
    try:
        agent._loop()
    except KeyboardInterrupt:
        agent._loop()

def main():
    p_a = Process(target=run_agent, args=(AgentA,), name="AgentA")
    p_b = Process(target=run_agent, args=(AgentB,), name="AgentB")

    p_a.start()
    p_b.start()

    try:
        while p_a.is_alive() or p_b.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Stopping agents…")
        p_a.terminate()
        p_b.terminate()
    finally:
        p_a.join()
        p_b.join()

if __name__ == "__main__":
    main()
