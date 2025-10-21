from shared_utils.Logger import GlobalLogger
from multiprocessing import Manager

class BrokerQueue:
    def __init__(self, manager=None):
        if manager is None:
            manager = Manager()
        self.queue = manager.Queue()
        self.logger = GlobalLogger().get_logger()

    def put_message(self, message):
        self.logger.debug(f"[Broker] Putting message: {message}")
        self.queue.put_nowait(message)

    def get_message(self, timeout=None):
        try:
            msg = self.queue.get(timeout=timeout)
            self.logger.debug(f"[Broker] Got message: {msg}")
            return msg
        except Exception:
            return None
