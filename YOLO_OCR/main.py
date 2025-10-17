from time import sleep
from threading import Thread
from src.AgentA import AgentA
from src.AgentB import AgentB

def main():
    agent_a = AgentA()

    # run agent A in background thread so main can continue and call stop()
    t = Thread(target=agent_a.run, daemon=True)
    t.start()

    # run agent A for 10 sec
    sleep(30)
    agent_a.stop()

    # wait briefly for clean shutdown
    t.join(timeout=2)

if __name__ == "__main__":
    main()