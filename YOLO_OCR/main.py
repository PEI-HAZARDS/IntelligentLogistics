from time import sleep
from threading import Thread
from agentA_microservice.src.AgentA import AgentA
from agentB_microservice.src.AgentB import AgentB

def main():
    agent_a = AgentA()

    agent_a.run()

if __name__ == "__main__":
    main()