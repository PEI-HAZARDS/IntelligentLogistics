from queue import Queue

class BrokerQueue():
    def __init__(self):
        self.queue = Queue()
    
    def get_queue(self):
        return self.queue
    
    def put_message(self, message):
        self.queue.put_nowait(message)

    def get_message(self, timeout=None):
        try:
            return self.queue.get(timeout=timeout)
        except Exception:
            return None